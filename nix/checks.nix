# Checks run by `nix flake check` (and by CI). None of them reads or needs game data.
{
  pkgs,
  self,
  rexglue-src,
  rexglue-sdk,
  vulkan-probe,
  iso-identify,
  private-guard,
  private-project,
  address-compare,
}:

let
  python = pkgs.python3;
  elfDepsCheck = "${self}/tools/check_elf_deps.sh";

  # Broken ELF samples for the self-test of tools/check_elf_deps.sh, each in its own store
  # path: the loader's error lines then start with /nix/store/, the case the first version
  # of the C1.3 check let through (J1 review of PR #2). They are cut from or derived from
  # an SDK library, so they hold no game data.
  brokenElfTruncated = pkgs.runCommand "elf-sample-truncated.so" { } ''
    head -c 64 ${rexglue-sdk}/lib/librexbase.so > "$out"
  '';
  brokenElfMissingNeeded =
    pkgs.runCommand "elf-sample-missing-needed.so" { nativeBuildInputs = [ pkgs.patchelf ]; }
      ''
        cp ${rexglue-sdk}/lib/librexbase.so "$out"
        chmod u+w "$out"
        patchelf --add-needed libfifa2010wc-does-not-exist.so.1 "$out"
      '';
in
{
  # The SDK itself: building it runs its unit tests (checkPhase in nix/rexglue-sdk.nix).
  inherit rexglue-sdk;

  # The same SDK built in Debug, for its tests: eight lock order tests run only in debug
  # builds (they SKIP under NDEBUG, as in the Release package above).
  rexglue-sdk-debug-tests = rexglue-sdk.overrideAttrs (_: {
    pname = "rexglue-sdk-debug-tests";
    cmakeBuildType = "Debug";
    # Built after the Release SDK, never at the same time. Some kernel tests hand work
    # between guest threads that spin (e.g. "XamGetOverlappedResult sees the event set
    # once the result is complete": 20000 handoffs, 20 s deadline, 1.65 s when the CPUs
    # are free). In CI the Debug tests ran while the Release SDK was compiling on the 4
    # vCPUs of the runner, and that test missed its deadline. Referencing the Release
    # output makes it a build input, so Nix orders the two builds.
    FIFA2010WC_BUILT_AFTER = "${rexglue-sdk}";
  });

  # C1.3: the SDK command line tool runs inside the Nix build sandbox. The sandbox has no
  # FHS library folders and no nix-ld or steam-run: only the store paths of the inputs.
  rexglue-cli-runs =
    pkgs.runCommand "rexglue-cli-runs"
      {
        nativeBuildInputs = [
          pkgs.patchelf
          pkgs.file
        ];
      }
      ''
        set -euo pipefail
        mkdir -p "$out"
        log="$out/report.txt"
        sdk=${rexglue-sdk}

        {
          echo "== Sandbox root (no FHS library folders expected)"
          ls -1 /
          for d in /lib /lib64 /usr/lib /usr/lib64; do
            if [ -e "$d" ]; then echo "unexpected FHS folder: $d"; exit 1; fi
          done
          echo "no /lib, /lib64, /usr/lib or /usr/lib64"
        } > "$log"

        interp=$(patchelf --print-interpreter "$sdk/bin/rexglue")
        case "$interp" in
          /nix/store/*) echo "== Interpreter: $interp" >> "$log" ;;
          *) echo "interpreter outside the store: $interp" >&2; exit 1 ;;
        esac

        echo "== Dynamic dependencies of every ELF file of the SDK" >> "$log"
        # Fails on a non-zero exit of `ld.so --list`, a dependency not found, or a path
        # outside the store (tools/check_elf_deps.sh).
        bash ${elfDepsCheck} "$interp" "$sdk"/bin/* "$sdk"/lib/*.so* >> "$log"

        echo "== Libraries opened with dlopen() are on the RUNPATH" >> "$log"
        for lib in libSDL3.so.0 librexgpu-xenos-vulkan.so; do
          rpath=$(patchelf --print-rpath "$sdk/lib/$lib")
          case ":$rpath:" in
            *:${pkgs.vulkan-loader}/lib:*) echo "$lib: vulkan-loader on RUNPATH" >> "$log" ;;
            *) echo "$lib: vulkan-loader missing from RUNPATH ($rpath)" >&2; exit 1 ;;
          esac
        done

        echo "== $sdk/bin/rexglue --help" >> "$log"
        "$sdk/bin/rexglue" --help > "$out/rexglue-help.txt" 2>&1
        echo "exit status 0" >> "$log"
        cat "$out/rexglue-help.txt" >> "$log"
      '';

  # Regression proof for the ELF check used by rexglue-cli-runs: it accepts the SDK and
  # rejects a file the loader cannot analyse and a file with a missing dependency, both
  # stored under /nix/store.
  elf-deps-check-selftest =
    pkgs.runCommand "elf-deps-check-selftest"
      {
        nativeBuildInputs = [
          pkgs.patchelf
          pkgs.file
        ];
      }
      ''
        set -euo pipefail
        mkdir -p "$out"
        interp=$(patchelf --print-interpreter ${rexglue-sdk}/bin/rexglue)

        bash ${elfDepsCheck} "$interp" ${rexglue-sdk}/bin/* ${rexglue-sdk}/lib/*.so* \
          > "$out/sdk.txt"
        cat "$out/sdk.txt"

        expect_failure() {
          name=$1
          shift
          if bash ${elfDepsCheck} "$interp" "$@" > "$out/$name.txt" 2>&1; then
            echo "$name: the check accepted a broken file" >&2
            cat "$out/$name.txt" >&2
            exit 1
          fi
          echo "$name: rejected as expected"
          cat "$out/$name.txt"
        }
        expect_failure truncated ${brokenElfTruncated}
        expect_failure missing-needed ${brokenElfMissingNeeded}
        # One broken file among valid ones must still fail the whole run.
        expect_failure mixed ${rexglue-sdk}/bin/rexglue ${brokenElfTruncated}

        if bash ${elfDepsCheck} "$interp" > "$out/usage.txt" 2>&1; then
          echo "usage: missing arguments were accepted" >&2
          exit 1
        fi
        echo "usage error rejected as expected"
      '';

  # The CMake skeleton configures against the SDK package with the linux-amd64-release preset,
  # with REXGLUE_LLD set as in the dev shell. The preset passes it to CMake (J1 P-05, J2 A7).
  # Negative controls: without the variable, or with another ld.lld, the configure step stops.
  cmake-skeleton =
    pkgs.llvmPackages_20.stdenv.mkDerivation {
      name = "fifa2010wc-cmake-skeleton";
      src = self;
      nativeBuildInputs = [
        pkgs.cmake
        pkgs.ninja
      ];
      buildInputs = [ rexglue-sdk ];
      # The same value as in the dev shell (flake.nix).
      REXGLUE_LLD = "${pkgs.llvmPackages_20.bintools}/bin/ld.lld";
      dontUseCmakeConfigure = true;
      buildPhase = ''
        runHook preBuild
        set -euo pipefail
        cmake --preset linux-amd64-release 2>&1 | tee configure.log
        grep -E "^REXGLUE_LLD:[A-Z]+=$REXGLUE_LLD\$" out/build/linux-amd64-release/CMakeCache.txt \
          | tee -a configure.log
        expect_refusal() { # <name> <message> <command>...
          name=$1; message=$2; shift 2
          if "$@" > "$name.log" 2>&1; then
            echo "$name: the configure step accepted it" >&2; cat "$name.log" >&2; exit 1
          fi
          # CMake wraps long messages: compare with the line breaks folded into spaces.
          tr -s ' \n' '  ' < "$name.log" | grep -qF "$message" || { cat "$name.log" >&2; exit 1; }
          echo "$name: refused as expected" | tee -a configure.log
        }
        expect_refusal no-variable "REXGLUE_LLD is not set in the environment" \
          env -u REXGLUE_LLD cmake --preset linux-amd64-release -B "$TMPDIR/no-variable"
        expect_refusal other-lld "not the wrapped ld.lld of the dev shell" \
          cmake --preset linux-amd64-release -B "$TMPDIR/other-lld" \
            -DREXGLUE_LLD=${pkgs.llvmPackages_20.lld}/bin/ld.lld
        runHook postBuild
      '';
      installPhase = ''
        mkdir -p "$out"
        cp configure.log no-variable.log other-lld.log "$out/"
      '';
    };

  # J2 step A7 (docs/J2_A7_SYNTHETIC_CHAIN.md): code generation, compilation, linking and
  # running of a host program, the way the game executable will be built, with no game data.
  # 1. The PowerPC instruction tests of the ReXGlue source (tests/ppc/asm, BSD-3-Clause) are
  #    assembled by the GNU binutils of nixpkgs, built from source. Those binutils have no
  #    VMX128: the tests they refuse must be exactly the list in tests/a7-chain.
  # 2. The installed `rexglue recompile-tests` turns them into C++ and Catch2 cases.
  # 3. tests/a7-chain builds them against the installed SDK through rexglue_configure_target,
  #    with -DREXGLUE_LLD set to the wrapped ld.lld (J1 finding P-05).
  # 4. Every dynamic dependency of the program resolves in the store or among the SDK
  #    libraries staged next to it, which are byte-identical to the package's, so the Vulkan
  #    driver keeps vulkan-loader on its RUNPATH (P-07). Then the Catch2 cases run.
  # 5. Negative controls: without -DREXGLUE_LLD the configure step stops; with the plain lld
  #    the dependency check refuses the program (P-05 reproduced).
  # Nothing generated is kept in the output: only logs and reports.
  a7-synthetic-chain =
    let
      ppcBinutils = pkgs.pkgsCross.ppc-embedded.buildPackages.binutils-unwrapped;
      wrappedLld = "${pkgs.llvmPackages_20.bintools}/bin/ld.lld";
      plainLld = "${pkgs.llvmPackages_20.lld}/bin/ld.lld";
    in
    pkgs.llvmPackages_20.stdenv.mkDerivation {
      name = "a7-synthetic-chain";
      src = self;
      nativeBuildInputs = [
        pkgs.cmake
        pkgs.ninja
        pkgs.patchelf
        pkgs.file
        ppcBinutils
      ];
      buildInputs = [
        rexglue-sdk
        pkgs.catch2_3
      ];
      # Same reason as for the SDK build (nix/rexglue-sdk.nix) and the dev shell.
      hardeningDisable = [
        "fortify"
        "fortify3"
      ];
      dontUseCmakeConfigure = true;
      buildPhase = ''
        runHook preBuild
        set -euo pipefail
        W="$NIX_BUILD_TOP/a7"
        R="$W/report"
        mkdir -p "$W"/obj "$W"/bin "$W"/asm "$W"/gen "$W"/gen-small "$W"/bin-small "$W"/asm-small "$R"
        export HOME="$W/home"
        mkdir -p "$HOME"
        upstream=${rexglue-src}/tests/ppc/asm

        echo "== 1. Assembling $upstream with $(powerpc-none-eabi-as --version | head -n 1)" \
          > "$R/chain.txt"
        refused=""
        for s in "$upstream"/*.s; do
          n=$(basename "$s" .s)
          # The upstream flags (cmake/ppc_test_pipeline.cmake) without -mvmx128.
          if powerpc-none-eabi-as -a32 -be -mregnames -mpower7 -maltivec -mvsx -R \
               -o "$W/obj/$n.o" "$s" 2> "$W/obj/$n.err"; then
            powerpc-none-eabi-ld -A powerpc:common32 -melf32ppc -EB -nostdlib --oformat=binary \
              -Ttext=0x82010000 -e 0x82010000 -o "$W/bin/$n.bin" "$W/obj/$n.o"
            powerpc-none-eabi-nm --numeric-sort "$W/obj/$n.o" > "$W/bin/$n.map"
            cp "$s" "$W/asm/"
          else
            refused="$refused$n"$'\n'
          fi
        done
        printf '%s' "$refused" | sort > "$R/refused.txt"
        grep -vE '^(#|$)' tests/a7-chain/vmx128-tests.txt | sort > "$W/expected-refused.txt"
        if ! diff -u "$W/expected-refused.txt" "$R/refused.txt" >> "$R/chain.txt"; then
          echo "the tests refused by the assembler differ from tests/a7-chain/vmx128-tests.txt" >&2
          cat "$R/chain.txt" >&2
          exit 1
        fi
        total=$(ls "$upstream"/*.s | wc -l)
        built=$(ls "$W"/bin/*.bin | wc -l)
        echo "$built of $total test programs assembled; the $((total - built)) refused are the VMX128 list" \
          >> "$R/chain.txt"

        echo "== 2. rexglue recompile-tests" >> "$R/chain.txt"
        REX_LOG_FILE=false ${rexglue-sdk}/bin/rexglue recompile-tests --bin-dir="$W/bin" \
          --asm-dir="$W/asm" --output="$W/gen" --case-files=8 > "$R/recompile-tests.log" 2>&1
        cases=$(cat "$W"/gen/ppc_test_cases_*.cpp | grep -c '^TEST_CASE(' || true)
        echo "exit status 0, $cases Catch2 cases" >> "$R/chain.txt"
        if [ "$cases" -lt "$built" ]; then
          echo "fewer cases ($cases) than test programs ($built)" >&2
          exit 1
        fi

        configure() { # <build dir> <generated dir> [cmake arguments]
          b=$1; g=$2; shift 2
          cmake -S tests/a7-chain -B "$b" -G Ninja -DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_CXX_FLAGS=-march=x86-64-v2 \
            -DA7_GENERATED_DIR="$g" "$@"
        }
        interp=$(patchelf --print-interpreter ${rexglue-sdk}/bin/rexglue)
        # Every dependency resolves in the store or in the program's own folder.
        deps_ok() { # <elf file>
          d=$(dirname "$1")
          deps=$("$interp" --list "$1" 2>&1) || { printf '%s\n' "$deps"; return 1; }
          printf '%s\n' "$deps"
          if printf '%s\n' "$deps" | grep -q 'not found'; then return 1; fi
          if printf '%s\n' "$deps" | grep -E '=> /' | grep -vE "=> (/nix/store/|$d/)"; then
            return 1
          fi
          case "$(patchelf --print-interpreter "$1")" in /nix/store/*) ;; *) return 1 ;; esac
        }

        echo "== 3. Host build against ${rexglue-sdk}, REXGLUE_LLD=${wrappedLld}" >> "$R/chain.txt"
        # The first A7 run found module locations under "''${PACKAGE_PREFIX_DIR}//nix/store/..."
        # (an absolute CMAKE_INSTALL_LIBDIR joined to the prefix; nix/rexglue-sdk.nix).
        if grep -nE 'PACKAGE_PREFIX_DIR[}]//' ${rexglue-sdk}/lib/cmake/rexglue/*.cmake; then
          echo "the SDK package files join an absolute folder to their prefix" >&2; exit 1
        fi
        modules=0
        while read -r location; do
          [ -f "$location" ] || { echo "missing module file: $location" >&2; exit 1; }
          modules=$((modules + 1))
        done < <(sed -n -E 's@.*IMPORTED_LOCATION_RELEASE "\$\{PACKAGE_PREFIX_DIR\}/([^"]+)".*@${rexglue-sdk}/\1@p' \
                   ${rexglue-sdk}/lib/cmake/rexglue/rexglueModules-Release.cmake)
        [ "$modules" -gt 0 ] || { echo "no module location in rexglueModules-Release.cmake" >&2; exit 1; }
        echo "$modules provider module locations of the package exist" >> "$R/chain.txt"
        configure "$W/build" "$W/gen" -DREXGLUE_LLD=${wrappedLld} > "$R/configure.log" 2>&1
        cmake --build "$W/build" > "$R/build.log" 2>&1
        host="$W/build/a7_ppc_tests"
        grep -q -- "--ld-path=${wrappedLld}" "$W/build/build.ninja"
        echo "linked with --ld-path=${wrappedLld}" >> "$R/chain.txt"

        echo "== 4. Dependencies, RUNPATH and staged libraries" >> "$R/chain.txt"
        rpath=$(patchelf --print-rpath "$host")
        echo "RUNPATH: $rpath" >> "$R/chain.txt"
        case ":$rpath:" in *:'$ORIGIN':*) ;; *) echo "no \$ORIGIN on the RUNPATH" >&2; exit 1 ;; esac
        deps_ok "$host" > "$R/host-deps.txt" || { cat "$R/host-deps.txt" >&2; exit 1; }
        echo "a7_ppc_tests: every dependency resolved (host-deps.txt)" >> "$R/chain.txt"
        staged=0
        for f in "$W"/build/*.so*; do
          name=$(basename "$f")
          cmp "$f" ${rexglue-sdk}/lib/"$name"
          staged=$((staged + 1))
        done
        echo "$staged staged files, each identical to the SDK package's" >> "$R/chain.txt"
        rpath=$(patchelf --print-rpath "$W/build/librexgpu-xenos-vulkan.so")
        case ":$rpath:" in
          *:${pkgs.vulkan-loader}/lib:*) echo "staged librexgpu-xenos-vulkan.so: vulkan-loader on RUNPATH" >> "$R/chain.txt" ;;
          *) echo "staged Vulkan driver without vulkan-loader on its RUNPATH" >&2; exit 1 ;;
        esac

        echo "== 5. Catch2 cases" >> "$R/chain.txt"
        (cd "$W/build" && ./a7_ppc_tests --reporter console::out="$R/ppc-tests.txt" \
          --reporter junit::out="$R/ppc-tests-junit.xml") || {
          tail -n 40 "$R/ppc-tests.txt" >&2; exit 1; }
        tail -n 3 "$R/ppc-tests.txt" >> "$R/chain.txt"

        echo "== 6. Negative controls (P-05)" >> "$R/chain.txt"
        # One small test program is enough for the controls.
        cp "$W/bin/instr_add.bin" "$W/bin/instr_add.map" "$W/bin-small/"
        cp "$W/asm/instr_add.s" "$W/asm-small/"
        REX_LOG_FILE=false ${rexglue-sdk}/bin/rexglue recompile-tests --bin-dir="$W/bin-small" \
          --asm-dir="$W/asm-small" --output="$W/gen-small" > "$R/recompile-small.log" 2>&1
        # a. No -DREXGLUE_LLD and no ld.lld on PATH: the SDK stops the configure step.
        if configure "$W/build-nolld" "$W/gen-small" > "$R/configure-nolld.log" 2>&1; then
          echo "configure succeeded without REXGLUE_LLD" >&2; exit 1
        fi
        grep -q "ReXGlue links with lld" "$R/configure-nolld.log"
        echo "a. without REXGLUE_LLD: configure stops with the SDK's lld message" >> "$R/chain.txt"
        # b. The plain lld, outside the Nix linker wrapper: the program builds, and the
        #    dependency check refuses it.
        configure "$W/build-plain" "$W/gen-small" -DREXGLUE_LLD=${plainLld} \
          > "$R/configure-plain.log" 2>&1
        cmake --build "$W/build-plain" > "$R/build-plain.log" 2>&1
        if deps_ok "$W/build-plain/a7_ppc_tests" > "$R/plain-deps.txt" 2>&1; then
          echo "the program linked by the plain lld passed the dependency check" >&2
          cat "$R/plain-deps.txt" >&2
          exit 1
        fi
        echo "b. plain lld: dependency check refuses the program (plain-deps.txt)" >> "$R/chain.txt"
        grep -E 'not found|cannot open|error while loading' "$R/plain-deps.txt" | head -n 5 >> "$R/chain.txt" || true
        echo "  interpreter: $(patchelf --print-interpreter "$W/build-plain/a7_ppc_tests")" \
          >> "$R/chain.txt"
        runHook postBuild
      '';
      installPhase = ''
        mkdir -p "$out"
        # Reports and logs only: no generated source, object or program.
        for f in "$NIX_BUILD_TOP"/a7/report/*; do cat "$f" > "$out/$(basename "$f")"; done
        cat "$out/chain.txt"
      '';
    };

  # D-015 (O3): the SDK patch series leaves XEX loading and decryption as upstream wrote
  # them. Lists every file the patches touch, and fails if one is an XEX or cryptography
  # file (src/filesystem/xex.cpp, src/kernel/xex_module.cpp, thirdparty/excrypt, ...).
  # The rule is first run on a synthetic patch that touches xex.cpp, which must be refused.
  # Whether the series applies is tested by the SDK build itself.
  sdk-patches = pkgs.runCommand "sdk-patches" { } ''
    set -euo pipefail
    mkdir -p "$out"
    touched() { sed -n -E 's@^(\+\+\+|---) [ab]/@@p' "$@" | sort -u; }
    forbidden() { grep -iE 'xex|crypt' || true; }

    printf '%s\n' 'diff --git a/src/filesystem/xex.cpp b/src/filesystem/xex.cpp' \
      '--- a/src/filesystem/xex.cpp' '+++ b/src/filesystem/xex.cpp' > negative.patch
    [ -n "$(touched negative.patch | forbidden)" ] \
      || { echo "the rule does not refuse a patch of xex.cpp"; exit 1; }

    patches=(${self}/patches/rexglue-sdk/*.patch)
    [ -f "''${patches[0]}" ] || { echo "no patch in patches/rexglue-sdk"; exit 1; }
    touched "''${patches[@]}" > "$out/touched-files.txt"
    cat "$out/touched-files.txt"
    bad=$(forbidden < "$out/touched-files.txt")
    if [ -n "$bad" ]; then
      echo "a patch touches an XEX or cryptography file (O3, D-015): $bad"
      exit 1
    fi
  '';

  # J0: the disc identification tool, tested on synthetic disc images and XEX headers made
  # at run time (no game data). The tests also check that the key and signature fields of
  # an XEX never reach a report, and that a report passes the proprietary data check.
  # It is also run on the synthetic GDFX fixture of the pinned ReXGlue source, against the
  # file names and contents ReXGlue's own test expects (cross-check of the XDVDFS reader).
  iso-identify-selftest = pkgs.runCommand "iso-identify-selftest" { REXGLUE_SRC = rexglue-src; } ''
    set -euo pipefail
    mkdir -p "$out"
    ${python}/bin/python3 -I ${self}/tools/test_iso_identify.py > "$out/selftest.txt" 2>&1 \
      || { cat "$out/selftest.txt"; exit 1; }
    tail -n 3 "$out/selftest.txt"
    grep -q '^test_rexglue_gdfx_fixture .* ok$' "$out/selftest.txt" \
      || { echo "the ReXGlue fixture cross-check did not run"; exit 1; }
    # The refusal of a source in /nix/store is also tested on a real store file.
    grep -q '^test_real_store_path_is_refused_and_left_untouched .* ok$' "$out/selftest.txt" \
      || { echo "the /nix/store refusal test did not run"; exit 1; }
    # The packaged command starts and prints its usage.
    ${iso-identify}/bin/fifa2010wc-iso-identify --help > "$out/help.txt"
  '';

  # J2 step A4: the CP-1 and CP-4 controls (tools/private_guard.py), on synthetic folders
  # only. In the build sandbox the tests run as an unprivileged user, so the full cycle
  # (preflight, a write outside the private folder, postflight) is exercised, and the
  # refusal of a private folder in /nix/store is tested on the store path of Python.
  private-guard-selftest = pkgs.runCommand "private-guard-selftest" { nativeBuildInputs = [ pkgs.git ]; } ''
    set -euo pipefail
    mkdir -p "$out"
    ${python}/bin/python3 -I ${self}/tools/test_private_guard.py > "$out/selftest.txt" 2>&1 \
      || { cat "$out/selftest.txt"; exit 1; }
    tail -n 3 "$out/selftest.txt"
    for t in test_store_path_is_refused test_full_cycle_with_the_command_line \
             test_folder_inside_the_repository_is_refused; do
      grep -q "^$t .* ok$" "$out/selftest.txt" || { echo "$t did not run"; exit 1; }
    done
    ${private-guard}/bin/fifa2010wc-private-guard --help > "$out/help.txt"
  '';

  # J2 step A6 (#21, docs/J2_A6_LINUX_GAPS.md): the settings of the phase B procedure
  # (docs/J2_PHASE_B_CONTROLS.md) confine what a rexglue command writes, on a synthetic disc
  # image made by the J0 test helpers (two text files, no game data). Not root (the build
  # user), umask 077, no core dump, TMPDIR, XDG folders and REX_APP_ROOT in the private
  # folder, private_guard preflight and postflight around `rexglue vfs dump`.
  # 1. As the procedure says: preflight passes, the tree and the log land in the private
  #    folder with private modes, nothing in the home folder, postflight passes.
  # 2. Without the procedure's settings: preflight refuses; the same step run anyway writes
  #    its log under the home folder, and postflight reports it.
  # 3. With umask 022: preflight refuses.
  linux-confinement =
    pkgs.runCommand "linux-confinement" { nativeBuildInputs = [ pkgs.git ]; } ''
      set -euo pipefail
      mkdir -p "$out"
      G=${private-guard}/bin/fifa2010wc-private-guard
      REX=${rexglue-sdk}/bin/rexglue
      W="$TMPDIR"
      H="$W/home"
      P="$W/private"
      mkdir -m 700 "$H" "$P"
      (cd "$P" && mkdir -m 700 iso game xex generated cache saves logs)
      ${python}/bin/python3 -I -c '
      import importlib.util, sys
      spec = importlib.util.spec_from_file_location("t", sys.argv[1])
      t = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(t)
      t.write_image(sys.argv[2], {"default.txt": b"synthetic disc\n",
                                  "media": {"readme.txt": b"no game data\n"}})
      ' ${self}/tools/test_iso_identify.py "$P/iso/synthetic.iso"
      chmod a-w "$P/iso/synthetic.iso"

      # The environment of docs/J2_PHASE_B_CONTROLS.md section 2, in a subshell.
      procedure() {
        umask 077
        ulimit -c 0
        export HOME="$H" WC2010_PRIVATE_DIR="$P"
        export TMPDIR="$P/tmp" XDG_CONFIG_HOME="$P/xdg/config" XDG_DATA_HOME="$P/xdg/data"
        export XDG_CACHE_HOME="$P/xdg/cache" REX_APP_ROOT="$P/app"
        mkdir -p "$TMPDIR" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$REX_APP_ROOT"
        cd "$P"
      }
      pre() {
        "$G" preflight --dest "$P/game" --game-root "$P/game" --sdk-bin ${rexglue-sdk}/bin \
          --marker "$P/logs/$1.marker"
      }
      post() {
        "$G" postflight --marker "$P/logs/$1.marker" --watch "$H" --watch "$W/outside"
      }
      mkdir -m 700 "$W/outside"

      # 1. As the procedure says.
      (
        procedure
        pre ok
        "$REX" vfs dump "$P/iso/synthetic.iso" "$P/game"
        post ok
      ) > "$out/1-procedure.txt" 2>&1 || { cat "$out/1-procedure.txt"; exit 1; }
      cat "$out/1-procedure.txt"
      [ "$(cat "$P/game/default.txt")" = "synthetic disc" ] || { echo "bad default.txt"; exit 1; }
      [ "$(cat "$P/game/media/readme.txt")" = "no game data" ] || { echo "bad readme.txt"; exit 1; }
      logs=$(find "$P/app" -name '*.log')
      [ -n "$logs" ] || { echo "no log under REX_APP_ROOT"; exit 1; }
      for f in "$P/game/default.txt" "$P/game/media/readme.txt" $logs; do
        mode=$(stat -c %a "$f")
        [ "$mode" = 600 ] || { echo "$f has mode $mode, not 600 (umask 077)"; exit 1; }
      done
      [ -z "$(find "$H" -mindepth 1)" ] || { echo "the step wrote in the home folder"; exit 1; }
      echo "1: tree and log in the private folder, mode 600, home folder untouched" \
        >> "$out/1-procedure.txt"

      # 2. Without the procedure's settings: HOME only, as in a plain shell.
      rm -rf "$P/game"/* "$P/app"
      status=0
      (
        umask 077
        ulimit -c 0
        export HOME="$H" WC2010_PRIVATE_DIR="$P"
        unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME REX_APP_ROOT
        export TMPDIR="$W/outside"
        cd "$P"
        pre bad || status=$?
        echo "preflight status: $status"
        [ "$status" -eq 1 ] || exit 10
        # The marker is only written by a passing preflight: write it here, then run the
        # step anyway, as someone who ignored the refusal would.
        touch "$P/logs/bad.marker"
        sleep 1
        "$REX" vfs dump "$P/iso/synthetic.iso" "$P/game" || true
        poststatus=0
        post bad || poststatus=$?
        echo "postflight status: $poststatus"
        [ "$poststatus" -eq 1 ] || exit 11
      ) > "$out/2-without-settings.txt" 2>&1 || { cat "$out/2-without-settings.txt"; exit 1; }
      cat "$out/2-without-settings.txt"
      grep -q "REX_APP_ROOT" "$out/2-without-settings.txt" \
        || { echo "preflight did not name REX_APP_ROOT"; exit 1; }
      grep -q "file written outside the private folder: $H/.config/rexglue" \
        "$out/2-without-settings.txt" || { echo "postflight missed the log in HOME"; exit 1; }

      # 3. umask 022.
      status=0
      ( procedure; umask 022; pre umask ) > "$out/3-umask.txt" 2>&1 || status=$?
      cat "$out/3-umask.txt"
      [ "$status" -eq 1 ] && grep -q "umask is 022" "$out/3-umask.txt" \
        || { echo "preflight accepted umask 022"; exit 1; }
    '';

  # J2 step A5: the codegen manifest template and tools/private_project.py, on synthetic
  # private folders only. The unit tests check the template (relative paths, no game data,
  # pinned SDK) and the init and check commands. Then ReXGlue's own parser reads the copy
  # made by init, in a synthetic private folder that holds no XEX: it must name the project
  # and its module, report no unknown key, resolve the entry XEX inside the private folder,
  # and stop there, before reading any XEX, without writing a file. Its log file is off and
  # its app root is in the build folder.
  private-project-selftest =
    pkgs.runCommand "private-project-selftest" { nativeBuildInputs = [ pkgs.git ]; } ''
      set -euo pipefail
      mkdir -p "$out"
      ${python}/bin/python3 -I ${self}/tools/test_private_project.py > "$out/selftest.txt" 2>&1 \
        || { cat "$out/selftest.txt"; exit 1; }
      tail -n 3 "$out/selftest.txt"
      for t in test_repository_template_passes test_template_with_an_address_is_refused \
               test_init_refuses_a_folder_that_fails_cp1_and_writes_nothing \
               test_link_out_of_the_private_folder_is_refused \
               test_init_refuses_a_project_link_and_writes_nothing_outside \
               test_init_stops_on_a_link_put_in_place_during_init \
               test_template_paths_that_leave_the_private_root_are_refused_before_install \
               test_init_refuses_a_template_replaced_by_a_clean_one_after_reading; do
        grep -q "^$t .* ok$" "$out/selftest.txt" || { echo "$t did not run"; exit 1; }
      done
      ${private-project}/bin/fifa2010wc-private-project template > "$out/template.txt"
      cat "$out/template.txt"

      P="$TMPDIR/private"
      mkdir -m 700 "$P"
      (cd "$P" && mkdir -m 700 iso game xex generated cache saves logs)
      ${private-project}/bin/fifa2010wc-private-project --private-dir "$P" init > "$out/init.txt"
      cat "$out/init.txt"
      M="$P/project/wc2010_manifest.toml"
      cmp "$M" ${self}/config/private-template/wc2010_manifest.toml

      W="$TMPDIR/rex"
      mkdir -p "$W/app" "$W/home" "$W/tmp"
      touch "$W/marker"
      status=0
      (cd "$W" && env -i PATH="$PATH" HOME="$W/home" TMPDIR="$W/tmp" XDG_CONFIG_HOME="$W/home" \
        XDG_DATA_HOME="$W/home" XDG_CACHE_HOME="$W/home" REX_APP_ROOT="$W/app" \
        REX_LOG_FILE=false ${rexglue-sdk}/bin/rexglue codegen "$M") > "$out/rexglue.txt" 2>&1 \
        || status=$?
      cat "$out/rexglue.txt"
      [ "$status" -ne 0 ] || { echo "codegen must stop: the folder holds no XEX"; exit 1; }
      grep -q "Project:  wc2010" "$out/rexglue.txt" || { echo "project not read"; exit 1; }
      grep -q "Modules:  1 DLL" "$out/rexglue.txt" || { echo "module not read"; exit 1; }
      grep -qF "Entrypoint XEX not found: $P/project/../game/default.xex" "$out/rexglue.txt" \
        || { echo "the entry XEX does not resolve to game/default.xex"; exit 1; }
      if grep -q "unknown key" "$out/rexglue.txt"; then
        echo "ReXGlue reports an unknown key in the template"; exit 1
      fi
      cmp "$M" ${self}/config/private-template/wc2010_manifest.toml
      written=$(find "$P" "$W" -newer "$W/marker" ! -path "$W/marker")
      [ -z "$written" ] || { echo "codegen wrote: $written"; exit 1; }
      if ls /dev/shm 2>/dev/null | grep -q '^xenia_memory_'; then
        echo "a guest memory object is left in /dev/shm"; exit 1
      fi
      echo "ReXGlue read the template copy and wrote nothing" >> "$out/rexglue.txt"

      # P-40: with project/ a link to a folder outside the private folder, init must refuse
      # before writing anything, through the packaged command.
      L="$TMPDIR/linked"
      E="$TMPDIR/outside"
      mkdir -m 700 "$L" "$E"
      (cd "$L" && mkdir -m 700 iso game xex generated cache saves logs)
      ln -s "$E" "$L/project"
      status=0
      ${private-project}/bin/fifa2010wc-private-project --private-dir "$L" init \
        > "$out/links.txt" 2>&1 || status=$?
      cat "$out/links.txt"
      [ "$status" -eq 1 ] || { echo "init must refuse a project/ link"; exit 1; }
      [ -z "$(ls -A "$E")" ] || { echo "init wrote outside the private folder"; exit 1; }
      [ -z "$(ls -A "$L/generated")" ] || { echo "init created output folders"; exit 1; }
      echo "project/ link refused; the outside folder and generated/ stay empty" >> "$out/links.txt"
    '';

  # J2 step A8-bis (#22): the address comparator, on synthetic fixtures only (0x8C01xxxx
  # addresses, formats of the ReXGlue v0.11.0 source). Its unit tests cover the false
  # positives of docs/J2_A8_ADDRESS_VALIDATION.md section 4; then the packaged command runs
  # on a synthetic private folder: aggregated output with no address, the report in the
  # private folder only, and a report path outside it refused with nothing written.
  address-compare-selftest = pkgs.runCommand "address-compare-selftest" { } ''
    set -euo pipefail
    mkdir -p "$out"
    ${python}/bin/python3 -I ${self}/tools/test_address_compare.py > "$out/selftest.txt" 2>&1 \
      || { cat "$out/selftest.txt"; exit 1; }
    tail -n 3 "$out/selftest.txt"
    for t in test_entry_in_configuration_only_stays_n0 test_invalid_data_offset_stays_unverified \
             test_function_collision_is_reported test_absent_diagnostics_are_refused \
             test_unknown_or_partial_mappings_are_refused \
             test_paths_outside_the_private_folder_are_refused \
             test_paths_are_checked_before_any_file_is_read test_stop_lines_print_no_address \
             test_badly_typed_claims_are_refused_and_cannot_lift_a_stop \
             test_report_parent_swapped_for_a_link_is_refused; do
      grep -q "^$t .* ok$" "$out/selftest.txt" || { echo "$t did not run"; exit 1; }
    done

    P="$TMPDIR/private"
    mkdir -m 700 "$P"
    printf '[functions]\n0x8C010000 = {}\n0x8C010080 = {}\n' > "$P/entries.toml"
    printf '%s\n' 'const PPCFuncMapping kPPCFuncMappings[] = {' \
      '	{ 0x8C010000, sub_8C010000 },' '	{ 0, nullptr }' '};' > "$P/init.cpp"
    printf 'info: generation done\n' > "$P/codegen.log"
    AC=${address-compare}/bin/fifa2010wc-address-compare
    $AC --private-dir "$P" --entries function="$P/entries.toml" --mappings-with "$P/init.cpp" \
      --log "$P/codegen.log" --out "$P/report.json" > "$out/run.txt"
    cat "$out/run.txt"
    grep -q "function: refused 0, N0 1, N1 1, N2 0" "$out/run.txt"
    if grep -q "0x" "$out/run.txt"; then echo "addresses on standard output"; exit 1; fi
    [ -f "$P/report.json" ] || { echo "no report in the private folder"; exit 1; }
    status=0
    $AC --private-dir "$P" --entries function="$P/entries.toml" --mappings-with "$P/init.cpp" \
      --log "$P/codegen.log" --out "$TMPDIR/outside.json" > "$out/refused.txt" || status=$?
    cat "$out/refused.txt"
    [ "$status" -eq 2 ] && [ ! -e "$TMPDIR/outside.json" ] \
      || { echo "a report outside the private folder was not refused"; exit 1; }
  '';

  # D-007: no proprietary data among the tracked files of the repository.
  # The self-test needs git: the staged mode tests build a throwaway repository.
  proprietary-data-source = pkgs.runCommand "proprietary-data-source" { nativeBuildInputs = [ pkgs.git ]; } ''
    set -euo pipefail
    mkdir -p "$out"
    ${python}/bin/python3 -I ${self}/tools/test_check_proprietary_data.py > "$out/selftest.txt" 2>&1 \
      || { cat "$out/selftest.txt"; exit 1; }
    tail -n 3 "$out/selftest.txt"
    ${python}/bin/python3 -I ${self}/tools/check_proprietary_data.py tree ${self} > "$out/report.txt"
    cat "$out/report.txt"
  '';

  # D-007: no proprietary data in the store paths this flake builds or fetches: the runtime
  # closure of the SDK, of the Vulkan probe, of the identification tool and of the two
  # private folder tools, plus the ReXGlue source with its submodules.
  proprietary-data-closure =
    let
      closure = pkgs.closureInfo {
        rootPaths = [
          rexglue-sdk
          vulkan-probe
          iso-identify
          private-guard
          private-project
          address-compare
        ];
      };
    in
    pkgs.runCommand "proprietary-data-closure" { } ''
      set -euo pipefail
      mkdir -p "$out"
      # Written with cat, not cp: files copied from the store keep their read-only mode.
      cat ${closure}/store-paths > "$out/scanned-store-paths.txt"
      echo ${rexglue-src} >> "$out/scanned-store-paths.txt"
      ${python}/bin/python3 -I ${self}/tools/check_proprietary_data.py store \
        $(cat "$out/scanned-store-paths.txt") > "$out/report.txt"
      cat "$out/report.txt"
    '';
}

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

  # The CMake skeleton configures against the SDK package with the linux-amd64-release preset.
  cmake-skeleton =
    pkgs.llvmPackages_20.stdenv.mkDerivation {
      name = "fifa2010wc-cmake-skeleton";
      src = self;
      nativeBuildInputs = [
        pkgs.cmake
        pkgs.ninja
      ];
      buildInputs = [ rexglue-sdk ];
      dontUseCmakeConfigure = true;
      buildPhase = ''
        runHook preBuild
        cmake --preset linux-amd64-release 2>&1 | tee configure.log
        runHook postBuild
      '';
      installPhase = ''
        mkdir -p "$out"
        cp configure.log "$out/"
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

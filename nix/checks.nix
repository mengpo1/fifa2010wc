# Checks run by `nix flake check` (and by CI). None of them reads or needs game data.
{
  pkgs,
  self,
  rexglue-src,
  rexglue-sdk,
  vulkan-probe,
}:

let
  python = pkgs.python3;
in
{
  # The SDK itself: building it runs its unit tests (checkPhase in nix/rexglue-sdk.nix).
  inherit rexglue-sdk;

  # The same SDK built in Debug, for its tests: eight lock order tests run only in debug
  # builds (they SKIP under NDEBUG, as in the Release package above).
  rexglue-sdk-debug-tests = rexglue-sdk.overrideAttrs (_: {
    pname = "rexglue-sdk-debug-tests";
    cmakeBuildType = "Debug";
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
        found=0
        for f in "$sdk"/bin/* "$sdk"/lib/*.so*; do
          [ -f "$f" ] || continue
          file -L "$f" | grep -q ELF || continue
          found=$((found + 1))
          if "$interp" --list "$f" > deps.txt 2>&1; then :; fi
          if grep -q "not found" deps.txt; then
            echo "unresolved dependency in $f:" >&2
            grep "not found" deps.txt >&2
            exit 1
          fi
          # Lines read "libfoo.so.1 => /nix/store/.../libfoo.so.1 (0x...)": every resolved
          # path must be in the store, and so must a line that is a bare path (the loader).
          if grep -E '=> /' deps.txt | grep -vE '=> /nix/store/' ||
             grep -E '^\s*/' deps.txt | grep -vE '^\s*/nix/store/'; then
            echo "dependency outside the store in $f" >&2
            exit 1
          fi
        done
        echo "$found ELF files, every dependency resolved inside /nix/store" >> "$log"

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

  # D-007: no proprietary data among the tracked files of the repository.
  proprietary-data-source = pkgs.runCommand "proprietary-data-source" { } ''
    set -euo pipefail
    mkdir -p "$out"
    ${python}/bin/python3 -I ${self}/tools/test_check_proprietary_data.py > "$out/selftest.txt" 2>&1
    ${python}/bin/python3 -I ${self}/tools/check_proprietary_data.py tree ${self} > "$out/report.txt"
    cat "$out/report.txt"
  '';

  # D-007: no proprietary data in the store paths this flake builds or fetches: the runtime
  # closure of the SDK and of the Vulkan probe, plus the ReXGlue source with its submodules.
  proprietary-data-closure =
    let
      closure = pkgs.closureInfo {
        rootPaths = [
          rexglue-sdk
          vulkan-probe
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

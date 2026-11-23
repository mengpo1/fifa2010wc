# ReXGlue SDK built entirely from source (D-009, D-011).
#
# The source (`src`) is the flake input `rexglue-src`, pinned in flake.lock to the commit
# the upstream tag v0.11.0 points to, with every git submodule. Nothing is downloaded at
# build time: the build runs in the Nix sandbox without network access.
#
# The SDK's unit tests are built and run in checkPhase. Their CTest log and JUnit report
# are installed under share/rexglue-sdk/test-results, so a test result is never claimed
# without the run that produced it.
{
  lib,
  llvmPackages_20,
  src,
  # Build tools
  cmake,
  ninja,
  pkg-config,
  python3,
  wayland-scanner,
  autoPatchelfHook,
  # Graphics: the Vulkan Xenos driver module and SDL3's video backends
  vulkan-headers,
  vulkan-loader,
  vulkan-memory-allocator,
  libx11,
  libxcb,
  libxau,
  libxdmcp,
  libxext,
  libxscrnsaver,
  libxtst,
  libxi,
  libxrandr,
  libxcursor,
  libxfixes,
  libxinerama,
  libxrender,
  wayland,
  wayland-protocols,
  libxkbcommon,
  libdecor,
  # Audio: SDL3's backends
  alsa-lib,
  libpulseaudio,
  pipewire,
  # Desktop integration and input hotplug used by SDL3
  gtk3,
  dbus,
  systemdLibs,
}:

let
  # Libraries that SDL3 and the Vulkan driver open at run time with dlopen(). They get an
  # RPATH entry so the SDK runs on NixOS without nix-ld, steam-run or LD_LIBRARY_PATH.
  runtimeLibraries = [
    vulkan-loader
    libx11
    libxcb
    libxau
    libxdmcp
    libxext
    libxscrnsaver
    libxtst
    libxi
    libxrandr
    libxcursor
    libxfixes
    libxinerama
    libxrender
    wayland
    libxkbcommon
    libdecor
    alsa-lib
    libpulseaudio
    pipewire
    gtk3
    dbus
    systemdLibs
  ];
in
llvmPackages_20.stdenv.mkDerivation {
  pname = "rexglue-sdk";
  version = "0.11.0";

  inherit src;

  # Project patches on top of upstream v0.11.0 (D-011, docs/J2_A2_SDK_PATCHES.md). Each one
  # is a functional change with its own SDK unit tests, run in checkPhase below, and its
  # provenance in its header and in THIRD_PARTY.md (D-010). None of them touches XEX
  # loading or decryption (src/filesystem/xex.cpp, src/kernel/xex_module.cpp,
  # thirdparty/excrypt): O3 keeps the upstream decryption path unchanged (D-015).
  # nix flake check verifies it (sdk-patches).
  patches = [
    # 0003 in the project A numbering: configurable function table base (J2 step A3,
    # docs/J2_A3_FUNCTION_TABLE.md).
    ../patches/rexglue-sdk/0001-function-table-base.patch
  ];

  nativeBuildInputs = [
    cmake
    ninja
    pkg-config
    python3
    wayland-scanner
    autoPatchelfHook
  ];

  buildInputs = [
    vulkan-headers
    vulkan-memory-allocator
    wayland-protocols
  ] ++ runtimeLibraries;

  # dlopen() searches the RUNPATH of the library that calls it, such as the Vulkan driver
  # module (librexgpu-xenos-vulkan.so loads libvulkan.so.1). autoPatchelfHook adds
  # runtimeDependencies to executables only, and appendRunpaths to every ELF file it patches.
  appendRunpaths = map (pkg: "${lib.getLib pkg}/lib") runtimeLibraries;

  # SDL3 3.4 lists libsteam_api.so in its ELF dlopen notes, which autoPatchelfHook reads.
  # It is Valve's proprietary Steamworks library, loaded by SDL only for optional Steam
  # integration; SDL runs without it. The project must not depend on it.
  autoPatchelfIgnoreMissingDeps = [ "libsteam_api.so" ];

  # thirdparty/CMakeLists.txt checks that each vendored submodule is initialised by testing
  # for <submodule>/.git. The Nix git fetcher checks the submodules out (submodules=1) but
  # keeps no .git entries, so an empty .git folder is created for every path listed in the
  # upstream .gitmodules. A folder, not a file: SDL3's GetGitRevisionDescription.cmake
  # reads a .git file as a submodule pointer, while an empty .git folder without HEAD makes
  # it stop cleanly. git itself is not available to the build, so nothing runs git.
  postPatch = ''
    grep -E '^[[:space:]]*path[[:space:]]*=' .gitmodules | sed -E 's/^[^=]*=[[:space:]]*//' |
      while read -r submodule; do
        if [ ! -d "$submodule" ] || [ -z "$(ls -A "$submodule")" ]; then
          echo "submodule $submodule is missing from the source" >&2
          exit 1
        fi
        mkdir -p "$submodule/.git"
      done
  '';

  # The Nix cc-wrapper defines _FORTIFY_SOURCE; glibc then declares ftruncate() with
  # warn_unused_result, and ReXGlue builds with -Werror (src/base/mapped_memory_posix.cpp).
  # Found during the mission 001 audit (docs/audit/LINUX_FEASIBILITY.md §1.1).
  hardeningDisable = [
    "fortify"
    "fortify3"
  ];

  cmakeFlags = [
    # Same instruction set floor as the upstream linux-amd64 preset (CMakePresets.json).
    "-DCMAKE_C_FLAGS=-march=x86-64-v2"
    "-DCMAKE_CXX_FLAGS=-march=x86-64-v2"
    "-DREXGLUE_BUILD_TESTS=ON"
    # Never write to the user's CMake package registry from a build.
    "-DREXGLUE_REGISTER_PACKAGE=OFF"
    # On Linux x86_64 ReXGlue links every binary with lld through clang --ld-path, using the
    # first ld.lld found by find_program (cmake/rexglue_target.cmake). The plain lld
    # package bypasses the Nix linker wrapper, so the binaries got no RUNPATH entry for
    # libstdc++, X11 or Wayland. The wrapped ld.lld of llvmPackages_20.bintools adds them.
    "-DREXGLUE_LLD=${llvmPackages_20.bintools}/bin/ld.lld"
  ];

  doCheck = true;

  checkPhase = ''
    runHook preCheck
    # Libraries that SDL3 and the Vulkan driver open with dlopen() are added to the RUNPATH
    # of the installed files by autoPatchelfHook, in the fixup phase that comes after this
    # one. The test binaries stay in the build tree, so they get the same libraries here.
    export LD_LIBRARY_PATH="${lib.makeLibraryPath runtimeLibraries}"
    # Tests write temporary files and settings under HOME and XDG folders.
    export HOME="$TMPDIR/home"
    export XDG_RUNTIME_DIR="$TMPDIR/xdg-runtime"
    mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"
    mkdir -p "$NIX_BUILD_TOP/test-results"
    set -o pipefail
    ctest --output-on-failure --no-tests=error -j "$NIX_BUILD_CORES" \
      --output-junit "$NIX_BUILD_TOP/test-results/ctest-junit.xml" \
      2>&1 | tee "$NIX_BUILD_TOP/test-results/ctest.log"
    runHook postCheck
  '';

  postInstall = ''
    mkdir -p "$out/share/rexglue-sdk/test-results"
    cp "$NIX_BUILD_TOP"/test-results/* "$out/share/rexglue-sdk/test-results/"
  '';

  meta = {
    description = "ReXGlue: Xbox 360 recompilation runtime and toolkit (SDK built from source)";
    homepage = "https://github.com/rexglue/rexglue-sdk";
    license = lib.licenses.bsd3;
    platforms = [ "x86_64-linux" ];
    mainProgram = "rexglue";
  };
}

{
  description = "fifa2010wc: native Linux build infrastructure (milestone J1, no game data)";

  inputs = {
    # NixOS 26.05 channel release 26.05.14894.ab5c18fdedfc (nixpkgs ab5c18fdedfc8f9bbc9d773f10a540790e2787a7),
    # the release evaluated during the mission 001 audit. The releases.nixos.org URL is
    # immutable; flake.lock records its narHash.
    nixpkgs.url = "https://releases.nixos.org/nixos/26.05/nixos-26.05.14894.ab5c18fdedfc/nixexprs.tar.xz";

    # ReXGlue SDK v0.11.0 (D-011): the commit the upstream tag points to, with its submodules.
    rexglue-src = {
      url = "git+https://github.com/rexglue/rexglue-sdk?ref=refs/tags/v0.11.0&rev=a3e1d82678ca20d68d4837a8e9ee4652ff073745&submodules=1&shallow=1";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      rexglue-src,
    }:
    let
      # J1 targets Linux x86_64 only (D-001). aarch64-darwin is added at J6.
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      rexglue-sdk = pkgs.callPackage ./nix/rexglue-sdk.nix { src = rexglue-src; };

      # C1.4: lists the Vulkan devices that the Vulkan loader of this nixpkgs finds, with
      # the features ReXGlue's Vulkan driver requires. On NixOS the drivers come from
      # /run/opengl-driver (hardware.graphics.enable = true).
      vulkan-probe = pkgs.writeShellApplication {
        name = "fifa2010wc-vulkan-probe";
        runtimeInputs = [
          pkgs.vulkan-tools
          pkgs.python3
        ];
        text = ''exec python3 -I ${./tools/vulkan_probe.py} "$@"'';
      };
    in
    {
      packages.${system} = {
        inherit rexglue-sdk vulkan-probe;
        default = rexglue-sdk;
      };

      apps.${system}.vulkan-probe = {
        type = "app";
        program = "${vulkan-probe}/bin/fifa2010wc-vulkan-probe";
        meta.description = "List Vulkan devices and the features ReXGlue requires";
      };

      checks.${system} = import ./nix/checks.nix {
        inherit
          pkgs
          self
          rexglue-src
          rexglue-sdk
          vulkan-probe
          ;
      };

      # Development shell for the project and, from J2, the impure build of the game from
      # the user's private files (docs/audit/LINUX_FEASIBILITY.md §5.2): nothing derived
      # from the game enters the store.
      devShells.${system}.default = (pkgs.mkShell.override { stdenv = pkgs.llvmPackages_20.stdenv; }) {
        packages = [
          pkgs.cmake
          pkgs.ninja
          pkgs.python3
          pkgs.git
          pkgs.vulkan-tools
        ];
        # The wrapped ld.lld (see nix/rexglue-sdk.nix): from J2, pass it to CMake with
        # -DREXGLUE_LLD=$REXGLUE_LLD so that the host executable gets its RUNPATH entries.
        REXGLUE_LLD = "${pkgs.llvmPackages_20.bintools}/bin/ld.lld";
        # Puts the SDK package on CMAKE_PREFIX_PATH for find_package(rexglue).
        buildInputs = [ rexglue-sdk ];
        # Same reason as for the SDK build (nix/rexglue-sdk.nix): ReXGlue builds with -Werror.
        hardeningDisable = [
          "fortify"
          "fortify3"
        ];
        shellHook = ''
          echo "fifa2010wc dev shell: ReXGlue SDK ${rexglue-sdk.version} at ${rexglue-sdk}"
          if [ "$(git config --get core.hooksPath 2>/dev/null)" != ".githooks" ]; then
            echo "Enable the proprietary data check before each commit: git config core.hooksPath .githooks"
          fi
        '';
      };
    };
}

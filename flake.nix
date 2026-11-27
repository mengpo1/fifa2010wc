{
  description = "fifa2010wc: native Linux build infrastructure (J1) and disc identification (J0), no game data";

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

      # J0: identifies the user's disc image from its plaintext metadata, without
      # decrypting or extracting anything (docs/J0_ISO_IDENTIFICATION.md). The image is a
      # run time argument: it is opened in place and never enters the store.
      iso-identify = pkgs.writeShellApplication {
        name = "fifa2010wc-iso-identify";
        runtimeInputs = [ pkgs.python3 ];
        text = ''exec python3 -I ${./tools/iso_identify.py} "$@"'';
      };

      # J2, step A4: the CP-1 and CP-4 controls run before and after every phase B step on
      # the user's private files (docs/J2_PHASE_B_CONTROLS.md). It reads paths, modes and
      # timestamps only, and is run on the user's machine; the private folder is a run time
      # argument and never enters the store.
      private-guard = pkgs.writeShellApplication {
        name = "fifa2010wc-private-guard";
        runtimeInputs = [
          pkgs.python3
          pkgs.git
        ];
        text = ''exec python3 -I ${./tools/private_guard.py} "$@"'';
      };

      # J2, step A5: sets up and checks the codegen project in the private folder from the
      # manifest template (docs/J2_A5_CONFIG_TEMPLATE.md). The template holds relative paths
      # and no game data; the private folder is a run time argument and never enters the
      # store. The guard and the template are given by path: in the store, the script is a
      # lone file.
      private-project = pkgs.writeShellApplication {
        name = "fifa2010wc-private-project";
        runtimeInputs = [
          pkgs.python3
          pkgs.git
        ];
        text = ''
          exec python3 -I ${./tools/private_project.py} \
            --guard ${./tools/private_guard.py} \
            --template ${./config/private-template/wc2010_manifest.toml} "$@"
        '';
      };

      # J2, step A8-bis: compares ReXGlue address lists and diagnostics with configured
      # entries (docs/J2_A8BIS_ADDRESS_COMPARE.md). Purely analytic; every path is a run
      # time argument inside the private folder, which never enters the store.
      address-compare = pkgs.writeShellApplication {
        name = "fifa2010wc-address-compare";
        runtimeInputs = [ pkgs.python3 ];
        text = ''exec python3 -I ${./tools/address_compare.py} "$@"'';
      };

      # J2, step B1 (ticket #32): the controlled extraction of the disc tree with
      # `rexglue vfs dump`, run by hand on the user's machine after PB-0
      # (docs/J2_B1_EXTRACTION.md). The SDK is a dependency, so building this command builds
      # the SDK first, before any control starts. The extraction runs in a bubblewrap sandbox,
      # without privileges: no network, and writes only in its destinations. The disc image
      # and the private folder are run time arguments and never enter the store. `nix` and
      # `coredumpctl` come from the user's system, so that they match its daemon and its
      # journal.
      b1-tool = ./tools/b1_extract.py;
      # The only part of the store the sandbox of B1 shows (owner's arbitration on PR #33,
      # D-019): the closure of what runs inside it, Python, the SDK and the tool, as Nix
      # computes it at build time from the references of these paths. No list is kept by
      # hand. `store-paths` lists the paths, `registration` holds their references.
      b1-closure = pkgs.closureInfo {
        rootPaths = [
          pkgs.python3
          rexglue-sdk
          b1-tool
        ];
      };
      b1-extract = pkgs.writeShellApplication {
        name = "fifa2010wc-b1-extract";
        runtimeInputs = [
          pkgs.python3
          pkgs.git
          pkgs.findutils
          pkgs.util-linux
          pkgs.bubblewrap
        ];
        text = ''
          exec python3 -I ${b1-tool} \
            --guard ${./tools/private_guard.py} --sdk ${rexglue-sdk} \
            --store-closure ${b1-closure} "$@"
        '';
      };

      # J2, step B2 (docs/J2_B2_COMPATIBILITY.md): the compatibility check, a first
      # `rexglue codegen` of the two modules extracted at B1. A profile of the same engine
      # (docs/J2_LOCAL_STEP_ENGINE.md): what runs in the sandbox is the same, Python, the
      # SDK and the engine, so the sandbox shows the same store closure (D-019). The B2
      # profile, private_project.py and address_compare.py run outside it.
      b2-codegen = pkgs.writeShellApplication {
        name = "fifa2010wc-b2-codegen";
        runtimeInputs = [
          pkgs.python3
          pkgs.git
          pkgs.findutils
          pkgs.util-linux
          pkgs.bubblewrap
        ];
        text = ''
          exec python3 -I ${./tools/b2_codegen.py} --engine ${b1-tool} \
            --address-compare ${./tools/address_compare.py} \
            --private-project ${./tools/private_project.py} \
            --guard ${./tools/private_guard.py} --sdk ${rexglue-sdk} \
            --store-closure ${b1-closure} "$@"
        '';
      };
    in
    {
      packages.${system} = {
        inherit
          rexglue-sdk
          vulkan-probe
          iso-identify
          private-guard
          private-project
          address-compare
          b1-extract
          b2-codegen
          ;
        default = rexglue-sdk;
      };

      apps.${system} = {
        vulkan-probe = {
          type = "app";
          program = "${vulkan-probe}/bin/fifa2010wc-vulkan-probe";
          meta.description = "List Vulkan devices and the features ReXGlue requires";
        };
        iso-identify = {
          type = "app";
          program = "${iso-identify}/bin/fifa2010wc-iso-identify";
          meta.description = "Identify the disc image from its plaintext metadata (J0)";
        };
        private-guard = {
          type = "app";
          program = "${private-guard}/bin/fifa2010wc-private-guard";
          meta.description = "CP-1 and CP-4 controls around phase B steps (J2)";
        };
        private-project = {
          type = "app";
          program = "${private-project}/bin/fifa2010wc-private-project";
          meta.description = "Set up and check the codegen project in the private folder (J2)";
        };
        address-compare = {
          type = "app";
          program = "${address-compare}/bin/fifa2010wc-address-compare";
          meta.description = "Compare ReXGlue address lists with configured entries (J2)";
        };
        b1-extract = {
          type = "app";
          program = "${b1-extract}/bin/fifa2010wc-b1-extract";
          meta.description = "Controlled extraction of the disc tree, step B1 (J2)";
        };
        b2-codegen = {
          type = "app";
          program = "${b2-codegen}/bin/fifa2010wc-b2-codegen";
          meta.description = "Compatibility check, a first rexglue codegen, step B2 (J2)";
        };
      };

      checks.${system} = import ./nix/checks.nix {
        inherit
          pkgs
          self
          rexglue-src
          rexglue-sdk
          vulkan-probe
          iso-identify
          private-guard
          private-project
          address-compare
          b1-extract
          b1-closure
          b2-codegen
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
        # The wrapped ld.lld (see nix/rexglue-sdk.nix), so that the host executable gets its
        # RUNPATH entries. The presets of CMakePresets.json pass it to CMake. CMakeLists.txt
        # stops when it is missing, when the cache differs, or when a probe it links does not
        # start without LD_LIBRARY_PATH: this shell keeps the PATH of the machine, where
        # another ld.lld can come first (J2 step A7, docs/J2_A7_SYNTHETIC_CHAIN.md §5).
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

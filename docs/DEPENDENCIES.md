# Dépendances du projet (jalon J1)

> Toute dépendance est identifiée, justifiée et épinglée (mission 002).
> Rien ici ne provient du jeu. Les versions ont été lues par évaluation du `flake.lock` du
> dépôt le 2026-11-21.

## 1. Entrées épinglées dans `flake.lock`

| Entrée | Source | Épinglage | Justification |
|---|---|---|---|
| `nixpkgs` | `https://releases.nixos.org/nixos/26.05/nixos-26.05.14894.ab5c18fdedfc/nixexprs.tar.xz` | Révision `ab5c18fdedfc8f9bbc9d773f10a540790e2787a7`, narHash `sha256-xVwloUjz7paCDnvN5dkrasmAGV+O6uyRUPFHxv2w3VA=` | Plateforme cible NixOS 26.05 (D-001) ; même publication que celle évaluée pendant l'audit. L'URL de `releases.nixos.org` est immuable. |
| `rexglue-src` | `git+https://github.com/rexglue/rexglue-sdk`, étiquette `v0.11.0`, avec sous-modules | Révision `a3e1d82678ca20d68d4837a8e9ee4652ff073745`, narHash `sha256-uSyEi0ou+ixZCd7pjOrvfkVy8mSly1ys5Tev6xjdCQ0=` | Recompilateur et runtime retenus (D-002, D-011). C'est le commit de l'étiquette ; le commit de fusion `ebac1cf` de `main` a le même arbre. |

## 2. Sous-modules de ReXGlue v0.11.0

Ils sont épinglés par les gitlinks du commit `a3e1d82` et couverts par le narHash de
`rexglue-src`. Le SDK les compile lui-même (sources vendues) ; aucun n'est remplacé par
une version de nixpkgs.

| Sous-module | Commit |
|---|---|
| FFmpeg (fork `wmarti/FFmpeg`, décodage XMA) | `0604b464c7cb4ebc94940cf1f324a3b26b87717c` |
| catch2 (tests) | `88abf9bf325c798c33f54f6b9220ef885b267f4f` |
| cli11 | `bfffd37e1f804ca4fae1caae106935791696b6a9` |
| excrypt | `088094585aee1694cdeef9a9330d29d14aef9203` |
| glslang | `f4f1d8a352ca1908943aea2ad8c54b39b4879080` |
| imgui | `6d910d5487d11ca567b61c7824b0c78c569d62f0` |
| inja | `7d1b4600b68595085a949743331c2e5673f511ea` |
| libmspack | `305907723a4e7ab2018e58040059ffb5e77db837` |
| sdl3 | `147a8ee32dbf9ac02f3794964490687b6bbda1bc` |
| simde | `71fd833d9666141edcd1d3c109a80e228303d8d7` |
| spdlog | `79524ddd08a4ec981b7fea76afd08ee05f83755d` |
| tlsf | `deff9ab509341f264addbd3c8ada533678591905` |
| tomlplusplus | `30172438cee64926dc41fdd9c11fb3ba5b2ba9de` |
| tracy | `05cceee0df3b8d7c6fa87e9638af311dbabc63cb` |
| xxHash | `e626a72bc2321cd320e953a0ccf1584cad60f363` |

Remarque : `excrypt` fournit l'AES avec lequel ReXGlue déchiffre les XEX. Il est compilé
dans le SDK, avec les clés maîtresses intégrées dans `src/filesystem/xex.cpp`
(`docs/D-008_DECISION_NOTE.md` §3.4). **Aucun déchiffrement n'est exécuté à J1** : aucun
XEX n'est fourni, et ni les tests ni les contrôles ne lisent de fichier du jeu. À J1,
D-008 était ouverte. Depuis le 2026-11-22, O3 est retenue : ce SDK est le seul moyen de
déchiffrement du projet. J2 est autorisé depuis le 2026-11-23 (D-015), mais aucun XEX
n'est traité avant PB-0, et jamais en CI.

## 3. Paquets nixpkgs (révision `ab5c18f`)

### Compilation du SDK (`nix/rexglue-sdk.nix`)

| Paquet | Version | Rôle |
|---|---|---|
| `llvmPackages_20.stdenv` (clang) | 20.1.8 | Compilateur imposé par ReXGlue v0.11.0 (Clang ≥ 20, D-005) |
| `llvmPackages_20.lld` | 20.1.8 | Éditeur de liens des binaires en modèle de code `large` |
| libstdc++ (GCC) | 15.3.0 | Bibliothèque C++ standard, la même pour le SDK et le projet (§5.2 de LINUX_FEASIBILITY) |
| `glibc` | 2.42 | Bibliothèque C, interpréteur ELF dans `/nix/store` |
| `cmake` | 4.1.6 | Construction (CMake ≥ 3.25) |
| `ninja` | 1.13.2 | Générateur |
| `pkg-config` | 0.29.2 | Détection des bibliothèques par SDL3 |
| `python3` | 3.13.18 | Scripts de construction du SDK, contrôles du projet, outil d'identification de J0 (`iso-identify`, bibliothèque standard seulement) |
| `wayland-scanner` | 1.25.0 | Génération des protocoles Wayland pour SDL3 |
| `autoPatchelfHook` | (nixpkgs) | Ajoute au RUNPATH les bibliothèques liées et celles chargées par `dlopen` |
| `vulkan-headers` | 1.4.341.0 | En-têtes du pilote Vulkan Xenos |
| `vulkan-memory-allocator` | 3.3.0 | Allocation mémoire du pilote Vulkan (en-têtes) |
| `wayland-protocols` | 1.48 | Protocoles Wayland (SDL3) |

### Bibliothèques d'exécution (liées ou ouvertes par `dlopen`, ajoutées au RUNPATH)

| Paquet | Version | Rôle |
|---|---|---|
| `vulkan-loader` | 1.4.341.0 | Chargeur Vulkan (ICD du système sous NixOS : `/run/opengl-driver`) |
| `libx11`, `libxcb`, `libxau`, `libxdmcp`, `libxext`, `libxscrnsaver`, `libxtst`, `libxi`, `libxrandr`, `libxcursor`, `libxfixes`, `libxinerama`, `libxrender` | 1.8.14, 1.17.0, 1.0.12, 1.1.5, 1.3.7, 1.2.5, 1.2.6, 1.8.4, 1.5.5, 1.2.3, 6.0.2, 1.1.6, 0.9.13 | Fenêtrage X11 (SDL3, pilote Vulkan). `libxtst` et les suivants sont exigés par la configuration de SDL3 ; `libxau` et `libxdmcp` par `xcb.pc` |
| `wayland`, `libxkbcommon`, `libdecor` | 1.25.0, 1.13.1, 0.2.5 | Fenêtrage Wayland (SDL3, pilote Vulkan) |
| `alsa-lib`, `libpulseaudio`, `pipewire` | 1.2.15.3, 17.0, 1.6.6 | Sorties audio de SDL3 |
| `gtk3` | 3.24.52 | Dialogues de fichiers et boîtes de message de SDL3 |
| `dbus` | 1.16.2 | Intégration bureau de SDL3 |
| `systemdLibs` (libudev) | 260.5 | Détection à chaud des manettes par SDL3 |

### Contrôles, environnement de développement, sonde

| Paquet | Version | Rôle |
|---|---|---|
| `patchelf`, `file` | 0.15.2, 5.47 | Vérification de l'interpréteur ELF et du RUNPATH (`rexglue-cli-runs`) |
| `git` | 2.54.0 | Environnement de développement |
| `vulkan-tools` (`vulkaninfo`) | 1.4.341.0 | Sonde Vulkan (C1.4), même version que le chargeur du SDK |
| `mesa` (lavapipe) | 26.1.8 | **Non utilisé par le projet** ; seulement pour valider la sonde pendant J1, sans GPU |

## 4. Intégration continue (`.github/workflows/ci.yml`)

| Dépendance | Épinglage | Rôle |
|---|---|---|
| `actions/checkout` v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` | Récupération du dépôt |
| `cachix/install-nix-action` v32.0.0 | `bb0495a1086c46893eee56f32fd192dfe4a15bb9` | Installation de Nix |
| Nix | 2.34.6 (`https://releases.nixos.org/nix/nix-2.34.6/install`) | Même version que l'environnement de J1 |
| `actions/upload-artifact` v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` | Publication des preuves (journaux des tests, rapports) |
| Machine `ubuntu-24.04` | Image GitHub, version non épinglable | Hôte de Nix seulement : la compilation n'utilise que `/nix/store` |

## 5. Ce qui n'est pas une dépendance

- Aucun SDK précompilé, ni `nix-ld`, ni `steam-run`, ni bibliothèque du système hôte.
- Aucun service réseau pendant la compilation (bac à sable Nix sans réseau).
- Aucun fichier du jeu.

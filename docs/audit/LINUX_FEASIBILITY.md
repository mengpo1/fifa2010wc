# Audit — Faisabilité d'un portage natif Linux (NixOS 26.05, x86_64)

> Mission 001, révision « Linux prioritaire » — audit du 2026-11-21.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.
> Plateforme cible : Linux x86_64 sous NixOS 26.05. macOS ARM64 est une plateforme
> secondaire future : l'architecture la prévoit (§6), sans aucun travail avant qu'une
> version Linux ne soit jouable.

## Verdict

**Faisable, avec un risque concentré sur le rendu Vulkan et la maturité du runtime pour
ce jeu, et non sur des API Windows à réécrire.** L'outil sur lequel reposent les deux
ports existants, ReXGlue, compile sous Linux x86_64 depuis les sources avec la chaîne
de nixos-26.05 (vérifié pendant l'audit, §1.1). Il fournit déjà des pilotes Vulkan,
SDL3 audio et SDL3 entrées. Le jeu lui-même ne dépend pas de Direct3D ni de XAudio2
pour Windows : il parle au matériel Xbox 360, que le runtime émule sur l'hôte (§2). Le
code propre à Windows des ports existants se limite à leur couche applicative : environ
300 lignes pour le projet A, plus son lanceur.

Le blocage principal n'est pas technique : c'est la décision D-008 sur le déchiffrement
des XEX (`ISO_REQUIREMENTS.md` §5).

---

## 1. Compilation Linux x86_64 des outils de recompilation

### 1.1 ReXGlue

**Faits vérifiés sur le dépôt (v0.11.0, `ebac1cf`, même arbre que l'étiquette `v0.11.0` = `a3e1d82`, 2026-11-14)**

- **[V]** CI de publication `linux-amd64` (Ubuntu 24.04) et `linux-arm64`, en plus de
  Windows et macOS (`.github/workflows/_build-platform.yaml`).
- **[V]** Clang obligatoire, en version ≥ 20 (erreur CMake bloquante sinon). Les commits
  épinglés par les projets A et B exigeaient Clang ≥ 18.
- **[V]** Sous Linux x86_64, modèle de code `large` (`-mcmodel=large`) et édition de
  liens par lld, pour les exécutables recompilés de plus de 35 Mo
  (`cmake/rexglue_target.cmake`).
- **[V]** Préréglages CMake `linux-amd64`, `linux-arm64` et `linux-amd64-tsan` ;
  générateur Ninja Multi-Config.
- **[V]** Dépendances système déclarées par la CI Linux : GTK3, X11-xcb, XScrnSaver,
  Wayland et ses protocoles, xkbcommon, libdecor, ALSA, PulseAudio, PipeWire, ainsi que le
  SDK Vulkan de LunarG (en-têtes et VMA).

**Faits vérifiés sur le SDK précompilé `rexglue-sdk-0.11.0-linux-amd64.zip`**
(127,7 Mo, SHA-256 `e7d543ab8dde2c7839836a0417bfe84691c10f93357ec2c023fa98d3d315803b`),
inspecté statiquement sans exécution :

- **[V]** Outil `bin/rexglue` : ELF 64 bits x86-64, qui exige GLIBC 2.38 et la libstdc++
  de GCC.
- **[V]** Modules de pilotes livrés : `librexgpu-xenos-vulkan`, `librexgpu-xenos-null`,
  `librexapu-sdl3`, `librexhid-sdl3` et `librexui-sdl3`. Il n'y a **aucun pilote D3D12** ;
  les variantes Debug et RelWithDebInfo sont incluses.
- **[V]** `librexgpu-xenos-vulkan` est lié directement à X11, X11-xcb, xcb et
  wayland-client. `libSDL3.so.0` ne déclare que libc et libm, et charge le reste par
  `dlopen` : `libvulkan.so.1`, `libwayland-*`, `libxkbcommon`, `libdecor-0`,
  `libasound`, `libpulse`, `libgtk-3`, `libdbus-1`, entre autres. Point crucial pour
  NixOS (§5).

**Compilation depuis les sources pendant l'audit**

Environnement : conteneur Ubuntu 24.04 x86_64, 4 cœurs, avec la chaîne **Nix** du canal
`nixos-26.05` (version `26.05.14894.ab5c18fdedfc`) : clang 20.1.8 (`llvmPackages_20.stdenv`),
lld 20, CMake 4.1.6, Ninja, libstdc++ de GCC 15.3, vulkan-headers, vulkan-loader et
vulkan-memory-allocator. Sources v0.11.0 avec sous-modules ; options
`-DCMAKE_BUILD_TYPE=Release -DREXGLUE_BUILD_TESTS=OFF -march=x86-64-v2`.

| Essai | Résultat | Cause, correction |
|---|---|---|
| 1 | Échec à la configuration | SDL3 : « Couldn't find dependency package for XTEST ». Sous Ubuntu, libXtst arrive avec `libgtk-3-dev` ; sous Nix, il faut lister libxtst, libxi, libxrandr, libxcursor, libxfixes, libxinerama et libxrender **[V]** |
| 2 | Configuration réussie, compilation en échec (`mapped_memory_posix.cpp:85`) | Le durcissement `fortify`/`fortify3` du compilateur enveloppé par Nix définit `_FORTIFY_SOURCE` ; glibc marque alors `ftruncate` « warn_unused_result », et le `-Werror` de ReXGlue en fait une erreur **[V]** |
| 3 | `hardeningDisable = [ "fortify" "fortify3" ]`, recompilation propre (l'en-tête précompilé doit être reconstruit) | **Succès** : configuration, 1 051 étapes et installation sans erreur, en 3 min 44 s au total sur 4 cœurs **[V]** |

Produits de l'essai 3 (inspection statique) :

- **[V]** Installation de 47 Mo : `bin/rexglue` (ELF x86-64), 24 bibliothèques dans
  `lib64/`, dont les pilotes `librexgpu-xenos-vulkan.so`, `librexgpu-xenos-null.so`,
  `librexapu-sdl3.so`, `librexhid-sdl3.so` et `librexui-sdl3.so`, ainsi que la copie de
  SDL 3.4.14 compilée par le SDK.
- **[V]** Le RUNPATH des binaires ne contient que `$ORIGIN`, `$ORIGIN/../lib64` et un
  chemin propre à `nix-shell`. Il ne référence **ni** X11, **ni** Wayland, **ni**
  libstdc++ dans `/nix/store`. Une compilation faite dans un `devShell` ne s'exécute donc
  pas telle quelle sous NixOS : il faut une dérivation avec correction du rpath
  (`autoPatchelfHook`) ou une enveloppe (§5.2).
- **[V]** `cmake_minimum_required(VERSION 2.8.12)` de glslang ne bloque pas avec CMake
  4.1.6 : seul un avertissement « dev » apparaît.
- **[V]** Aucune modification des sources de ReXGlue n'a été nécessaire ; seul
  l'environnement de compilation a été ajusté.
- **[I]** Fonctionnement à l'exécution sur NixOS : l'outil compilé n'a pas été lancé
  pendant l'audit. Les tests unitaires du SDK (`REXGLUE_BUILD_TESTS=ON`) n'ont pas été
  compilés.

### 1.2 XenonRecomp

- **[V]** Compilé pendant l'audit sous Linux x86_64 avec clang 18.1.3 (Ubuntu), CMake
  3.28 et Ninja : 34 étapes, 7 s, binaires `XenonRecomp` (1,1 Mo) et `XenonAnalyse`
  (0,6 Mo) produits, sans erreur.
- **[V]** Le code généré cible x86 (intrinsèques) et passe par SIMDe pour ARM64 (README).
- **[V]** **Pas de runtime.** Utiliser XenonRecomp imposerait d'écrire le noyau
  Xbox 360, XAM, le GPU Xenos, l'APU XMA et le système de fichiers, soit ce que ReXGlue
  hérite de Xenia. Unleashed Recompiled l'a fait pour un seul jeu, en remplaçant le
  rendu par une réimplémentation de haut niveau ; ce projet est sous GPL-3.0.
- **Conclusion [H]** : XenonRecomp n'est pas une base réaliste pour FIFA World Cup 2010
  dans un délai raisonnable. Il reste utile comme référence (analyse, tables de sauts).

## 2. Dépendances Windows et services Xbox 360

### 2.1 Distinction essentielle

- **[V]** Le jeu Xbox 360 n'appelle ni Direct3D ni XAudio2 pour Windows. Il intègre les
  bibliothèques de la console, qui écrivent des paquets PM4 dans le tampon circulaire du
  GPU Xenos (documentation ReXGlue `devices/graphics.md`) et enregistrent des clients
  de rendu audio auprès du noyau (`XAudioRegisterRenderDriverClient`,
  `devices/audio.md`).
- **[V]** Le « Direct3D 12 » des ports existants est donc **le backend hôte** qui exécute
  ce flux PM4 sur le PC. Ce n'est pas une dépendance du code recompilé.

### 2.2 Inventaire

| Domaine | Ports actuels (Windows) | ReXGlue v0.11.0 sous Linux | Statut |
|---|---|---|---|
| GPU (flux Xenos) | Pilote `d3d12` | Pilote `vulkan`, choisi par défaut hors Windows ; pilote `null` pour les tests sans GPU | [V] |
| Présentation et fenêtre | D3D12 et SDL3 | Vulkan et SDL3 (X11 ou Wayland) | [V] |
| Audio hôte | SDL3 | SDL3 (ALSA, PulseAudio ou PipeWire via SDL) | [V] |
| Décodage XMA | FFmpeg (copie Xenia) | Identique, code portable | [V] |
| Entrées | SDL3 (par défaut) + XInput (option Windows) | SDL3 ; clavier et souris via les événements de fenêtre | [V] |
| Noyau `xboxkrnl`, `xam`, `xbdm` | C++ du runtime | Identique ; les couches de base ont des variantes `_posix` (mémoire, exceptions, fibres, threads, horloge, sockets) | [V] |
| Caméra USB (exports importés par le jeu) | Correctif 0001 du projet A | `xboxkrnl_usbcam.cpp` présent | [V] |
| Xbox Live | Non fonctionnel | Non fonctionnel | [V] (projet A) |
| ISO comme racine du jeu | Correctif 0005 (projet A) | Non pris en charge : la racine doit être un dossier | [V] |
| Couche applicative (chemins, plantages, lanceur) | Win32 (`LOCALAPPDATA`, DbgHelp, `ShellExecuteW`, WPF) | À écrire : répertoires XDG, gestionnaire de signaux, CLI ou TOML | [V] constat, travail à faire |
| Construction | PowerShell, Visual Studio | CMake et Ninja ; Nix | À écrire |

### 2.3 Dépendances propres au jeu relevées

- **[V]** Deux modules XEX (`default.xex` et `fifadllzf.xex`), chargés à des adresses qui
  font se chevaucher les tables de répartition par défaut (correctif 0003 du projet A).
- **[V]** Lua embarqué : `setjmp`/`longjmp` du CRT à rediriger.
- **[V]** Un fil `MoviePlayer2 Decode Thread` et un dossier `data/movies/` (notes du
  projet B). **[H]** Les vidéos sont décodées en logiciel par le jeu : aucun codec hôte
  n'est à prévoir.
- **[V]** Exports de la caméra USB (Xbox Live Vision) importés.
- **[I]** Liste complète des bibliothèques importées : elle s'obtient à J0 en lisant
  l'en-tête *import libraries*, en clair (`ISO_REQUIREMENTS.md` §3, étape 5).

## 3. Faisabilité du backend Vulkan

**Faits vérifiés**

- **[V]** Backend complet dans `src/gpu/xenos/vulkan` (environ 23 200 lignes) et
  `src/gpu/xenos/host/vulkan`, à parité de structure avec D3D12 : cache de pipelines,
  cache de cibles de rendu, cache de textures, mémoire partagée, tessellation.
- **[V]** Il partage avec D3D12 la base `XenosGraphicsDriverBase` : processeur de
  commandes PM4, fils `GPU Commands` et `GPU VSync`, cache de shaders.
- **[V]** Il existe déjà dans les commits épinglés par les deux projets
  (`src/graphics/vulkan`). Le projet B a même modifié des fichiers du présentateur
  Vulkan.
- **[V]** Les deux réglages GPU propres à FIFA y sont pris en charge.
- **[V]** Fonctionnalités Vulkan obligatoires : `independentBlend`,
  `fragmentStoresAndAtomics` et `vertexPipelineStoresAndAtomics`. Les geometry shaders
  et `fillModeNonSolid` sont facultatifs ; sans eux, des chemins de repli sont utilisés
  (`vulkan_device.cpp`, `command_processor.cpp`).
- **[V]** Deux chemins de cibles de rendu : `fsi` (fragment shader interlock,
  l'équivalent des ROV de D3D12) et cibles de rendu hôtes.

**Hypothèses**

- **[H]** Les GPU de bureau récents sous Linux (Mesa RADV ou ANV, NVIDIA propriétaire)
  satisfont les fonctionnalités obligatoires.
- **[H]** La parité visuelle avec D3D12 n'est pas garantie pour ce jeu : réglages
  d'échelle interne, « readbacks » et post-traitement ont demandé des ajustements au
  projet B sous D3D12, et rien de cela n'a été validé sous Vulkan.

**Inconnues**

- **[I]** Rendu de FIFA World Cup 2010 sous Vulkan : aucun essai connu.
- **[I]** Chemin de cibles de rendu le plus fidèle pour ce jeu.

**Conclusion** : il n'y a **pas de backend Vulkan à écrire**. Le travail consiste à
**valider et corriger** le backend existant pour ce jeu. Écrire notre propre
abstraction graphique au-dessus de Vulkan serait redondant : l'abstraction existe déjà
(`IGraphicsDriver` et modules de pilotes).

## 4. Runtime sous Linux

- **[V]** Linux x86_64 utilise des pages de 4 Kio : la vue physique est projetée à
  `0x1000` sans correction dans le code généré (`runtime/memory.md`).
- **[V]** Gestion des exceptions par signaux (`exception_handler_posix.cpp`), fibres
  POSIX, verrou d'instance, journaux, relance, ressources de processus : tout existe
  en variante POSIX.
- **[H]** La cadence vblank sous Linux sera plus fine que sous Windows, où le
  `Sleep(1)` peut dormir environ 15,6 ms. Le correctif 0004 serait alors moins
  nécessaire.
- **[I]** Comportement du gestionnaire de signaux face aux accès invalides que la console
  tolère (cas corrigé par `boot_fixes.cpp` sous Windows).

## 5. Adaptations nécessaires pour NixOS

### 5.1 Disponibilité dans nixos-26.05 (évaluée pendant l'audit)

| Composant | Paquet | Version |
|---|---|---|
| Compilateur | `clang_20`, `llvmPackages_20`, `lld_20` | 20.1.8 [V] |
| Construction | `cmake`, `ninja`, `pkg-config` | 4.1.6, 1.13.2, 0.29.2 [V] |
| Vulkan | `vulkan-headers`, `vulkan-loader`, `vulkan-memory-allocator`, `vulkan-validation-layers`, `vulkan-tools` | 1.4.341.0 (VMA 3.3.0) [V] |
| SDL | `sdl3` | 3.4.10 [V] (ReXGlue embarque sa propre copie de SDL 3.4) |
| Fenêtrage | `wayland`, `wayland-protocols`, `libxkbcommon`, `libdecor`, `libx11`, `libxcb` | 1.25.0, 1.48, 1.13.1, 0.2.5, 1.8.14, 1.17.0 [V] |
| Audio | `pipewire`, `libpulseaudio`, `alsa-lib` | 1.6.6, 17.0, 1.2.15.3 [V] |
| GTK | `gtk3` | 3.24.52 [V] |
| ISO | `extract-xiso`, `xdvdfs-cli` | 202505152050, 0.8.3 [V] |
| Débogage | `renderdoc`, `gamescope` | 1.44, 3.16.23 [V] |
| Exécution de binaires étrangers | `nix-ld`, `steam-run`, `patchelf` | 2.0.6, 1.0.0.85, 0.15.2 [V] |
| Pilotes | `mesa` | 26.1.8 [V] |

Remarque **[V]** : l'espace de noms `xorg.*` a disparu dans 26.05 (`xorg.libX11`
absent). Les paquets X11 portent désormais des noms à plat (`libx11`, `libxtst`…).

### 5.2 Adaptations identifiées

1. **Compiler le SDK depuis les sources, ne pas utiliser le SDK précompilé.** [V] Le
   paquet précompilé suppose une libstdc++ de GCC 13 et des bibliothèques à des chemins
   FHS ; la documentation demande `--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/13`,
   un chemin qui n'existe pas sous NixOS. Une compilation complète par
   `llvmPackages_20.stdenv` utilise une libstdc++ cohérente pour le SDK et le jeu.
2. **Lister explicitement les bibliothèques X11** exigées par SDL3 [V] (§1.1, essai 1).
3. **Régler le durcissement** [V] : désactiver `fortify`/`fortify3`, ou bien ajouter
   `-Wno-error=unused-result`, ou corriger la ligne en amont. **[H]** Évaluer aussi
   `zerocallusedregs` et `stackclashprotection` sur le code recompilé (performances).
4. **Bibliothèques liées et chargées par `dlopen`** [V] : le RUNPATH produit dans un
   `devShell` ne couvre pas les dépendances (§1.1, essai 3). Il faut les fournir à
   l'exécution, par une enveloppe (`makeWrapper --prefix LD_LIBRARY_PATH`) ou en
   corrigeant le rpath (`autoPatchelfHook`, `patchelf`) : libstdc++, X11, xcb,
   wayland, vulkan-loader, libxkbcommon, libdecor, alsa-lib, libpulseaudio, pipewire et
   dbus. Les ICD Vulkan viennent de `/run/opengl-driver`
   (`hardware.graphics.enable = true` dans la configuration NixOS) **[H]**.
5. **Sous-modules vendus** : la copie de FFmpeg (fork `wmarti/FFmpeg`, branche
   `xenia-ffmpeg-canary-full`), compilée par la CMake du SDK, n'est pas remplaçable par
   le `ffmpeg` de nixpkgs sans étude **[H]**. On utilisera
   `fetchgit { fetchSubmodules = true; }` en épinglant les révisions.
6. **Séparation pur/impur** :
   - *pur* (dérivation Nix, cache possible) : SDK ReXGlue, outil `rexglue`, outils
     d'analyse, tests unitaires du SDK ;
   - *impur* (dans le `devShell`, dossier privé local) : génération de code depuis les
     XEX, compilation et exécution du jeu. Rien de ce qui dérive du jeu n'entre dans
     `/nix/store` (`ISO_REQUIREMENTS.md` §1).
7. **Solution de secours** : `nix-ld` ou `steam-run` permettent de lancer le SDK
   précompilé pour comparer, mais ce n'est pas la voie retenue [V] (paquets disponibles).

### 5.3 Esquisse d'environnement (vérifiée sur la compilation du SDK)

```nix
# Environnement de compilation du SDK ReXGlue (audit, nixos-26.05)
(pkgs.mkShell.override { stdenv = pkgs.llvmPackages_20.stdenv; }) {
  hardeningDisable = [ "fortify" "fortify3" ];
  nativeBuildInputs = with pkgs; [ cmake ninja pkg-config python3 git
    llvmPackages_20.lld wayland-scanner ];
  buildInputs = with pkgs; [ vulkan-headers vulkan-loader vulkan-memory-allocator
    libx11 libxcb libxscrnsaver libxext libxtst libxi libxrandr libxcursor
    libxfixes libxinerama libxrender systemdLibs
    wayland wayland-protocols libxkbcommon libdecor
    alsa-lib libpulseaudio pipewire gtk3 dbus ];
}
```

Ce n'est pas encore un `flake.nix` de projet : il sera écrit au jalon J1 (D-009).

## 6. Architecture portable (Linux d'abord, macOS ARM64 ensuite)

### 6.1 Ce que ReXGlue apporte déjà

- **[V]** Abstractions par modules dynamiques : `IGraphicsDriver` (Vulkan, D3D12, null),
  `IAudioSystem` et son pilote SDL3, `IInputSystem` (SDL3, XInput), `IUISystem` (SDL3).
- **[V]** CI `mac-arm64`, pages de 16 Kio gérées (`REX_PHYS_HOST_OFFSET`),
  `VK_KHR_portability_subset` géré pour MoltenVK, SIMDe pour le vectoriel sur ARM64.

### 6.2 Couches proposées pour le projet

```
┌──────────────────────────────────────────────────────────────┐
│ app/          Application TitleApp portable (C++23)          │
│               chemins, configuration, réglages GPU du jeu    │
├──────────────────────────────────────────────────────────────┤
│ hooks/        Correctifs propres au jeu (C++ portable,       │
│               adresses invitées, aucune API système)         │
├──────────────────────────────────────────────────────────────┤
│ platform/     Seule couche dépendante du système :           │
│   common/     interfaces (DataDirs, CrashReporter, Dialogs)  │
│   linux/      XDG, signaux, journal (implémentation J1–J5)   │
│   macos/      bouchons tant que Linux n'est pas jouable      │
├──────────────────────────────────────────────────────────────┤
│ ReXGlue SDK (épinglé + série de correctifs)                  │
│   GPU : vulkan (Linux, puis MoltenVK) │ audio : sdl3         │
│   entrées : sdl3 │ fenêtre : sdl3 │ noyau, XAM, système de   │
│   fichiers : portables                                       │
├──────────────────────────────────────────────────────────────┤
│ generated/    C++ généré (privé, jamais versionné)           │
└──────────────────────────────────────────────────────────────┘
```

Règles de conception (D-006) :

1. Aucun `#include` système hors de `platform/<os>/`.
2. Aucun appel Vulkan, SDL ou POSIX direct dans `app/` et `hooks/`. Ces couches passent
   par les interfaces du SDK ou par `platform/common`.
3. Aucune hypothèse x86_64 (intrinsèques, `-mcmodel`, taille de page) dans le code du
   projet. Ces réglages restent dans la CMake du SDK et dans les préréglages.
4. Préréglages CMake `linux-amd64-*` maintenant ; `mac-arm64-*` seulement à J6.
5. Pas de lanceur graphique au premier jalon : configuration TOML et ligne de commande.

## 7. Synthèse des inconnues techniques

1. **[I]** Rendu du jeu sous Vulkan (R-03).
2. **[I]** Comportement du runtime Linux sur les accès invalides tolérés par la console.
3. **[I]** Correctifs du projet A encore nécessaires sur v0.11.0 (0002, 0004, 0007, 0008).
4. **[I]** Fonctionnement du SDK compilé sur NixOS à l'exécution (ICD, `dlopen`).

## Sources

- https://github.com/rexglue/rexglue-sdk (v0.11.0 : `CMakeLists.txt`, `CMakePresets.json`,
  `cmake/rexglue_target.cmake`, `.github/`, `docs/site/pages/`, `src/gpu/xenos/`)
- https://github.com/rexglue/rexglue-sdk/releases/tag/v0.11.0
- https://github.com/hedge-dev/XenonRecomp
- https://channels.nixos.org/nixos-26.05 (évaluation des paquets)
- https://github.com/CalinGraphics/fifa-world-cup-2010-recompiled
- https://github.com/RamiChaaben8/Fifa_World_Cup_2010_PC_Port

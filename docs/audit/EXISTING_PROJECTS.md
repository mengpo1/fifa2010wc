# Audit — Projets existants de portage de *2010 FIFA World Cup South Africa*

> Mission 001, révision « Linux prioritaire » — audit du 2026-11-21.
> Ce document remplace la version de la mission initiale. Les documents de cette
> mission initiale n'ont été trouvés dans aucun des dépôts accessibles (ce dépôt était
> vide au moment de l'audit). Ils ont donc été réécrits à partir de zéro, avec la
> nouvelle stratégie.

## Conventions

Chaque constat porte une étiquette :

- **[V] Fait vérifié** : constaté directement dans le code source, un fichier, une
  compilation ou une évaluation réalisée pendant l'audit (référence donnée).
- **[H] Hypothèse** : déduction plausible, non vérifiée par l'exécution.
- **[I] Inconnue** : information manquante, à obtenir avant de décider.

Méthode : clonage superficiel et en lecture seule des dépôts publics, hors de ce dépôt.
Aucun fichier de jeu n'a été téléchargé, lu ou produit. Aucun code de jeu n'a été
généré ou compilé. Les binaires tiers téléchargés n'ont pas été exécutés (inspection
statique seulement).

| Dépôt examiné | Commit examiné | Date du commit |
|---|---|---|
| `CalinGraphics/fifa-world-cup-2010-recompiled` | `498d18a` | 2026-10-26 |
| `RamiChaaben8/Fifa_World_Cup_2010_PC_Port` | `7ca2bea` (« Prepare v0.8 release ») | 2026-11-04 |
| `rexglue/rexglue-sdk` (outil commun aux deux) | `ebac1cf` (fusion « Release v0.11.0 », même arbre que l'étiquette `v0.11.0` = `a3e1d82`) | 2026-11-14 |
| `hedge-dev/XenonRecomp` | `ddd128b` | 2025-08-04 |

## Synthèse

Les deux projets identifiés sont des **recompilations statiques ReXGlue** : le code
PowerPC du jeu est traduit en C++ par ReXGlue, puis compilé avec le runtime ReXGlue
(dérivé de l'émulateur Xenia). Aucun n'émule le processeur à l'exécution. Les deux
ciblent **uniquement Windows x64 avec Direct3D 12**. Aucun ne distribue de fichiers du
jeu ni de code généré : le code C++ est généré chez l'utilisateur, depuis son ISO.

| Critère | A — CalinGraphics | B — RamiChaaben8 |
|---|---|---|
| Version | 0.3.1, statut « released » [V] | v0.8, « experimental, incomplete » [V] |
| Licence du code propre | BSD 3-Clause [V] | MIT, titulaire nommé « SAMUELITODAVILA » [V] |
| Plateforme | Windows 10/11 x64, D3D12 [V] | Windows 10/11 x64, D3D12 [V] |
| Commit ReXGlue épinglé | `bd833a2` (2026-10-01, entre v0.10.0 et v0.11.0) [V] | `c94f5eb` = v0.10.0 (2026-08-21) [V] |
| Correctifs du SDK | 8 correctifs, environ 640 lignes [V] | environ 20 000 lignes en deux correctifs principaux, plus 24 correctifs ciblés [V] |
| Version du disque exigée | Europe (En, Es, Nl) uniquement, SHA-256 des deux XEX publiés [V] | « Any region » selon le README, PAL ou USA/Asie selon d'autres sources [I] |
| Lecture directe de l'ISO | Oui, grâce à un correctif du SDK [V] | Non : extraction préalable avec extract-xiso [V] |
| Interface | Lanceur WPF/.NET 10 [V] | Scripts PowerShell, `Settings.exe` versionné [V] |
| Fonctions avancées | 60 i/s en match, 720p à 4K, filtrage anisotrope [V] | FSR, échelle 1x–4x, succès hors ligne, installation de DLC et de sauvegardes [V] |
| Linux | Non prévu (code Windows non protégé par `#ifdef`) [V] | Préréglages CMake Linux hérités du gabarit ReXGlue, jamais documentés comme testés [V]/[H] |

**Recommandation** : ne reprendre ni l'un ni l'autre en bloc. Construire un projet
portable propre sur ReXGlue, en réutilisant le savoir du projet A (licence BSD 3-Clause,
correctifs courts et documentés) comme référence principale, et celui du projet B
comme source secondaire (défauts du SDK identifiés, couverture régionale, DLC). Le
détail des réutilisations figure dans `docs/DECISIONS.md` (D-010).

---

## A. `CalinGraphics/fifa-world-cup-2010-recompiled`

### État d'avancement

- **[V]** Version `0.3.1` (fichier `VERSION`), statut `"released"` dans `.recomp.json`,
  cible unique `"Windows"`, chaîne `"ReXGlue"`, rendu Direct3D 12.
- **[V]** Fonctions annoncées : 60 i/s en match (30 i/s dans les menus et les cinématiques,
  comme sur la console), rendu interne 720p, 1440p ou 4K, filtrage anisotrope jusqu'à
  16x, manette ou clavier, lancement direct depuis l'ISO, mode portable.
- **[V]** Problèmes connus déclarés : Xbox Live indisponible, et « tous les modes de jeu
  n'ont pas encore été joués de bout en bout ».
- **[V]** Le jeu se compose de deux modules : `default.xex`, petit chargeur, et
  `fifadllzf.xex`, le module de jeu chargé par nom (`pc/fifawc10_manifest.toml`).
- **[V]** Correctifs propres au jeu :
  - `pc/fixes/boot_fixes.cpp` : contourne une lecture d'adresse quasi nulle au premier
    écran, tolérée par la console mais fatale sur PC ;
  - `pc/fixes/lua_diagnostics.cpp` : journalise les erreurs Lua (le jeu embarque Lua) ;
  - adresses `setjmp`/`longjmp` du CRT déclarées dans `pc/config/fifadllzf.toml` ;
  - deux réglages GPU imposés : `execute_unclipped_draw_vs_on_cpu` (écrans noirs dans
    Training Ground) et `gpu_allow_invalid_fetch_constants` (textures noires).
- **[V]** Fichiers d'analyse propres à la version du disque : 663 lignes de pointeurs de
  code pour `default.xex` et 17 028 lignes pour `fifadllzf.xex`, plus des débuts de
  fonctions ajoutés par `tools/autofix_codegen.py`. Ces adresses ne valent que pour les
  deux XEX dont les empreintes SHA-256 sont publiées dans le README.

### Construction

- **[V]** Windows uniquement : Visual Studio 2022+, LLVM/clang 18+, Python 3.9+ avec
  `cryptography` et `capstone`, .NET 10 pour le lanceur. Script unique `build.ps1`
  (PowerShell).
- **[V]** `tools/setup_sdk.ps1` clone ReXGlue, se place sur `bd833a2`, applique
  `patches/rexglue-sdk/*.patch` puis compile le SDK (environ une heure la première fois,
  selon le README).
- **[V]** `pc/CMakePresets.json` ne définit que des préréglages `win-amd64-*`.

### Correctifs du SDK (`patches/rexglue-sdk/`)

| Correctif | Rôle | Dépendance Windows | Présent en amont dans v0.11.0 |
|---|---|---|---|
| 0001 build-usbcam-exports | Compile les exports noyau de la caméra USB importés par le jeu | Non [V] | Exports `xboxkrnl_usbcam.cpp` présents [V] |
| 0002 find-module-by-file-name | Trouve un module chargé par son nom nu | Non [V] | [I] |
| 0003 function-table-base | Déplace la table de répartition pour éviter la collision des deux modules | Non [V] | Aucune occurrence de `function_table_base` [V] |
| 0004 precise-vblank | Cadence vblank précise | Minuterie Windows, avec repli portable [V] | [I] |
| 0005 disc-image-game-root | Accepte une ISO comme racine du jeu | Non [V] | Non : en v0.11, `title.game_root` doit être un dossier [V] |
| 0006 frame-rate-limit-and-swap-count | Limite 30/60 i/s, compteur d'images | Non [V] | Réglage `gpu.frame_limit` présent [V] |
| 0007 dialogs-without-continuous-repaint | Évite un rafraîchissement continu de la fenêtre | Non [V] | [I] |
| 0008 aggregate-enumerator-user-saves | Corrige l'énumération des sauvegardes (XUID tronqué à 32 bits par le jeu) | Non [V] | Traitement partiel du XUID de profil [H] |

**[V]** Un seul correctif contient du code propre à Windows (0004), et il prévoit un
repli portable. Les correctifs sont donc transposables à Linux. En revanche,
ReXGlue a été profondément réorganisé entre `bd833a2` et v0.11.0 (338 commits ;
`src/graphics` est devenu `src/gpu/xenos`, `src/audio` est devenu `src/apu`, les pilotes
sont devenus des modules chargés dynamiquement). Leur transposition vers v0.11.0 est donc
une réécriture partielle, pas une simple réapplication [V].

### Ce qui empêche une compilation Linux du code applicatif

| Fichier | Problème | Fait |
|---|---|---|
| `pc/src/data_folder.cpp` | `_wgetenv(L"LOCALAPPDATA")` sans garde `#ifdef` | [V] |
| `pc/src/open_launcher.cpp` | `#include <windows.h>`, `ShellExecuteW`, `MessageBoxW` sans garde | [V] |
| `pc/CMakeLists.txt` | `project(... LANGUAGES CXX RC)` et ressource `.rc` inconditionnels | [V] |
| `pc/CMakePresets.json` | Préréglages Windows uniquement | [V] |
| `launcher/` | WPF/.NET 10, Windows uniquement | [V] |
| `build.ps1`, `installer/*.ps1`, `tools/*.ps1` | PowerShell | [V] |
| `pc/src/crash_handler.cpp`, `pc/src/debug_watch.cpp`, `pc/src/main.cpp` | Code Windows protégé par `#ifdef _WIN32`, avec bouchon ailleurs | [V] |

**[H]** Ces blocages relèvent de la couche applicative : environ 300 lignes à
réécrire ou à isoler, sans incidence sur le code recompilé.

### Outils d'analyse (`tools/`)

- **[V]** `disc.py` : détecte, liste et extrait les images de disque Xbox 360 (XDVDFS,
  partitions XGD1/2/3) et PS3. En Python pur, donc portable.
- **[V]** `xexinfo.py` : lit les en-têtes XEX en clair (identifiant du titre, version,
  bibliothèques importées).
- **[V] Point juridique** : `xeximage.py` contient en dur la clé AES « retail » des XEX
  et produit l'image déchiffrée et décompressée. `disc.py` déchiffre les images PS3 avec
  la clé du disque. Voir `docs/audit/ISO_REQUIREMENTS.md` §5 et `docs/DECISIONS.md` D-008.
- **[V]** `ppcdis.py` (capstone), `find_code_pointers.py`, `find_setjmp.py`, `xref.py`,
  `callers.py`, `autofix_codegen.py` : aides à la rétro-ingénierie, en Python, portables.
  *Précision du 2026-11-22 : tous chargent l'image par `xeximage.load`, donc par le
  déchiffrement de `xeximage.py` (`docs/J2_PREREQUISITES.md` §3.3).*
- **[V]** `tools/lzxdec/lzxdec.c` : décompresseur LZX en C portable (libmspack).

### Licence

- **[V]** BSD 3-Clause, « Copyright (c) 2026, Miertescu Stefan-Calin ». Le texte précise
  qu'elle ne couvre ni le jeu, ni son contenu, ni le code recompilé.
- **[V]** Les composants tiers des versions publiées (ReXGlue, qui dérive de Xenia,
  FFmpeg, SDL…) gardent leurs licences, livrées dans `licenses/`.
- **Conséquence [V]** : réutilisation, modification et redistribution autorisées, sous
  réserve de conserver la notice et la clause de non-recommandation.

---

## B. `RamiChaaben8/Fifa_World_Cup_2010_PC_Port`

### État d'avancement

- **[V]** README : « unofficial, experimental, incomplete work in progress » ; certains
  parcours du jeu peuvent s'arrêter sur une fonction non recompilée.
- **[V]** v0.8 (2026-11-04) : succès hors ligne (31), notifications, installation de
  DLC (maillots, ballons, panneaux publicitaires) et de sauvegardes d'effectifs copiées
  depuis la console de l'utilisateur (paquets STFS).
- **[V]** v0.6 et v0.7 : FSR, échelle interne 1x–4x, FXAA/MSAA, correction du verrou à
  30 i/s propre à `fifadllzf.xex`, sélection des équipes sur le globe, remappage du clavier.
- **[V]** `NOTES.md` (465 Ko) consigne 32 « rounds » de débogage. Le dernier daté
  (2026-10-19) corrige un plantage pendant une rentrée de touche, causé par une de leurs
  propres déclarations de fin de fonction erronée. Le test en jeu restait alors à faire.
- **[H]** Le jeu atteint des matchs jouables sous Windows (PCGamingWiki le classerait
  « Playable », selon une recherche non vérifiée à la source).
- **[V]** Défaut de ReXGlue v0.10 découvert par le projet : les arguments 64 bits des
  exports noyau étaient tronqués à 32 bits (XUID de profil). Ils l'ont contourné par un
  correctif. **[H]** v0.11.0 réécrit ce chemin
  (`include/rex/ppc/call.h`, `GetIntegerArgumentValue<size>` paramétré par la taille) ;
  la correction reste à confirmer.

### Construction

- **[V]** Windows x64 : Visual Studio C++ Build Tools, LLVM, CMake, Ninja, environ 12 Go
  libres. Installateurs en ligne et hors ligne qui compilent le portage sur la machine.
- **[V]** ReXGlue épinglé sur `c94f5eb` (Release v0.10.0), avec
  `patches/rexglue-v0.3-local.patch` (10 700 lignes) et
  `patches/rexglue-local-changes.patch` (9 321 lignes). Ces correctifs touchent le
  générateur de code, la mémoire, XAM, ainsi que les présentateurs D3D12 et Vulkan.
- **[V]** L'ISO doit être extraite au préalable avec extract-xiso, binaire inclus dans
  l'installateur v0.3 avec sa notice de licence.
- **[V]** `Installer/recomp-template/CMakePresets.json` contient des préréglages
  `linux-amd64-*`, `linux-arm64-*` et `mac-*` issus du gabarit ReXGlue. **[H]** Rien
  n'indique qu'ils aient été essayés.

### Licence et provenance

- **[V]** Fichier `LICENSE` : MIT, « Copyright (c) 2026 SAMUELITODAVILA ». Le README dit
  le projet basé sur `samuelit0davila/fifa-street-pc-port`. La notice n'a pas été mise à
  jour pour l'auteur actuel.
- **[I]** Titularité exacte des contributions de RamiChaaben8 : MIT probable par
  cohérence, à confirmer.
- **[V]** Fichiers binaires versionnés : `Settings.exe` (≈ 375 Ko) et
  `sounds/Sequence 01.wav`. **[I]** Provenance du son inconnue. À ne pas reprendre.
- **[V]** extract-xiso est sous une licence de type BSD avec clause de publicité
  (fichier `Installer/EXTRACT-XISO-NOTICE.txt`).

---

## C. Outils de recompilation communs

### ReXGlue (`rexglue/rexglue-sdk`)

- **[V]** Recompilateur statique (génération de C++ ahead-of-time) et runtime. Le runtime
  dérive de Xenia ; l'analyse et la traduction des instructions s'inspirent de
  XenonRecomp.
- **[V]** Licence BSD 3-Clause (« Copyright (c) 2026, Tom Clay », avec des portions
  « Copyright (c) 2022, Ben Vanik and Xenia project contributors »).
- **[V]** « Early development », API instable entre versions (README).
- **[V]** CI de publication pour `win-amd64`, `linux-amd64`, `linux-arm64`, `mac-amd64`
  et `mac-arm64` (`.github/workflows/`).
- Détails Linux, Vulkan et NixOS : `docs/audit/LINUX_FEASIBILITY.md`.

### XenonRecomp (`hedge-dev/XenonRecomp`)

- **[V]** Licence MIT. Il ne fournit **aucun runtime** : il traduit seulement le code
  (avertissement explicite du README).
- **[V]** Dernier commit le 2025-08-04, soit environ 15 mois sans activité à la date de
  l'audit.
- **[V]** Compile sous Linux x86_64 (voir `LINUX_FEASIBILITY.md` §1.2).
- **[V]** Utilisé par Unleashed Recompiled (hedge-dev), qui a écrit son propre runtime
  et son propre moteur de rendu. Unleashed Recompiled est sous GPL-3.0 (documentation
  du projet) ; il ne peut donc servir que de référence d'architecture si l'on veut
  éviter la contamination GPL.

### Autres ports ReXGlue signalés sous Linux

- **[H]** Selon une recherche web non vérifiée à la source : reGH2 (Guitar Hero II,
  Linux/Vulkan), un port de Skate 3 (Vulkan sous Linux, MoltenVK sous macOS) et
  « bardown » (NHL 14, Linux et Windows). Si ces ports se confirment, ReXGlue sous Linux
  a déjà fait tourner des jeux commerciaux. Aucun ne concerne FIFA World Cup 2010.

## Inconnues prioritaires

1. **[I]** Version et région de l'ISO de l'utilisateur. Si ce n'est pas le disque
   « Europe (En, Es, Nl) » aux empreintes publiées par le projet A, ses 17 000 lignes de
   pointeurs ne s'appliquent pas et l'analyse doit être refaite (outils réutilisables).
   *Mise à jour du 2026-11-22 (J0)* : disque PAL en version `0.0.0.3`, aux empreintes
   différentes de celles du projet A. Les pointeurs ne peuvent pas être supposés valables
   et sont à revalider. Que le code diffère n'est pas établi
   (`docs/reports/J0_IDENTIFICATION.md` §3).
2. **[I]** Comportement du jeu sur le backend Vulkan : aucun des deux projets ne
   documente d'essai Vulkan.
3. **[I]** Correctifs du projet A encore nécessaires sur ReXGlue v0.11.0 (0002, 0004,
   0007, 0008).

## Sources

- https://github.com/CalinGraphics/fifa-world-cup-2010-recompiled
- https://github.com/RamiChaaben8/Fifa_World_Cup_2010_PC_Port
- https://github.com/rexglue/rexglue-sdk
- https://github.com/hedge-dev/XenonRecomp
- https://www.pcgamingwiki.com/wiki/List_of_unofficial_ports
- https://glitchmod.com/games/2010-fifa-world-cup-south-africa/mods/quiver-2010-fifa-world-cup-south-africa-fifa-world-cup-2010-pc-port
- https://mintlify.wiki/hedge-dev/UnleashedRecomp/introduction

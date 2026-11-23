# J2, étape A2 — Correctifs du projet A face à ReXGlue v0.11.0

> Étape A2 de `docs/J2_PLAN.md` (§3.2), sous l'autorisation PA-0 (D-015). **Phase A :
> aucune donnée du jeu.** Le document établit le besoin de chaque correctif **avant**
> toute transposition, comme le demande l'arbitrage du ticket #14. **Il ne contient aucun
> correctif.**
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Méthode

- **Correctifs comparés** : ceux de `patches/rexglue-sdk/` du projet A (BSD 3-Clause,
  commit `498d18a`). Ils visent la base `bd833a2` du SDK.
- **Base de comparaison** : le code de ReXGlue v0.11.0 à la révision `a3e1d82`. Les
  références `fichier:ligne` sans autre préfixe désignent cette source.
- **Lecture** : faite avec un agent de recherche en lecture seule. Ont été relus ligne
  par ligne :
  - la compilation de `xboxkrnl_usbcam.cpp` (0001) ;
  - la recherche des modules (0002) ;
  - l'énumérateur de contenus (0008) ;
  - la boucle de vblank (0004) ;
  - la normalisation des chemins (0002).
- **Ce qui reste à constater** : l'effet réel sur le jeu ne se constate qu'en l'exécutant,
  après PB-0 [I].

**Aucun correctif ne touche au déchiffrement** [V] :
- aucun des fichiers modifiés par la série n'est `src/filesystem/xex.cpp`, ni un fichier
  de `thirdparty/excrypt` (`grep '^diff --git'` sur la série) ;
- aucune transposition proposée ne touche un fichier qui inclut les en-têtes XEX ou
  cryptographiques.

## 2. Bilan

| Correctif | Besoin du jeu | État en v0.11.0 | Verdict | Jalon concerné |
|---|---|---|---|---|
| 0001 exports de la caméra USB | Le jeu importe les exports `XUsbcam*` | **Fourni** : `xboxkrnl_usbcam.cpp` est compilé (`src/kernel/CMakeLists.txt:136`), avec des bouchons (`src/kernel/xboxkrnl/xboxkrnl_usbcam.cpp:25-48`) | **Déjà en amont** | — |
| 0002 module trouvé par son nom nu | `default.xex` charge `fifadllzf.xex` par son seul nom | **Non fourni** : le nom nu est joint au chemin de périphérique de l'exécutable (`src/kernel/module_registry.cpp:385-393`), et la recherche exige une égalité exacte (`:620-630`) | **Compatibilité à vérifier en phase B** : la configuration d'abord, le correctif seulement si elle échoue (§3.1) | J3 (démarrage) |
| 0003 table de répartition | Les tables de `default.xex` et de `fifadllzf.xex` se chevauchent | **Non fourni** (`docs/J2_A1_SDK_INVENTORY.md` §5.4) | **Candidat à une intervention**, à confirmer à l'étape A3 [H] | J2 (gabarits de génération), J3 |
| 0004 vblank précis | Des vblanks réguliers à 60 Hz | **Fourni** : sommeil jusqu'au prochain vblank par `SleepFor`, rattrapage limité à 4 (`src/gpu/xenos/xenos_graphics_driver_base.cpp:157-180`, `src/gpu/xenos/vblank_pacing.h:19-51`). Sous Linux, `SleepFor` est une boucle `nanosleep` (`src/base/threading_posix.cpp:264-273`) | **Déjà en amont**. Le correctif visait Windows | — |
| 0005 ISO comme racine du jeu | Lancer directement sur l'image | **En partie** : un lecteur d'images GDFX existe (`include/rex/filesystem/mount.h:31-36`), mais la racine doit être un dossier (`src/filesystem/file_system.cpp:337-345`, `src/app/title_app.cpp:122-124`) | **Non nécessaire** : le plan extrait la racine du jeu (B1, `rexglue vfs dump`) | — |
| 0006 limite de cadence et compteur d'images | Option « 30 i/s », et compteur pour l'affichage des i/s | **Compteur fourni** : `IGraphicsSystem::GetFrameStats` (`include/rex/gpu/graphics_system.h:23-27,67-68`). **Limiteur absent** pour l'invité : `gpu.frame_limit` ne limite que les présentations de l'hôte (`src/gpu/present_thread.cpp:72-84`), et `VdSwap` n'est pas freiné (`src/kernel/xboxkrnl/xboxkrnl_video.cpp:377-433`) | Compteur : **déjà en amont**. Limiteur : **seulement si l'option 30 i/s est voulue** | J5 (réglages) |
| 0007 dialogues sans repeinture continue | Ne pas repeindre à la fréquence de l'écran entre deux images du jeu | **Fourni par la conception** : les incrustations sont dessinées à chaque présentation (`src/gpu/present_thread.cpp:64-69`), et `RequestPaint` ne fait rien (`src/gpu/xenos/host/xenos_presentation.h:78`) | **Sans objet** | — |
| 0008 énumération des sauvegardes | Le jeu demande ses sauvegardes avec un identifiant tronqué (`00000000BABEBABE`) et n'en trouve aucune. Le projet A a constaté une sauvegarde nouvelle à chaque lancement | **Non fourni** : l'identifiant brut est transmis (`src/xam/xam_content_aggregate.cpp:98-99`), avec un seul type de contenu (`:84`) | **Besoin probable, à vérifier à l'exécution** [H] | J4 et J5 (sauvegardes) |

**Conséquences pour J2** (génération de code et édition de liens, C2.1 à C2.4). Aucun
essai n'a encore eu lieu avec les fichiers du jeu ; ce sont des constats de lecture :
- seul 0003 est **candidat** à une intervention pour J2, par le gabarit
  `_indirect_call.inja`. Le besoin est à confirmer à l'étape A3 ;
- 0002 et 0008 touchent l'exécution, à J3 et après ;
- l'édition de liens n'attend aucun de ces correctifs [H].

## 3. Détail des correctifs à traiter

### 3.1 0002 — module trouvé par son nom nu

**Le mécanisme** [V] :
- `LoadUserModule` joint le nom nu au dossier de l'exécutable. Celui-ci est chargé comme
  `game:\default.xex`, et son chemin est sous la forme de périphérique
  `\Device\Harddisk0\Partition1\…` (`src/kernel/title_state.cpp:637-643`,
  `src/filesystem/file_system.cpp:26,344-346`) ;
- `FindRecompiledModule` compare ensuite les chemins normalisés ;
- `NormalizeGuestPath` (`src/base/path.cpp:254-270`) :
  - change les séparateurs en `/` ;
  - retire un préfixe `X:` ;
  - simplifie le chemin ;
  - retire les `/` en tête ;
  - passe en minuscules.

**Deux voies.** La première est retenue d'abord, parce qu'elle ne modifie pas le SDK :

1. **Configuration seule.** Le module est déclaré dans le manifeste avec
   `guest_path = "\\Device\\Harddisk0\\Partition1\\fifadllzf.xex"`.
   - [V] Ce chemin et le chemin joint par le runtime se normalisent tous deux en
     `device/harddisk0/partition1/fifadllzf.xex`.
   - [V] La génération de code n'utilise `guest_path` que pour le registre des modules ;
     elle trouve le fichier par `file_path` (`src/codegen/project_recompiler.cpp:636-646`).
   - [H] Cela suffit si le jeu charge son module par son nom nu. S'il passe
     `game:\fifadllzf.xex`, le `guest_path` par défaut (`fifadllzf.xex`) convient déjà.
     Le journal de la phase B le dira.
2. **Correctif**, si la configuration ne suffit pas.
   - Dans `ModuleRegistry::FindRecompiledModule`, accepter une correspondance sur le seul
     nom de fichier quand un seul module enregistré porte ce nom.
   - Il est accompagné d'un test unitaire du SDK, sans données du jeu.

### 3.2 0003 — table de répartition

Il fait l'objet de l'étape A3 (`docs/J2_PLAN.md` §3.3). Ce qu'il faut toucher [V] :
- la configuration de la génération de code : aucune clé n'existe aujourd'hui ;
- le gabarit `resources/templates/codegen/_indirect_call.inja:15-18`, qui calcule la base
  comme `REX_IMAGE_BASE + REX_IMAGE_SIZE` ;
- `FunctionDispatcher::InitializeFunctionTable` (`src/kernel/function_dispatcher.cpp:162-185`) ;
- `GuestAddressSpace::InitializeFunctionTable` (`src/kernel/memory.cpp:778-806`) ;
- les appelants (`src/kernel/title_state.cpp:332`, `src/kernel/module_registry.cpp:481-483`).

Le correctif 0002 du projet A contient aussi une partie de 0003 : le passage de
`function_table_base`. Les deux sont à séparer.

### 3.3 0008 — énumération des sauvegardes

La correction irait dans `src/xam/xam_content_aggregate.cpp:73-152` [V]. Quand le jeu
demande un utilisateur quelconque (identifiant 0 ou -1), ou un identifiant réduit à ses
32 bits de poids faible :
- employer l'identifiant du profil connecté (`CurrentXAM().GetUserProfile().GetXUID()`) ;
- pour le type de contenu 0, lister les sauvegardes, le contenu acheté et le contenu de
  l'éditeur ;
- toujours lister le contenu commun.

[H] Le jeu demande encore `00000000BABEBABE` en v0.11.0 : cela dépend de l'API
d'identifiant qu'il lit. Seul un journal d'exécution le confirmera. Le correctif n'est
pas nécessaire à J2.

## 4. Réglages qui remplacent les options du projet A

| Option du projet A | Équivalent en v0.11.0 | Référence |
|---|---|---|
| `frame_rate_limit` (0006) | `gpu.frame_limit` : limite les présentations de l'hôte, pas l'invité | `include/rex/gpu/graphics_system.h:40-41` |
| `vsync` | `gpu.vsync` | `include/rex/gpu/graphics_system.h:39` |
| `game_data_root` (0005) | `title.game_root` : un dossier | `include/rex/kernel/title_paths.h:23-24` |
| `allow_game_relative_writes` | `title.game_writable` [H] | `include/rex/kernel/title_paths.h:25` |

## 5. Proposition pour la suite

1. **Rien à transposer** pour 0001, 0004, 0005 et 0007. Pour 0006, seul le compteur est
   fourni : `GetFrameStats` remplace `VdSwapCount`.
2. **0003** : traité à l'étape A3, qui confirmera ou non le besoin pour J2, avec un test
   synthétique et une analyse du placement.
3. **0002** :
   - d'abord la configuration (§3.1, voie 1), dans le gabarit A5 ;
   - le correctif seulement si le journal de la phase B montre qu'elle ne suffit pas.
4. **0008** : à transposer avant J4. Ce n'est pas un prérequis de PB-0 ni de J2.
5. **Limiteur de 0006** : seulement si le porteur du projet veut l'option 30 i/s (J5).

**Décision de l'orchestrateur** (revue 6021690260 de la PR #17, 2026-11-23) :
- **0002** : retenir d'abord le `guest_path` configuré, sans modifier ReXGlue. Cette
  configuration reste une hypothèse, à essayer localement après PB-0. Aucun correctif
  0002 n'est autorisé par ce seul résultat ;
- **0003** : réservé à l'étape A3, avec un test synthétique et une analyse du placement ;
- **0008** reporté à J4, et le limiteur de l'invité de 0006 reporté à J5, sauf besoin
  démontré plus tôt ;
- **0001, 0004 et 0007** : ne pas les transposer, puisqu'ils sont en amont ;
- les correctifs du déchiffrement restent exclus.

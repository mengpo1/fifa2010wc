# Plan du jalon J2 — génération de code et édition de liens

> Préparé le 2026-11-22 pour le ticket [#12](https://github.com/mengpo1/fifa2010wc/issues/12).
> **Ce plan n'autorise à lui seul aucune exécution.** Chaque phase demande sa propre
> autorisation explicite (§2).
>
> Mise à jour du 2026-11-23 (D-015, ticket #14) :
> - PA-0 et PJ2-3 sont accordées ;
> - PB-0 n'est pas franchi : la phase B attend PA-1, les contrôles CP-1 à CP-7 et la
>   décision sur la méthode A8 ;
> - les points du §6 sont tranchés, sauf la méthode de validation des adresses ;
> - J2 est commencé par l'étape A1, dont l'inventaire est `docs/J2_A1_SDK_INVENTORY.md`.
>
> Mise à jour du 2026-11-24 (D-016) :
> - la phase A est close : **PA-1 est franchi** (`reports/J2_PHASE_A.md`) ;
> - la méthode de validation des adresses est décidée (§6) ;
> - **PB-0 n'est pas franchi** : la phase B attend les contrôles CP-1 à CP-7 sur la
>   machine de l'utilisateur, puis la décision PB-0.
>
> Mise à jour du 2026-11-24 (D-017, ticket #14) :
> - **PB-0 est franchi**, pour **B1 seulement**, sur la machine NixOS de l'utilisateur et
>   dans `$WC2010_PRIVATE_DIR` ;
> - la procédure de B1 est préparée sans données du jeu (ticket #32,
>   `J2_B1_EXTRACTION.md`). B1 n'est pas encore exécutée ;
> - **PB-1 n'est pas franchi** ; B2 attend sa décision.
>
> Mise à jour du 2026-11-27 (D-020, ticket #32) :
> - **B1 est exécutée et validée : PB-1 est franchi** (`reports/J2_B1_RESULT.md`) ;
> - **B2 n'est pas autorisée** : elle est soumise à un mandat distinct. Sa procédure est
>   proposée, sans données du jeu (`J2_B2_COMPATIBILITY.md`), sur le moteur d'étapes de
>   B1 (`J2_LOCAL_STEP_ENGINE.md`).
>
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Cadre

**Objectif de J2** (`ROADMAP.md` §2 et §4) : générer le code des deux modules du disque
de l'utilisateur et lier un exécutable Linux natif. Critères : C2.1 à C2.4.

**Statuts au départ** :

| Élément | État | Référence |
|---|---|---|
| D-008 | Décision de projet clôturée — O3 retenue. Le risque juridique résiduel reste ouvert | `DECISIONS.md` ; `audit/RISKS.md`, R-01 |
| J0 | Clos : C0.1 à C0.5 atteints | `reports/J0_IDENTIFICATION.md` §5.2 |
| PJ2-1 | Levé au plan de la gouvernance, sans certification juridique | `J2_PREREQUISITES.md` §2 |
| PJ2-2 | Atteint | `J2_PREREQUISITES.md` §2 |
| PA-0 | **Accordée** le 2026-11-23 | `DECISIONS.md`, D-015 |
| PJ2-3 | **Accordée sur le principe** le 2026-11-23, phase B comprise, sur la machine de l'utilisateur | `DECISIONS.md`, D-015 ; `J2_PREREQUISITES.md` §2 |
| PB-0 | **Franchi** le 2026-11-24, pour B1 seulement | `DECISIONS.md`, D-017 ; §2 |

**Règles qui valent pour toutes les étapes** :

- **D-007** : l'ISO, les XEX, les images décodées, le code généré, les caches et les
  journaux du jeu restent dans `$WC2010_PRIVATE_DIR`. Ils ne vont jamais dans Git, en CI,
  dans un journal public ni dans `/nix/store`.
- **Contrainte reformulée** (D-008) : seul le SDK amont ReXGlue v0.11.0 déchiffre, et
  localement. Le projet n'écrit, ne versionne ni ne diffuse aucune clé, ni aucun code ou
  outil de déchiffrement qui lui soit propre. Restent donc exclus `xeximage.py` du projet
  A et XenonRecomp.
- **Ne pas réimplémenter ce que ReXGlue fournit.** Chaque ajout est précédé d'un
  inventaire (étape A1).
- **Toute dépendance** est identifiée, justifiée et épinglée (`DEPENDENCIES.md`).
- **Aucun résultat déclaré sans preuve d'exécution.**
- **Pas d'identité de code présumée avec le projet A.** Des adresses compatibles ne la
  prouvent pas (`J2_PREREQUISITES.md` §3).
- **Une PR en brouillon par étape**, avec une revue de l'orchestrateur. Aucune fusion
  sans l'accord explicite du porteur du projet.

## 2. Autorisations et points d'arrêt

| Point | Quand | Qui décide | Condition |
|---|---|---|---|
| **PA-0** | Avant la phase A | Porteur du projet, avec l'orchestrateur | Autorisation explicite de la phase A. **Accordée le 2026-11-23** (D-015) |
| **PA-1** | Fin de la phase A | Orchestrateur, puis porteur du projet | Critères de sortie du §3.9. **Franchi le 2026-11-24** (D-016) |
| **PB-0** | Avant la phase B | Porteur du projet | **Autorisation PJ2-3 expresse** (accordée le 2026-11-23, D-015), PA-1 franchi, contrôles CP-1 à CP-7 exécutés et consignés (`J2_PREREQUISITES.md` §6), méthode de validation des adresses décidée (`J2_PREREQUISITES.md` §3.3). **Franchi le 2026-11-24** (D-017), pour B1 seulement : la méthode est décidée (M1, §6), PA-1 est franchi (D-016), et les contrôles CP-1 à CP-7 sont exécutés sur la machine de l'utilisateur et consignés dans le ticket #14, dont la vérification des *core dumps* |
| **PB-1** | Après l'extraction (B1) | Orchestrateur | Nombres de fichiers et empreintes conformes au rapport J0. **Franchi le 2026-11-27** (D-020) : 49 fichiers, 8 dossiers, empreintes concordantes, aucun constat (`reports/J2_B1_RESULT.md`) |
| **PB-2** | Après le contrôle de compatibilité (B2) | Orchestrateur, puis porteur du projet | Validation des adresses ou nouvelle analyse |
| **PB-3** | Avant de versionner un fichier tiré du disque | Orchestrateur, puis porteur du projet | Seules des adresses et des métadonnées, autorisées par D-007, après le contrôle des données |
| **PB-4** | Fin de J2 | Orchestrateur, puis porteur du projet | C2.1 à C2.4. J3 ne commence pas sans décision |

**Confirmé (D-015)** : PA-0 est distincte de PJ2-3. La phase A ne lit aucune donnée du
jeu.

**Arrêts immédiats, à toute étape** (on suspend, on consigne, on ne supprime rien sans
décision explicite) :

- une donnée propriétaire est trouvée dans le dépôt, en CI ou dans le magasin Nix ;
- une valeur de clé apparaît dans une sortie. La sortie reste privée et n'est pas
  partagée ;
- une étape demanderait un déchiffrement par un autre outil que le SDK ;
- un correctif toucherait le décodage des XEX, `thirdparty/excrypt` ou les clés du SDK.

## 3. Phase A — préparations génériques, sans données du jeu

**Entrée** : PA-0, accordée le 2026-11-23.

**Règles de la phase** :

- aucune donnée du jeu n'est lue, demandée ni produite, et aucune n'est requise ;
- la CI publique exécute tout ;
- chaque étape passe `nix flake check -L --no-update-lock-file` et
  `check_proprietary_data.py repo`.

### 3.1 A1 — Inventaire de ce que fournit ReXGlue v0.11.0

- **But** : ne rien réécrire de ce que le SDK fournit, et savoir où il écrit ses sorties.
- **Faits déjà relevés** (lecture de la source à `a3e1d82`, sans exécution) :
  - [V] `GetUserFolder` suit `XDG_DATA_HOME`, et à défaut `~/.local/share`
    (`src/base/platform/file_posix.cpp`). L'inventaire A1 a établi qu'aucun code de `src/`
    ne l'appelle ;
  - [V] `GetUserConfigFolder` suit `XDG_CONFIG_HOME`, et à défaut `~/.config/<nom>` ;
  - [V] `XDG_STATE_HOME` n'est utilisé nulle part dans `src/` ;
  - [V] un rapporteur de plantage POSIX par signaux existe (`src/base/crash_posix.cpp`) ;
  - [V] `rexglue` écrit son journal dans un fichier avec `--log-file`
    (`src/rexglue/main.cpp`).
- **État (2026-11-23)** : l'inventaire est rédigé, `docs/J2_A1_SDK_INVENTORY.md`. Il
  est soumis à la revue de l'orchestrateur.
- **Livrable** : un inventaire versionné, `docs/J2_A1_SDK_INVENTORY.md`. Pour chaque
  point, le fichier source et sa ligne, et le statut « fourni » ou « à écrire ». Points
  couverts :
  - chemins, journaux et plantages ;
  - fichiers écrits par `rexglue codegen` et par le runtime ;
  - ce qui est journalisé pendant le décodage d'un XEX ;
  - ce que la génération de code expose pour valider des adresses : fonctions
    découvertes, diagnostics.
- **Critère de sortie** : chaque affirmation renvoie à la source épinglée. Les sorties
  qui pourraient contenir des données du jeu ou des clés sont listées.
- **Arrêt si** : un besoin demande un correctif du décodage des XEX.

### 3.2 A2 — Correctifs du SDK sans adresse du jeu

- **But** : transposer vers v0.11.0 les correctifs 0001, 0002, 0004, 0006, 0007 et 0008
  du projet A (`J2_PREREQUISITES.md` §4). Avant cela, établir ceux qui sont déjà en
  amont : 0001 et 0006 semblent l'être (D-011).
- **État (2026-11-23)** : l'analyse des besoins est rédigée, sans aucun correctif
  (`docs/J2_A2_SDK_PATCHES.md`). Elle est soumise à la revue.
  - Déjà en amont : 0001, 0004 et 0007.
  - En partie : 0006, dont le compteur est fourni.
  - 0002 : compatibilité à vérifier en phase B, la configuration d'abord.
  - 0008 : besoin probable, reporté à J4.
  - 0003 : candidat pour J2, à confirmer en A3. *Transposé en A3 (§3.3).*
  - Non nécessaire : 0005, puisque la racine du jeu est extraite.

  Les correctifs ne seront écrits qu'après la validation de ces verdicts.
- **Livrable** : une série numérotée dans `patches/rexglue-sdk/`, appliquée par
  `nix/rexglue-sdk.nix`, et la provenance de chaque correctif (D-010).
- **Critère de sortie** :
  - `nix build .#rexglue-sdk` passe, avec les tests du SDK ;
  - aucun correctif ne touche `src/filesystem/xex.cpp`, `thirdparty/excrypt` ni les
    clés ; une commande de vérification sur la série le montre.
- **Tranché (D-015)** : « O3 tel quel » désigne le mécanisme de décodage et de
  déchiffrement des XEX de l'amont, inchangé.
  - Les correctifs fonctionnels sans lien avec le déchiffrement restent permis, avec des
    tests.
  - Aucun correctif ancien n'est présumé compatible : chaque besoin est confirmé avant la
    transposition, et son impact est examiné.

### 3.3 A3 — Correctif 0003 : table de répartition des fonctions

- **But** : savoir où placer la table de répartition dans le runtime de v0.11.0. Il faut
  connaître la taille par module, la carte mémoire invitée et les réservations
  (`J2_PREREQUISITES.md` §5). Ensuite, rendre `function_table_base` configurable.
- **Livrable** : le correctif, des contraintes documentées et un test synthétique.
- **Critère de sortie** : le test passe dans la construction du SDK. La valeur
  `0x86100000` du projet A n'est pas tenue pour valide sans cette analyse.
- **État (2026-11-23)** : correctif et analyse rédigés, soumis à la revue
  (`docs/J2_A3_FUNCTION_TABLE.md`, `patches/rexglue-sdk/0001-function-table-base.patch`).
  - Sans la clé, la table reste où l'amont la place.
  - Une table déplacée doit tomber sur des pages libres : v0.11.0 ne le vérifie pas. Le
    correctif l'alloue par une allocation exclusive, sans fenêtre entre la vérification et
    la prise des pages (P-38), et calcule tailles et fins sur 64 bits (P-39).
  - `0x86100000` n'est valable que si le code de `fifadllzf.xex` ne dépasse pas
    `0x12C8000` octets [I]. `0x86C10000` l'est pour toute taille de code. Le choix
    revient à la phase B.

### 3.4 A4 — Outils des contrôles avant traitement

- **But** : automatiser ce qui peut l'être des contrôles CP-1 à CP-6
  (`J2_PREREQUISITES.md` §6).
- **État (2026-11-23)** : `tools/private_guard.py` et ses tests
  (`tools/test_private_guard.py`, contrôle Nix `private-guard-selftest`) sont rédigés, ainsi
  que la procédure `docs/J2_PHASE_B_CONTROLS.md`. Ils sont soumis à la revue.
- **Livrable** :
  - un script qui vérifie le confinement de `$WC2010_PRIVATE_DIR` (CP-1). Il refuse un
    dossier situé dans le dépôt ou dans `/nix/store`, un chemin relatif et des droits
    trop larges ;
  - un script pour CP-4 (`J2_PREREQUISITES.md` §6.1). Avant l'invocation, il vérifie les
    destinations d'écriture. Après, il recherche les fichiers créés dans les
    emplacements surveillés ;
  - une procédure écrite pour CP-3 et CP-5.
- **Critère de sortie** : des tests sur des arborescences synthétiques, dans
  `nix flake check`. Ils montrent que :
  - le script de CP-1 refuse un dossier privé placé dans le dépôt ;
  - celui de CP-4 refuse une destination hors du dossier privé ;
  - celui de CP-4 signale un fichier écrit dans un emplacement surveillé.

  Ces tests ne prouvent pas l'absence de toute sortie ailleurs (`J2_PREREQUISITES.md`
  §6.1).

### 3.5 A5 — Gabarit de configuration non propriétaire

- **But** : un manifeste et une configuration de projet qui prennent leurs chemins dans
  `$WC2010_PRIVATE_DIR`, selon `ISO_REQUIREMENTS.md` §6. Ils déclarent la version du SDK
  de v0.11.0. Si `rexglue init` produit déjà cette structure, le gabarit en part (A1).
- **Exclu** : les adresses de la configuration d'analyse du projet A (CP-7).
- **Critère de sortie** :
  - le gabarit se résout sur un dossier privé synthétique ;
  - le dépôt ne contient aucun chemin absolu ni aucune valeur propre au disque ;
  - le contrôle des données passe.
- **État (2026-11-23)** : gabarit et outil rédigés, soumis à la revue
  (`docs/J2_A5_CONFIG_TEMPLATE.md`, `config/private-template/wc2010_manifest.toml`,
  `tools/private_project.py`).
  - Les deux XEX doivent se trouver sous `game_root` : le gabarit les cherche dans
    `game/`, et le dossier `xex/` ne sert pas à la génération.
  - Le module porte le `guest_path` de la voie 1 de 0002, hypothèse à essayer en phase B.
  - L'analyseur de ReXGlue lit la copie dans un dossier synthétique sans XEX, et s'arrête
    avant de lire le jeu.

### 3.6 A6 — Couche `platform/linux`, limitée aux manques

- **But** : n'écrire que ce que l'inventaire A1 donne comme manquant, en respectant les
  règles de D-006.
- **Ticket #11** (J1-bis) : il est remplacé par la phase A (D-015). La couche Linux
  générique relève de A1, puis de A6, et rien n'est engagé sous #11.
- **Critère de sortie** : des tests Linux sans données du jeu.
- **État (2026-11-23)** : audit rédigé, soumis à la revue (`docs/J2_A6_LINUX_GAPS.md`,
  ticket #21). **Aucun changement du runtime** : aucun manque ne justifie du code.
  - Le contrôle Nix `linux-confinement` rejoue la procédure de phase B avec `rexglue vfs
    dump` sur une image synthétique : les réglages confinent les écritures, et leur absence
    est signalée avant et après l'étape.
  - Restent sans correctif : l'objet de mémoire de l'invité dans `/dev/shm`, et le
    *core dump* transmis par tube, à vérifier une fois sur la machine de l'utilisateur.

### 3.7 A7 — Essai de la chaîne sans données du jeu (facultatif)

- **But** : exercer la génération de code et l'édition de liens dans l'environnement
  Nix : `-DREXGLUE_LLD`, RUNPATH, constats P-05 et P-07 de
  `reports/J1_VALIDATION.md` §6.
- **Moyen** : une entrée non propriétaire, à trouver [I].
  `rexglue recompile-tests` produit des tests Catch2 à partir d'assembleur PowerPC
  (`src/rexglue/command/test_recompiler.cpp`). C'est une piste, à évaluer [H].
- **Critère de sortie** : un ELF lié au SDK sans aucune donnée du jeu, ou un constat
  d'impossibilité documenté.
- **État (2026-11-24)** : critère atteint ; revue favorable (6039473611), fusionnée (#26)
  (`docs/J2_A7_SYNTHETIC_CHAIN.md`). Le contrôle Nix `a7-synthetic-chain` construit un
  hôte par `rexglue_configure_target`, à partir du C++ que `rexglue recompile-tests` tire
  de 161 programmes de test d'amont, assemblés par les GNU binutils de nixpkgs.
  - **Défaut trouvé et corrigé** : les emplacements des modules fournisseurs du paquet du
    SDK étaient faux, ce qui empêchait de lier l'hôte. Le correctif est
    `-DCMAKE_INSTALL_LIBDIR=lib` dans `nix/rexglue-sdk.nix`, sans toucher au SDK.
  - **Second défaut, corrigé** : `nix develop` garde le `PATH` de la machine. Sans
    `-DREXGLUE_LLD`, un `ld.lld` hors de Nix aurait été pris sans rien signaler. Les
    presets passent maintenant `REXGLUE_LLD`. `CMakeLists.txt` arrête la configuration
    dans trois cas : la variable manque, le cache en diffère, ou un programme sonde lié
    par cet éditeur de liens ne démarre pas sans `LD_LIBRARY_PATH` (revue P-47). C'est
    un contrôle de comportement, pas d'identité.
  - P-05 est reproduit avec le `lld` brut, et vérifié corrigé avec le `ld.lld`
    enveloppé. P-07 tient pour les copies faites à côté de l'hôte.
  - Les 1 615 cas Catch2 tirés des 161 programmes passent.
  - Non couverts : un XEX (`rexglue codegen`, `rexglue_project`), VMX128 (29 programmes)
    et le chargement des modules à l'exécution.

### 3.8 A8 — Proposition sur la source de l'image en clair

- **But** : préparer la décision du `J2_PREREQUISITES.md` §3.3, à partir de A1. Les outils
  du projet A chargent l'image par `xeximage.py`, qui est exclu. ReXGlue n'a aucune
  commande qui écrive l'image décodée.
- **Arbitrage (D-015)** :
  - la note évalue d'abord une validation fondée sur les diagnostics, les sorties et les
    interfaces existants de ReXGlue ;
  - si elle ne suffit pas, la note compare les autres méthodes, avec leurs risques,
    leurs limites et les dérogations qu'elles demanderaient ;
  - aucun programme nouveau produisant une image décodée n'est autorisé implicitement.
- **Livrable** : une note qui compare les pistes, sans en exécuter aucune. **La décision
  revient à l'orchestrateur et au porteur du projet.**
- **État (2026-11-23)** : la note est rédigée, `docs/J2_A8_ADDRESS_VALIDATION.md`.
  L'arbitrage de l'orchestrateur (revue 6021690700) :
  - M1 est la méthode de première analyse : les diagnostics, les listes d'adresses et la
    désassemblée en commentaire du code généré ;
  - M3, une nouvelle analyse avec ReXGlue seul, est le repli de recherche ;
  - M2, une image produite par le projet, n'est pas autorisée ;
  - l'étape A8-bis est autorisée en phase A. Ce sera l'outil de comparaison, purement
    analytique, avec des tests synthétiques. Elle ne franchit pas PB-0 à elle seule.

  M1 n'établit que des niveaux de preuve N0 à N2. Les valeurs de données restent N3,
  non vérifiées.
- **A8-bis (2026-11-23)** : outil rédigé, soumis à la revue (`tools/address_compare.py`,
  `docs/J2_A8BIS_ADDRESS_COMPARE.md`, ticket #22). Il automatise N0 et N1 à partir des
  formats de la source de ReXGlue. N2 vient d'un relevé d'examen manuel, que l'outil
  contrôle, car les commentaires du code généré ne portent pas d'adresse. Ses tests sont
  synthétiques ; il ne traitera les sorties privées qu'en phase B.

### 3.9 Sortie de la phase A (PA-1)

- A1 à A6 et A8 sont fusionnées, chacune avec la CI verte. A7 est faite, ou son
  impossibilité est documentée.
- `nix flake check -L --no-update-lock-file` et `check_proprietary_data.py repo` passent
  sur `main`.
- Aucun fichier du jeu n'a été lu ni requis, ce que garantit une CI sans le jeu.
- La série de correctifs ne touche ni le décodage des XEX, ni `excrypt`, ni les clés.
- La source de l'image est décidée par le porteur du projet, sur la proposition A8. À
  défaut, PB-0 n'est pas franchi et la phase B ne commence pas.
- Un rapport de phase A est rédigé. PJ2-3 est déjà accordée (D-015) : PA-1 n'en est
  pas un nouveau consentement, seulement un point de revue.
- **État (2026-11-24)** : rapport rédigé (`reports/J2_PHASE_A.md`).
  - **Première revue** (6039494135) : le rapport est recevable, mais **PA-1 n'est pas
    franchi**. A7 (#26) est fusionnée et le rapport est ramené sur `main`. Il faut
    encore une CI verte, une seconde revue et la décision du porteur du projet.
  - **Tests Debug de ReXGlue instables sous charge** (§4.1 du rapport, ticket #28) :
    l'orchestrateur retient l'option 2 à titre provisoire, sous réserve de la
    confirmation du porteur. La règle : une relance manuelle au plus, les preuves des
    deux tentatives gardées, et un second échec bloque.
  - **Seconde revue** (6043202272) : P-47 est levé, et le contenu est accepté. Le
    rapport est fusionné (#27).
  - **Décision du porteur du projet (2026-11-24, D-016)** : **PA-1 est franchi**, et la
    règle des tests Debug est confirmée. PB-0 n'est pas franchi.

## 4. Phase B — traitement local des données privées, après PB-0

**Entrée** : PB-0 (§2). L'autorisation PJ2-3 est citée et reliée à sa source dans
`DECISIONS.md` (D-015) et `J2_PREREQUISITES.md` §2.

**Règles de la phase** :

- l'utilisateur exécute les étapes sur sa machine, d'après une procédure versionnée,
  comme à J0 ;
- rien ne s'exécute en CI ;
- toutes les sorties vont sous `$WC2010_PRIVATE_DIR` ;
- après chaque étape, on refait CP-3 et CP-4 (`J2_PREREQUISITES.md` §6) ;
- seuls des résultats sans contenu propriétaire reviennent dans le dépôt : nombres,
  statuts, empreintes, adresses.

### 4.1 B1 — Extraction de la racine du jeu

- **Action** : `rexglue vfs dump` de l'ISO vers `$WC2010_PRIVATE_DIR/game`. En v0.11.0,
  `title.game_root` doit être un dossier.
- **Fait relevé** : [V] la commande ouvre le conteneur et l'extrait (`OpenContainer`,
  puis `Extract`), sans appel au décodage des XEX
  (`src/rexglue/command/vfs_command.cpp`).
- **Procédure** : `J2_B1_EXTRACTION.md` (ticket #32), outil `.#b1-extract`.
  - [V] Syntaxe : `rexglue vfs dump <source> <destination>`, sans option propre.
  - [V] L'extraction écrase les fichiers existants : la destination doit être vide.
  - [V] Le nombre de nœuds de ReXGlue compte la racine ; celui de J0 ne la compte pas.
- **État (2026-11-24)** : procédure et tests synthétiques en PR brouillon. B1 n'est pas
  exécutée.
- **Revue de la PR #33 (2026-11-25)** : corrections B1-R01 à B1-R07, dont le confinement
  de l'extraction dans un bac à sable bubblewrap.
- **Arbitrages du porteur (D-018)** :
  - option B pour les plantages : limite `1` pour l'extraction seule, mode tube seul ;
  - rapport J0 local obligatoire.

  `run` reste bloqué tant que `rehearse` n'a pas apporté la preuve locale du
  `J2_B1_EXTRACTION.md` §6.3, dans le même démarrage.
- **Revue de la version 3 (2026-11-25)** : plantages de la preuve identifiés par leur pid,
  preuve liée au protocole, à l'outil et à bubblewrap, contrôles après coup isolés, et
  bac à sable par liste positive.
- **Arbitrage du porteur (D-019)** : du magasin Nix, le bac à sable ne montre que la
  fermeture de la commande empaquetée, calculée à la construction ; sans fermeture valide
  et complète, rien ne démarre (`J2_B1_EXTRACTION.md` §3.4).
- **Essai local du porteur (2026-11-26)**, version 5 fusionnée : `prepare` conforme ;
  `rehearse` en `core-probe-failed`, les plantages synthétiques ne démarrant pas. Cause :
  bubblewrap cherché par son nom dans un environnement vide. Corrigé en version 6, avec
  `diagnose` en lecture seule (`J2_B1_EXTRACTION.md` §6.4). `run` reste non autorisé.
- **Exécution (2026-11-27)** : avec la version 6, sur la machine du porteur, sans constat.
  **PB-1 est franchi** (D-020, `reports/J2_B1_RESULT.md`).
- **Critère de sortie** (PB-1) :
  - 49 fichiers et 8 dossiers, comme dans le rapport J0 ;
  - les SHA-256 de `default.xex` et `fifadllzf.xex` extraits sont ceux du rapport J0 ;
  - l'empreinte de l'ISO est inchangée ;
  - CP-3 et CP-4 passent.
- **Arrêt si** : un nombre ou une empreinte diffère.

### 4.2 B2 — Contrôle de compatibilité

- **Action** : une première génération de code par ReXGlue, avec la configuration du
  projet A comme simple entrée de test. ReXGlue déchiffre les modules localement :
  c'est le premier déchiffrement du projet, par la voie O3. Le code généré va dans
  `$WC2010_PRIVATE_DIR/generated`.
- **Critère** :
  - C2.1 : 0 `UnresolvedCall`, 0 erreur de validation ;
  - contrôles ciblés : `setjmp` et `longjmp`, sites des correctifs du jeu
    (`J2_PREREQUISITES.md` §3.2). Leur méthode dépend de la décision A8.
- **Point d'arrêt** (PB-2) :
  - un échec écarte la réutilisation telle quelle, et l'on passe à la nouvelle analyse
    (`J2_PREREQUISITES.md` §5) ;
  - un succès ne prouve pas l'identité du code.
- **Procédure** : proposée le 2026-11-27, version 2 après la revue ciblée de la PR #35 ;
  **non autorisée** (`J2_B2_COMPATIBILITY.md`, outil `.#b2-codegen`). Elle demande un
  mandat distinct (D-020). Elle propose un critère de plus, distinct de C2.1 : la
  complétude de la génération (`J2_B2_COMPATIBILITY.md` §6.3).

### 4.3 B3 — Validation des adresses

- **Action** : la validation de `J2_PREREQUISITES.md` §3.2, avec la méthode décidée en
  A8.
- **Critère de sortie** :
  - si les résultats régénérés sont identiques aux fichiers du projet A, la configuration
    est valable pour ce disque ;
  - au moindre écart, on garde la sortie régénérée et l'on reprend l'analyse sur les
    points divergents.

### 4.4 B4 — Configuration propre au disque de l'utilisateur

- **Action** : arrêter la configuration d'analyse finale, validée ou refaite.
- **Point d'arrêt** (PB-3) : avant de versionner des adresses tirées du disque. D-007 les
  autorise comme métadonnées, mais seulement après le contrôle des données et une revue.

### 4.5 B5 — Génération de code complète et édition de liens

- **Action** : le manifeste à deux modules, les correctifs 0002 et 0003 transposés (0003 :
  A3 ; 0002 : seulement si la configuration échoue, `docs/J2_A2_SDK_PATCHES.md` §5), et
  l'édition de liens avec `-DREXGLUE_LLD` et un RUNPATH corrigé. La configuration se fait
  depuis `nix develop`, avec un preset, qui passe `REXGLUE_LLD`
  (`docs/J2_A7_SYNTHETIC_CHAIN.md` §5 et §7).
- **Critère de sortie** : C2.1 à C2.4 (`ROADMAP.md` §4) :
  - `readelf -h` montre un ELF x86-64, sans dépendance à Wine ni à Windows ;
  - **après le vrai lien**, contrôle des dépendances de l'exécutable et des bibliothèques
    copiées à côté de lui, comme à l'étape 4 de `a7-synthetic-chain` (revue P-47) :
    - `$ORIGIN` dans le RUNPATH ;
    - `ld.so --list` sans « not found » ;
    - chaque bibliothèque dans le magasin ou dans le dossier de l'exécutable ;
    - l'interpréteur dans le magasin ;
  - aucun interpréteur ni JIT ;
  - le code généré n'est pas versionné : `git status` et le script du §4.5 de la feuille
    de route.

### 4.6 B6 — Contrôles de fin de J2

- **Actions** :
  - refaire CP-3 à CP-6 ;
  - vérifier que les empreintes de l'ISO et des XEX sont inchangées ;
  - rédiger le rapport J2, sans contenu propriétaire.
- **Point d'arrêt** (PB-4) : la revue de l'orchestrateur, puis la décision du porteur du
  projet. J3 n'est pas commencé sans décision.

## 5. Hors du plan

- J3 et la suite, ainsi que toute distribution.
- Le correctif « sans clé » d'O2, et `xeximage.py`.
- Le ticket #11 (J1-bis), remplacé par la phase A (D-015).
- La mise à jour du titre et les DLC.

## 6. Points à trancher

Points tranchés le 2026-11-23 (D-015) :

1. **L'autorisation de la phase A** : PA-0 est distincte de PJ2-3, et accordée.
2. **La lecture de « O3 tel quel »** : le déchiffrement de l'amont reste inchangé, et les
   correctifs fonctionnels sont permis (§3.2).
3. **L'articulation avec le ticket #11** : il est remplacé par la phase A (§3.6).

4. **La méthode de validation des adresses** (`J2_PREREQUISITES.md` §3.3) : M1 d'abord,
   M3 en repli, M2 non autorisée, A8-bis autorisée (`docs/J2_A8_ADDRESS_VALIDATION.md`
   §4). Arbitrée par l'orchestrateur le 2026-11-23, acquise à la fusion de la note (#18)
   avec l'accord du porteur du projet.

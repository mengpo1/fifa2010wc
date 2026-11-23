# Prérequis techniques du jalon J2

> Préparé le 2026-11-22, après l'identification du disque de l'utilisateur
> (`docs/reports/J0_IDENTIFICATION.md`). **Ce document ne commence pas J2.** Il dit ce
> dont J2 aura besoin, ce qui peut être repris du projet A et ce qui demande une
> nouvelle analyse.
> Mis à jour le 2026-11-22 après la clôture de D-008 (O3 retenue) et de J0. Le plan
> d'exécution de J2 est dans `docs/J2_PLAN.md`.
> Mis à jour le 2026-11-23 (D-015) : **PA-0 et PJ2-3 sont accordées. PB-0 n'est pas
> franchi.** Aucun fichier du jeu n'est encore traité.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Point de départ

- **J1** : chaîne de compilation Linux et NixOS validée et fusionnée (PR #2). C1.4 est
  validé sur le GPU de l'utilisateur.
- **J0** : clos le 2026-11-22. L'identification est faite (PR #3 pour l'outil), et C0.1 à
  C0.5 sont atteints (`J0_IDENTIFICATION.md` §5.2).
  - Le disque de l'utilisateur est un XGD2 PAL du titre `454108E4`, version `0.0.0.3` :
    49 fichiers, 8 dossiers, aucune anomalie.
  - Les SHA-256 de ses deux modules **diffèrent** de ceux du projet A.
  - Les deux modules sont chiffrés (AES) et compressés (LZX).
  - Leur disposition en mémoire **concorde** avec les trois valeurs publiées par le
    projet A (`J0_IDENTIFICATION.md` §3.2).
- **D-008** est une décision de projet clôturée : O3 est retenue le 2026-11-22. ReXGlue
  v0.11.0 amont déchiffrera lui-même les modules, localement. Le risque juridique
  résiduel reste ouvert (R-01).
- Le code machine des deux disques peut être identique ou différent [I]. Ni les
  empreintes des fichiers, ni la disposition en mémoire ne suffisent à le dire
  (`J0_IDENTIFICATION.md` §3). Des adresses compatibles ne permettent pas de présumer un
  code identique.

## 2. Prérequis bloquants

| N° | Prérequis | État | Responsable |
|---|---|---|---|
| PJ2-1 | D-008 tranchée. Toute génération de code a besoin de l'image en clair des deux modules. Éléments de décision : `docs/D-008_DECISION_NOTE.md` | **Levé au plan de la gouvernance** (2026-11-22) : décision de projet clôturée, **O3** retenue, c'est-à-dire ReXGlue v0.11.0 amont tel quel. La contrainte de mission est reformulée (D-008). **Ce n'est pas une certification juridique** : la qualification du déchiffrement, de la recompilation et du SDK contenant des clés n'est pas faite (R-01). La distribution est exclue | Porteur du projet, consigné par l'orchestrateur (ticket #8, commentaire 7086214621) |
| PJ2-2 | J0 clos : C0.5 atteint (`J0_IDENTIFICATION.md` §5) | **Atteint** (2026-11-22) : C0.1 à C0.5 atteints, vérification au §5.2 du rapport J0 | Orchestrateur et utilisateur |
| PJ2-3 | Autorisation explicite de commencer J2 | **Accordée sur le principe** le 2026-11-23 : « oui je l'autorise et AVEC les fichiers du jeu » (ticket #14, D-015). Elle vaut pour J2, phase B comprise, pour l'exemplaire privé de l'utilisateur et sur sa machine uniquement. Elle ne vaut ni autorisation des titulaires de droits, ni avis juridique (R-01) | Porteur du projet, consigné par l'orchestrateur |

La phase A, sans données du jeu, a sa propre autorisation (PA-0), accordée le 2026-11-23.
**Aucun fichier du jeu n'est traité avant PB-0** (`docs/J2_PLAN.md` §2). Il faut d'abord :
- PA-1 ;
- les contrôles du §6, exécutés et consignés ;
- la décision sur la méthode de validation des adresses (§3.3).

Ce sont des conditions d'exécution, et non un nouveau consentement.

## 3. Établir si le code du disque est celui du projet A

La configuration d'analyse du projet A (débuts de fonctions, pointeurs de code,
`setjmp`/`longjmp`, correctifs à adresses fixes) ne vaut que pour le code de son disque.
Avant de la réutiliser, il faut établir que le code du disque de l'utilisateur est le
même. Les étapes vont de la moins coûteuse à la plus probante.

### 3.1 Sans déchiffrement : disposition en mémoire (faite le 2026-11-22)

Le projet A publie trois valeurs de disposition dans `pc/config/default.toml` (BSD
3-Clause) [V]. Le rapport J0 de l'utilisateur contient les champs correspondants, lus en
clair [V].

| Valeur | Disque de l'utilisateur | Projet A | Résultat |
|---|---|---|---|
| Chargement de `default.xex` | `0x82000000` | `0x82000000` | Concordante |
| Fin de l'image de `default.xex` | `0x821F0000` (taille 2 031 616 octets, `0x1F0000`) | `0x821F0000` | Concordante |
| Chargement de `fifadllzf.xex` | `0x82300000` | `0x82300000` | Concordante |
| Taille de l'image de `fifadllzf.xex` | 25 493 504 octets (`0x1850000`), fin `0x83B50000` | Non publiée dans ce fichier | Non comparable [I] |

Contrôle complémentaire, sur les seules données publiques du projet A [V] : les 1 980
adresses de la configuration de `default.xex` et les 51 114 de celle de `fifadllzf.xex`
(débuts de fonctions, emplacements des pointeurs, crochets des deux correctifs du jeu)
tombent toutes dans l'image du module correspondant du disque de l'utilisateur
(`J0_IDENTIFICATION.md` §3.2).

**Portée** :

- c'est une condition **nécessaire, pas suffisante**. Une différence aurait suffi à
  écarter la configuration du projet A ; la concordance ne prouve ni un même code, ni la
  validité des adresses ;
- elle **ne vérifie pas** `function_table_base = 0x86100000`. Le placement de la table
  de répartition dépend d'autres contraintes du runtime (§5).

### 3.2 Avec l'image en clair : tests de compatibilité, puis validation des adresses

Avec O3, c'est ReXGlue qui déchiffre les modules, dès le contrôle de compatibilité. Ces
contrôles relèvent donc de la phase B du plan (`docs/J2_PLAN.md`) : ils n'ont lieu qu'après
PB-0, dans le dossier privé de l'utilisateur et sur sa machine. Le déchiffrement ne
prouve rien à lui seul. Il donne accès au code en clair, qui peut alors être comparé à ce
que le projet A a publié de son propre code.

**Contrôle de compatibilité (tests initiaux).** Il détecte une incompatibilité, mais ne
prouve pas l'identité du code :

1. génération de code de ReXGlue avec la configuration du projet A, sur les modules de
   l'utilisateur ;
2. critère C2.1 : 0 `UnresolvedCall` et 0 erreur de validation ;
3. contrôles ciblés :
   - `setjmp` et `longjmp` du projet A (`0x8283C680`, `0x8283C950`) désignent des
     fonctions de la forme attendue (`find_setjmp.py`) ;
   - les sites des correctifs du jeu (§5) contiennent les séquences d'instructions
     décrites dans leurs commentaires.

Un échec à ce contrôle écarte la réutilisation telle quelle : nouvelle analyse (§5). Un
succès **ne suffit pas** pour reprendre les milliers de pointeurs et d'adresses du projet
A. Un analyseur peut accepter une adresse fausse, et un pointeur faux peut ne produire
aucune erreur de génération.

**Validation des adresses, avant toute réutilisation.** Elle est exigée avant de
reprendre les 663 et 17 028 lignes de pointeurs, les débuts de fonctions et les adresses
des correctifs :

1. régénérer, avec les méthodes des outils du projet A, ses fichiers d'analyse à partir de
   l'image de l'utilisateur. La source de cette image reste à décider (§3.3) :
   - `find_code_pointers.py` pour `*_pointers.toml` ;
   - `autofix_codegen.py` pour les débuts de fonctions ;
   - `find_setjmp.py` pour `setjmp` et `longjmp` ;
2. exiger que les résultats régénérés soient **identiques** aux fichiers publiés par le
   projet A : mêmes adresses, et mêmes emplacements de données notés en commentaire ;
3. vérifier une à une les adresses écrites à la main, qu'aucun outil ne régénère :
   `boot_fixes.cpp` (fonction, registre et emplacement) et `lua_diagnostics.cpp`
   (`luaD_throw` et décalages des structures Lua), d'après le code désassemblé ;
4. au moindre écart, garder la sortie régénérée pour le disque de l'utilisateur, et non
   le fichier du projet A, puis reprendre l'analyse sur les points divergents.

Même identiques, les fichiers régénérés ne prouvent pas l'identité intégrale des images.
Ils établissent que la configuration d'analyse est valable pour ce disque, ce qui suffit
au projet. Une comparaison d'images complète demanderait l'empreinte de l'image en clair
du projet A, qui n'est pas publiée [I].

### 3.3 Source de l'image en clair pour les outils d'analyse (point à décider)

- **[V]** Les outils d'analyse du projet A lisent l'image en clair par `xeximage.load`,
  qui déchiffre avec une clé écrite dans `xeximage.py`. C'est le cas de
  `find_code_pointers.py`, `find_setjmp.py`, `autofix_codegen.py`, `ppcdis.py`, `xref.py`
  et `callers.py`. Seuls `disc.py` et `xexinfo.py` ne l'importent pas (lecture du dépôt du
  projet A, commit `498d18a`).
- **[V]** `xeximage.py` est exclu (D-008, D-010). La contrainte reformulée exclut aussi
  tout outil de déchiffrement propre au projet.
- **[V]** ReXGlue v0.11.0 n'a aucune commande qui écrive l'image décodée d'un module. Ses
  sous-commandes sont `init`, `codegen`, `vfs dump`, `list shim` et `recompile-tests`
  (lecture de `src/rexglue/command/`, sans exécution).

La validation des adresses ne peut donc pas utiliser les outils du projet A tels quels.
Pistes, **à décider avant la phase B**, sans en retenir aucune ici :

1. valider avec les seules sorties de la génération de code de ReXGlue : diagnostics,
   fonctions découvertes, erreurs de validation. Ce qu'elles exposent est à établir
   (`docs/J2_PLAN.md`, étapes A1 et A8) ;
2. faire lire aux outils du projet A une image obtenue par une fonction du SDK, appelée
   depuis un programme du projet. L'image décodée serait alors produite par du code du
   projet, même si le déchiffrement reste celui du SDK. Il faut une décision explicite
   pour dire si la contrainte reformulée le permet ;
3. réanalyser sans la configuration du projet A, avec les seules analyses de ReXGlue.

`xeximage.py` n'est pas une piste : il est exclu.

**Arbitrage du 2026-11-23 (D-015)** :
- la priorité va à la piste 1, à évaluer par lecture du code en A1 et A8 ;
- la piste 2 demanderait une dérogation explicite : aucun programme nouveau produisant
  une image décodée n'est autorisé implicitement ;
- la méthode est décidée après A8, avant PB-0.

Premiers constats sur la piste 1 : `docs/J2_A1_SDK_INVENTORY.md`.

## 4. Réutilisable sans nouvelle analyse du disque

| Élément | Origine | Pourquoi il ne dépend pas du disque | Statut |
|---|---|---|---|
| Chaîne de compilation, SDK, tests, CI, contrôles de données | Ce dépôt (J1) | Aucune donnée du jeu | [V] |
| Runtime ReXGlue, pilotes Vulkan, audio et entrées SDL3 | ReXGlue v0.11.0 | Indépendants du titre | [V] |
| Structure du manifeste : `default.xex` en point d'entrée, `fifadllzf.xex` chargé par son nom | Projet A, `pc/fifawc10_manifest.toml` | Les deux modules existent sous ces noms sur le disque de l'utilisateur, avec les mêmes adresses de chargement (§3.1) | [V] pour les noms et le chargement ; chemins à adapter au dossier privé |
| Bibliothèques importées : `xam.xex` et `xboxkrnl.exe`, version 2.0.9328.0, minimale 2.0.8955.0 | Rapport J0 | Ce sont les services système que ReXGlue fournit | [V] noms et versions ; la liste des fonctions importées n'est pas connue avant J2 [I] |
| Outils d'analyse en Python : `disc.py`, `xexinfo.py`, `ppcdis.py`, `find_code_pointers.py`, `find_setjmp.py`, `xref.py`, `callers.py`, `autofix_codegen.py` | Projet A, `tools/` | Ce sont des méthodes, pas des résultats ; elles s'appliquent à tout binaire, et servent aussi à la validation des adresses (§3.2) | [V] portables (audit) ; reprise avec notice (D-010). **Exclu** : `xeximage.py`, qui déchiffre (D-008). [V] Tous sauf `disc.py` et `xexinfo.py` chargent l'image par `xeximage.load` : ils ne sont réutilisables qu'avec une autre source de l'image, à décider (§3.3) |
| Correctifs du SDK sans adresse du jeu : 0001 (exports de la caméra USB), 0002 (module trouvé par son nom nu), 0004 (vblank), 0006 (cadence), 0007 (dialogues), 0008 (énumération des sauvegardes) | Projet A, `patches/rexglue-sdk/` | Ils modifient le SDK, pas le code du jeu | [V] sans adresse ; [H] encore utiles au même titre ; transposition vers v0.11.0 à faire (R-04, 338 commits d'écart). *A2 (2026-11-23) : 0001, 0004 et 0007 sont déjà en amont, et 0006 l'est en partie ; 0002 et 0008 restent nécessaires (`docs/J2_A2_SDK_PATCHES.md`)* |
| Réglages GPU : `execute_unclipped_draw_vs_on_cpu`, `gpu_allow_invalid_fetch_constants` | Projet A | Ils portent sur le rendu du moteur, pas sur des adresses | [H] valables pour le même moteur |
| Savoir : Lua avec `setjmp`/`longjmp` à rediriger, fil de décodage vidéo, exports de la caméra USB | Audit (`LINUX_FEASIBILITY.md` §2.3) | Propriétés du moteur du jeu | [H] mêmes besoins ; adresses à valider (§3.2) |
| Constats de J1 : `-DREXGLUE_LLD` vers le `ld.lld` enveloppé, RUNPATH, durcissement | `docs/reports/J1_VALIDATION.md` §6 | Propriétés de la chaîne de compilation | [V] |

## 5. À valider (§3.2) ou à refaire

| Élément du projet A | Valeur ou volume | Dépend de | Action |
|---|---|---|---|
| Débuts de fonctions ajoutés (`[functions]`, marqueur « autofix ») | Dans `pc/config/default.toml` et `fifadllzf.toml` | Adresses du code | Validation des adresses (§3.2) : régénérer selon la méthode d'`autofix_codegen.py`, comparer, garder la sortie régénérée |
| Pointeurs de code | 663 lignes (`default_pointers.toml`), 17 028 lignes (`fifadllzf_pointers.toml`) | Adresses du code et des données | Validation des adresses : régénérer selon la méthode de `find_code_pointers.py`, exiger l'identité |
| `setjmp_address`, `longjmp_address` | `0x8283C680`, `0x8283C950` | Adresses du CRT dans `fifadllzf.xex` | Contrôle de compatibilité, puis méthode de `find_setjmp.py` et vérification manuelle (validation des adresses) |
| `function_table_base` (correctif 0003) | `0x86100000` | La disposition des modules, concordante (§3.1), mais aussi des contraintes du runtime que les en-têtes ne donnent pas : taille de la table de répartition de chaque module, carte mémoire invitée de ReXGlue v0.11.0, autres réservations | **Non vérifiable par les seuls en-têtes.** À établir à J2 avec le runtime de v0.11.0, lors de la transposition du correctif 0003. *A1 (2026-11-23) : la clé n'existe pas en v0.11.0, qui place chaque table juste après son image. Pour `default.xex`, elle chevaucherait `fifadllzf.xex` si son code dépasse `0x78000` octets ; cette taille est inconnue (`docs/J2_A1_SDK_INVENTORY.md` §5.4)* |
| `pc/fixes/boot_fixes.cpp` | Crochet sur `sub_82CBD7E0`, registre en `0x83A4648C`, emplacement `0x64` | Adresses du code et des données | Validation des adresses : vérification manuelle ; si écart, retrouver la fonction et le registre équivalents et réécrire le crochet |
| `pc/fixes/lua_diagnostics.cpp` | Crochet sur `sub_829655A8` (`luaD_throw`), décalages de structures Lua | Adresse de la fonction ; disposition des structures de Lua | Validation des adresses : vérification manuelle ; les décalages sont propres à la version de Lua [H] |
| Valeurs du manifeste | Chemins `out/game-files`, `sdk_version = "0.10.0"` | Installation du projet A | Chemins vers le dossier privé (variable d'environnement), `sdk_version` de v0.11.0 |

Coût d'une nouvelle analyse, si le contrôle de compatibilité ou la validation des adresses
échoue : de quelques jours à quelques
semaines [H] (`ISO_REQUIREMENTS.md` §3, étape 6). Les outils du projet A la rendent
faisable sans réécrire de méthode.

## 6. Contrôles requis avant de traiter des fichiers du jeu

Ils conditionnent l'entrée en phase B du plan (`docs/J2_PLAN.md`). Chacun se vérifie par
des commandes ou une procédure écrite, et son résultat est consigné sans contenu
propriétaire. Ils sont répétés
après chaque étape de la phase B qui lit ou produit des données du jeu.

| N° | Contrôle | Vérification |
|---|---|---|
| CP-1 | **Confinement du dossier privé.** `$WC2010_PRIVATE_DIR` est défini et absolu. Il n'est ni dans le dépôt, ni dans `/nix/store`. Ses droits sont `0700`. Les sous-dossiers prévus existent, et `iso/` est en lecture seule (`ISO_REQUIREMENTS.md` §6) | `realpath`, `stat -c %a` ; `git -C "$WC2010_PRIVATE_DIR" rev-parse` doit échouer. Script à écrire en phase A (étape A4) |
| CP-2 | **Aucune entrée du jeu dans Nix.** Ni l'ISO, ni les XEX, ni un chemin du dossier privé ne sont une entrée du flake ou d'une dérivation. Les chemins sont donnés à l'exécution seulement | Lecture de `flake.nix` et de `nix/` ; `nix flake check` sur une copie propre, sans le dossier privé |
| CP-3 | **Magasin Nix vérifié avant et après.** Recherches de `docs/J0_ISO_IDENTIFICATION.md` §6, avec la procédure non destructive : constater, vérifier, conserver les preuves, ne rien supprimer sans décision explicite | **Aucune nouvelle correspondance suspecte imputable aux opérations du jeu.** Le magasin peut changer pour des raisons sans rapport avec le projet : les différences sont comparées et replacées dans leur contexte, sans rien supprimer. Le fichier `nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude` déjà relevé n'est pas examiné plus avant. Si rien ne change, on note simplement le résultat. Ces recherches sont limitées et non exhaustives (C0.4) |
| CP-4 | **Sorties, journaux et caches confinés.** Toute sortie de ReXGlue et des outils d'analyse est écrite sous `$WC2010_PRIVATE_DIR` : code généré, journal par `--log-file`, caches, fichiers temporaires | Un contrôle avant l'invocation, puis un contrôle après (§6.1). `git status --porcelain` n'en est qu'un complément |
| CP-5 | **Aucun contenu du jeu dans ce qui est partagé.** Un journal ou un rapport n'est partagé qu'après relecture. Il ne contient ni clé, ni vidage mémoire, ni code généré, ni chaînes ou ressources du jeu au-delà de quelques lignes de contexte | `check_proprietary_data.py tree` sur le dossier de ce qui est partagé, puis relecture ; aucun envoi en CI |
| CP-6 | **Dépôt protégé.** Le crochet de pré-commit est actif et le dépôt est propre | `git config core.hooksPath` vaut `.githooks` ; `check_proprietary_data.py repo` et `staged` passent |
| CP-7 | **Pas d'identité présumée avec le projet A.** Sa configuration n'est qu'une entrée de test tant que la validation des adresses (§3.2) n'est pas faite | Aucun fichier d'adresses du projet A n'est repris dans le dépôt avant cette validation |

### 6.1 CP-4 en détail : confinement des sorties

**Avant chaque invocation** :

1. **Lister toutes les destinations d'écriture de la commande** :
   - le dossier de sortie du code généré et le fichier `--log-file` ;
   - les caches et les fichiers temporaires ;
   - le répertoire de travail courant ;
   - les chemins relatifs du fichier de configuration.

   Ce que ReXGlue écrit, et où, est établi par l'inventaire A1, par lecture du code
   (`docs/J2_A1_SDK_INVENTORY.md` §3 et §6). Ce que le jeu lui-même écrit reste
   inconnu [I].
2. Résoudre chaque destination en **chemin canonique**, liens symboliques compris
   (`realpath -m`).
3. Exiger que chacune soit **sous `$WC2010_PRIVATE_DIR`**, dossier lui-même vérifié par
   CP-1.
4. Lancer la commande depuis un **répertoire de travail du dossier privé**. Diriger aussi
   vers des sous-dossiers du dossier privé :
   - `TMPDIR` ;
   - `XDG_CONFIG_HOME` : [V] le SDK y place le dossier de l'application quand celui de
     l'exécutable n'est pas inscriptible, et à défaut sous `~/.config`
     (`docs/J2_A1_SDK_INVENTORY.md` §2) ;
   - `XDG_DATA_HOME`, par précaution : [V] le SDK ne le lit que dans une fonction sans
     appelant ;
   - `XDG_CACHE_HOME`, par précaution ;
   - `REX_APP_ROOT`, pour le dossier de l'application de ReXGlue (journaux, `user`,
     réglages) : [V] essai sans données du jeu (`docs/J2_A1_SDK_INVENTORY.md` §2).
5. Vérifier aussi les autres mesures relevées par l'inventaire A1
   (`docs/J2_A1_SDK_INVENTORY.md` §6) :
   - aucun `rexglue.toml` parasite ;
   - aucune exécution en root ;
   - masque `077` ;
   - `ulimit -c 0` ;
   - aucun `.xexp` imprévu ;
   - un dossier de sortie dédié.

**Après chaque invocation** :

1. Juste avant l'invocation, **créer un fichier repère** dans le dossier privé.
2. Ensuite, rechercher les **fichiers créés ou modifiés depuis ce repère** dans les
   emplacements surveillés hors du dossier privé :
   - le dépôt ;
   - le répertoire personnel, dont `~/.local/share`, `~/.config` et `~/.cache` ;
   - `/tmp` et le `TMPDIR` d'origine ;
   - `/dev/shm`, où aucun objet `xenia_memory_*` ne doit rester après l'arrêt ;
   - le chemin du SDK dans le magasin, avec `nix store verify` ;
   - les *core dumps* (`coredumpctl list`, si systemd-coredump est actif).

   Commande type, pour chaque emplacement :
   `find <emplacement> -xdev -newer <repère> -type f -not -path "$WC2010_PRIVATE_DIR/*"`.
3. Un fichier trouvé est **examiné localement, sans être partagé**. S'il peut contenir
   des données du jeu, l'étape s'arrête (arrêt immédiat de `docs/J2_PLAN.md` §2). Il n'est
   supprimé qu'après une décision explicite.
4. `git status --porcelain`, qui ne doit montrer aucun fichier nouveau, complète ce
   contrôle. Il ne suffit pas : il n'inspecte que le dépôt.

**Limite** : ces contrôles couvrent les destinations déclarées et les emplacements
surveillés. Ils ne prouvent pas qu'aucune sortie n'a été écrite ailleurs. Le script qui
les automatise est à réaliser à l'étape A4 du plan.

## 7. Plan de J2

Le plan d'exécution est dans `docs/J2_PLAN.md`. Il a deux phases séparées :

- **phase A** : préparations génériques, sans données du jeu ;
- **phase B** : traitement local des données privées, seulement après PB-0, c'est-à-dire
  PA-1, les contrôles du §6 et la méthode de validation des adresses.

Le plan seul n'autorise aucune exécution.

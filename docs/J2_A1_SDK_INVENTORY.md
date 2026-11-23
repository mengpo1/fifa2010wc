# J2, étape A1 — Inventaire de ce que fournit ReXGlue v0.11.0

> Étape A1 de `docs/J2_PLAN.md` (§3.1), ticket [#14](https://github.com/mengpo1/fifa2010wc/issues/14).
> Réalisée le 2026-11-23, sous l'autorisation PA-0 (D-015). **Phase A : aucune donnée du
> jeu.** Aucun XEX ni fichier du jeu n'a été lu, demandé ni produit. Rien n'a été
> déchiffré, et aucun code du jeu n'a été généré. Aucune valeur de clé n'est reproduite.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Méthode et limites

**Source.** Le code public de ReXGlue v0.11.0, à la révision épinglée par `flake.lock`
(`a3e1d82`). Les références `fichier:ligne` sont relatives à la racine de cette source.

**Lecture.** Claude Code l'a lue avec deux agents de recherche en lecture seule. Ont été
relus ligne par ligne :
- la mémoire partagée de l'invité (§4.3) ;
- le journal par défaut (§2) ;
- le dossier de l'application (§2) ;
- les clés de configuration (§5.3) ;
- la table des fonctions (§5.4) ;
- l'ordre d'application des réglages (§2).

**Essais sans données du jeu.** Ils ont été faits dans le conteneur de Claude Code, avec
un dossier personnel isolé (`HOME`, `XDG_CONFIG_HOME`) :
1. `rexglue --help` et l'aide de chaque sous-commande : aucun fichier n'est écrit ;
2. `rexglue codegen` sur un manifeste synthétique qui désigne un XEX absent : échec
   immédiat (« Entrypoint XEX not found »), aucun fichier écrit ;
3. `rexglue vfs dump` sur une **image XDVDFS synthétique**. Elle est fabriquée par les
   fonctions de test de J0 (`tools/test_iso_identify.py`) et ne contient que deux
   fichiers texte. Ces essais montrent où l'application écrit vraiment (§2, §6).

**Limites.**
- Les bibliothèques tierces n'ont pas été auditées : spdlog, SDL3, chargeur Vulkan,
  pilotes GPU, FFmpeg.
- Ce que le jeu lui-même journalise ou écrit n'est connaissable qu'en phase B [I].

**Incident pendant l'essai 3.**
- Le conteneur tourne en root, et son magasin Nix y est accessible en écriture. Le
  premier lancement a donc écrit son journal **dans le chemin du SDK du magasin** :
  `…-rexglue-sdk-0.11.0/bin/logs/rexglue_001.log`.
- Le contenu était synthétique : uniquement les lignes de chargement des modules du SDK.
- Le fichier a été copié comme preuve, puis supprimé. `nix store verify` du chemin
  passe de nouveau.
- La cause et la parade sont au §2. La même chose s'est produite une seconde fois, lors
  d'un essai sans redirection du journal ; même nettoyage, même vérification.

## 2. Services de plateforme Linux déjà fournis

Ces services existent : le projet ne les réécrit pas.

| Service | Ce que fait ReXGlue | Référence | Statut |
|---|---|---|---|
| Dossier de l'application (`app.root`) | Le dossier de l'exécutable s'il est inscriptible et que ce n'est pas une AppImage. Sinon `$XDG_CONFIG_HOME/<app>`, à défaut `~/.config/<app>`. Le test d'écriture crée puis supprime `.rex_write_check_<pid>_<n>` dans le dossier de l'exécutable | `src/base/platform/file.cpp:43-49`, `src/base/platform/file_posix.cpp:107-139` | [V] Fourni |
| Dossier de configuration de l'utilisateur | `GetUserConfigFolder(nom)` : `$XDG_CONFIG_HOME/<nom>`, à défaut `~/.config/<nom>` | `file_posix.cpp:107-122` | [V] Fourni |
| Dossier de données XDG | `GetUserFolder` suit `XDG_DATA_HOME`, à défaut `~/.local/share`. **Aucun appel dans `src/`** | `file_posix.cpp:88-94` ; grep | [V] Fourni, inutilisé |
| `XDG_CACHE_HOME`, `XDG_STATE_HOME` | Jamais lus | grep sur `src/` | [V] Absents |
| Chemins réglables | `app.root`, `app.log_root` (`{app.root}/logs`), `app.config_file` (`{app.root}/{app.name}.toml`), `app.user_root` (`{app.root}/user`), `app.cache_root` (vide), `title.game_root`, `title.game_writable` (`false`), `title.update_root`, `title.metadata_root`, `title.entry` (`default.xex`) | `include/rex/app/app.h:75-81`, `include/rex/path_settings.h:25-30`, `include/rex/kernel/title_paths.h:23-35` | [V] Fourni |
| Réglages | Couches par priorité croissante : défaut, titre, fichier TOML, environnement (`REX_<PORTÉE>_<NOM>`), ligne de commande (`--portée.nom=…`). **Le fichier TOML est lu avant l'environnement** : `REX_APP_CONFIG_FILE` est sans effet | `include/rex/setting.h:50-58`, `src/base/settings/settings_registry.cpp:26-32`, `src/app/app.cpp:362-409`, `docs/site/pages/app/settings.md:143` | [V] Fourni |
| Journal | Console et fichier. **Le fichier est créé par défaut** (`log.file = true`), sous `app.log_root`, au nom `<app>_NNN.log`. **Les anciens fichiers sont tous gardés** (`log.folder_budget = 0`). Niveau par défaut `info` | `include/rex/logging/logger.h:218-232`, `src/base/log_file.cpp:80-93`, `src/app/app.cpp:406-409` | [V] Fourni |
| Rapport de plantage | Signaux SIGSEGV, SIGILL, SIGBUS, SIGFPE et SIGABRT, pile de secours, écriture par `write(2)` sur stderr et dans le journal. Pas de fichier de vidage. Le signal est relevé ensuite, et le système décide d'un éventuel *core dump* | `src/base/crash_posix.cpp:45-49,229-240,330-338,366-387`, `src/base/crash.cpp:85-143` | [V] Fourni |
| Arrêt propre | Un fil dédié attend SIGINT et SIGTERM (`sigwait`), puis demande l'arrêt. SIGHUP et SIGQUIT ne sont pas traités | `src/app/lifecycle.cpp:67-81,125-164` | [V] Fourni |
| Autres | Verrou d'instance (désactivé par défaut), relance, hausse de la limite de fichiers ouverts, écriture atomique (`<fichier>.tmp` puis renommage) | `src/base/instance_lock_posix.cpp:33-49`, `src/base/relaunch_posix.cpp:27-60`, `src/app/app.cpp:56-73`, `src/base/platform/file.cpp:98-127` | [V] Fourni |

**Conséquence sous NixOS** :
- un exécutable du magasin n'a normalement pas le droit d'écrire à côté de lui. Il
  range alors configuration, journaux et sauvegardes sous `~/.config/<app>` [V code ;
  [H] sur la machine de l'utilisateur, où le magasin est censé être en lecture seule] ;
- **lancé en root sur un magasin inscriptible, il écrit dans le magasin** [V essai 3].

**Redirections vérifiées à l'essai 3** :

| Réglage, par l'environnement | Effet constaté | Magasin |
|---|---|---|
| Aucun, en root | Journal dans `…/bin/logs/` du SDK | **Modifié** |
| `REX_APP_ROOT=<privé>/app` | Journal dans `<privé>/app/logs/rexglue_001.log` | Intact (`nix store verify`) |
| `REX_APP_LOG_ROOT=<privé>/logs` | Journal dans `<privé>/logs/` | Intact |
| `REX_LOG_FILE=false` | Aucun fichier journal | Intact |

Dans tous les cas, en root, le test d'écriture touche le dossier `bin` du SDK, ce que
trahit sa date de modification. Il n'y laisse aucun fichier.

## 3. Ce que lisent et écrivent les commandes `rexglue`

### 3.1 `rexglue codegen`

**Manifeste et chemins** [V] :
- le manifeste est l'argument donné, ou bien l'unique `*_manifest.toml` du dossier
  courant, ou encore l'unique `.toml` (`src/rexglue/command/codegen_command.cpp:137-178`) ;
- tous les chemins (`file_path`, `game_root`, `out_directory_path`, `hook_sources`,
  `template_dir`) se résolvent **par rapport au dossier du manifeste**, et non au
  dossier courant (`src/codegen/manifest.cpp:77`, `src/codegen/project_recompiler.cpp:285-392`) ;
- les `includes` se résolvent par rapport au fichier qui les contient ;
- `game_root` vaut par défaut le dossier du XEX d'entrée. Tous les modules doivent s'y
  trouver.

**Écritures** [V] :
- Dans le dossier de sortie, par module : `<préfixe>_pch.h`, `_funcs.h`, `_init.h`,
  `_init.cpp`, `_register.cpp`, `_funcs.N.h`, `_recomp.N.cpp`, `codegen.partition.json`,
  `codegen.mmio.json`, `sources.cmake` et `codegen.stamp`
  (`src/codegen/codegen_writer.cpp:306-430`).
- Dans le dossier du module d'entrée :
  - `codegen.d`, qui liste les **chemins absolus** du XEX, du manifeste et des sources
    (`src/codegen/output_stamp.cpp:91-118`) ;
  - `codegen.build.stamp` ;
  - `module_registry.cpp` et `dll_targets.cmake`, si le manifeste déclare des modules.
- **Le manifeste lui-même est réécrit** à chaque génération réussie : `[project].sdk_version`
  y est inscrit (`codegen_command.cpp:207`, `manifest.cpp:204-261`).
- **Suppressions** : dans le dossier de sortie, tout fichier dont le nom ressemble à une
  sortie, et que la génération n'a pas produit, est supprimé (`codegen_writer.cpp:131-179,471-488`).
  Le dossier de sortie doit donc être dédié.
- Écritures atomiques : fichier `.tmp` dans le même dossier, puis renommage.
- **Le code généré est une traduction complète du code du jeu**, avec la désassemblée de
  chaque instruction en commentaire (`src/codegen/function_graph.cpp:643-647`). Il
  n'embarque pas les données en lecture seule du jeu. Il est privé (D-007).
- La génération démarre l'application de ReXGlue, avec les mêmes effets que le runtime :
  - journal (§2) ;
  - mémoire partagée de l'invité, qui contient l'**image décodée** (§4.3) ;
  - pendant la génération, `user_root` vaut `{title.game_root}`
    (`src/codegen/tool_runtime.cpp:47`). Un fichier d'exploits à l'ancien format sous
    `game_root/achievements/` peut alors être réécrit
    (`src/xam/achievement_manager.cpp:185-238`) ;
  - aucun cache GPU : les pilotes graphique, audio, d'entrées et d'interface sont
    `none` (`tool_runtime.cpp:51-54`).
- Aucun chemin de code n'écrit l'image décodée dans un fichier ordinaire (grep sur toutes
  les écritures de `src/`).

**Lectures** [V] :
- le XEX d'entrée et les modules ciblés ;
- **un `.xexp` placé à côté d'un XEX, appliqué automatiquement**. Il n'entre pas dans
  l'empreinte de `codegen.stamp` : en ajouter un ne déclenche pas de régénération
  (`src/kernel/user_module.cpp:141-161`) ;
- l'arborescence entière de `game_root`, pour ses métadonnées (montage) ;
- un fichier d'exploits trouvé près de `game_root` ;
- les sources de crochets et les gabarits ;
- **`{app.root}/rexglue.toml`, s'il existe** (`src/app/app.cpp:396-403`).

### 3.2 `rexglue init`

- **`init`** [V] :
  - ne lit pas le XEX : il vérifie seulement qu'il existe ;
  - écrit `CMakeLists.txt`, `CMakePresets.json`, qui contient le **chemin absolu du SDK**,
    `<nom>_manifest.toml`, `src/main.cpp` et `src/<nom>_hooks.cpp`
    (`src/rexglue/command/init_command.cpp:48-89,136-147,246-295`) ;
  - ne démarre pas l'application : ni journal, ni mémoire partagée.
- **`init module`** [V] : ajoute un bloc `[[modules]]` au manifeste, sans lire le XEX.
- **`init achievements`** [V] :
  - décode le XEX ;
  - écrit `achievements.toml` et des icônes PNG **dans le dossier du XEX par défaut**
    (`init_command.cpp:388-389,443-520`) ;
  - ce fichier alimente ensuite chaque génération. **Il n'est pas prévu dans le plan.**

### 3.3 `rexglue vfs dump`

[V] Il ouvre le conteneur, puis l'extrait (`src/rexglue/command/vfs_command.cpp:43-65`),
sans appel au décodage des XEX.
- Essai 3 : 4 nœuds extraits de l'image synthétique.
- Aucun objet n'a été créé dans `/dev/shm`.
- L'application démarre, et son journal suit le §2.

## 4. Journalisation et mémoire pendant le décodage et l'analyse

### 4.1 Non trouvé dans les chemins d'exécution du SDK examinés [V]

Ce constat est **limité au code de ReXGlue lu pour cet inventaire**. Les bibliothèques
tierces et le jeu lui-même n'ont pas été examinés (§1, §9). Il ne dispense donc d'aucune
relecture : CP-5 exige que **tout journal** soit relu localement avant d'être partagé.

Dans les chemins examinés, il n'a été trouvé :
- aucune clé journalisée : ni maîtresse, ni de session, ni de fichier ;
- aucun octet de l'image journalisé. Le décodage est une boucle en mémoire sans journal
  (`src/filesystem/xex.cpp:313-339`). Sa seule ligne de journal signale une empreinte de
  correctif discordante (`xex.cpp:477`) ;
- côté chargeur, rien d'autre que le **type** de clé, sous forme d'indice, et seulement
  s'il n'est pas « retail » (`src/kernel/xex_module.cpp:242-244`) ;
- aucune fonction de vidage hexadécimal dans `src/`.

### 4.2 Ce qui peut venir du jeu dans les sorties [V]

| Sortie | Contenu possible |
|---|---|
| stderr, sans le journal | Nom du XEX, identifiants du titre et du média, version, horodatage PE (`src/rexglue/ui/progress.cpp:77-94`) |
| `info`, le niveau par défaut | Versions d'un correctif `.xexp`, bilan de génération, chemins des modules, nom du GPU |
| `warn` | **Mots d'instruction bruts** non décodables (`function_graph.cpp:644-646`), adresses du rapport d'erreurs, avertissements de configuration |
| `debug` et `trace` | **Noms de classes RTTI**, noms de sections, noms d'imports et d'exports, contenu des tables de sauts, chemins complets |
| Rapport de plantage | Registres en hexadécimal, adresses de la pile, pile d'appels. Pas de vidage mémoire ; une valeur de registre peut contenir une donnée [I] |

Conséquence pour CP-5 : on ne partage aucun journal de niveau `debug` ou `trace`. Un
journal `info` ou `warn` n'est partagé qu'après relecture : il peut contenir des
adresses et des mots d'instruction.

### 4.3 Mémoire de l'invité dans `/dev/shm` [V]

- **Création** : toute la mémoire de l'invité est un objet de mémoire partagée POSIX,
  d'environ 4,5 Gio, alloué de façon creuse. Il est créé par
  `shm_open("/xenia_memory_<pid>_<aléa>", O_CREAT|O_EXCL, 0777)`
  (`src/base/memory_posix.cpp:336-391`, `src/kernel/memory.cpp:58,232-245`).
- **Contenu** : l'image décodée de chaque module y est recopiée
  (`src/kernel/xex_module.cpp:236-238,266-271`).
- **Droits** : `0777` moins le masque du processus. Avec le masque usuel `022`, l'objet
  est lisible par tous les utilisateurs de la machine [I selon le masque].
- **Durée de vie** : l'objet est supprimé à l'arrêt. Après un plantage, il reste jusqu'au
  prochain lancement, qui efface ceux dont le processus n'existe plus
  (`memory_posix.cpp:393-423`).
- **Core dump** : le SDK ne désactive pas les fichiers *core*. Il ne touche ni
  `RLIMIT_CORE`, ni `PR_SET_DUMPABLE`, ni `MADV_DONTDUMP` (grep). Un *core dump* pourrait
  contenir l'image décodée [I selon la configuration du système].

## 5. Ce qu'expose la génération de code pour valider des adresses

C'est la première piste du `J2_PREREQUISITES.md` §3.3, prioritaire selon D-015. **Ce
sont des constats pour A8, pas une décision de méthode.**

### 5.1 Erreurs et refus [V]

- Il n'y a que deux catégories d'erreurs d'analyse : `UnresolvedCall` et `Millicode`
  (`src/codegen/analysis_error_log.h:22-26`).
- Le rapport liste chaque erreur sous la forme « `0xCIBLE from 0xSITE: message` », puis
  un total (`src/codegen/analyze.cpp:103-128`).
- Une erreur dans un module arrête la génération **avant toute écriture**
  (`project_recompiler.cpp:534-552`).
- `-f`/`--force` change les erreurs en avertissements, et le code émis contient alors un
  arrêt fatal à chaque appel non résolu (`src/codegen/builder/context.cpp:341-398`).

### 5.2 Listes d'adresses produites [V]

- `<préfixe>_init.cpp` : la table `kPPCFuncMappings` donne l'adresse et le nom de
  **chaque** fonction générée (gabarit `resources/templates/codegen/init_cpp.inja`).
- `codegen.partition.json` : une adresse par fonction émise, imports et cales exclus
  (`src/codegen/output_partition.cpp:76-89`).
- `codegen.mmio.json` : adresses des fonctions et des accès MMIO.
- Les nombres de fonctions, de tables de sauts et de vtables ne sont journalisés qu'en
  `debug` ou `trace`. Atteindre le plafond d'itérations de découverte ne produit aucun
  message (`src/codegen/phase_discover.cpp:187-203`).

### 5.3 Validation des entrées de configuration [V]

| Section | Contrôles |
|---|---|
| `[functions]`, clés hexadécimales | Clé ou valeur invalide : erreur, et l'entrée est ignorée. Fatal : adresse non alignée sur 4 octets, chevauchement, entrée sur du *millicode*. Avertissements « not a function entry point », « outranked by », « split by », « not in any code region » et « no blocks found », puis un corps factice est émis (`src/codegen/config.cpp:221-265,736-779`, `src/codegen/phase_validate.cpp:48-82`, `phase_discover.cpp:77-96`). **Non contrôlé** : une adresse au milieu d'une fonction connue des données d'exception |
| `setjmp_address`, `longjmp_address` | **Alignement seulement** (`config.cpp:652-660`) |
| `[[switch_tables]]`, `[[midasm_hook]]`, `[[invalid_instructions]]`, `[mmio]`, `[shim]` | Champs requis, registres, alignement ; une entrée `[mmio]` doit correspondre à un accès réel (`config.cpp:267-420,665-808`, `codegen_writer.cpp:288-296,365-385`) |
| Clé inconnue | **Avertissement seulement** (`src/codegen/config_keys.cpp:149-161`) |

**Compatibilité avec la configuration du projet A** [V] :
- ses fichiers `*_pointers.toml` sont des entrées `[functions]`, clé reconnue par
  v0.11.0. Ce sont des débuts de fonctions atteintes seulement par des pointeurs ;
- **`function_table_base` n'existe pas en v0.11.0** : la clé est seulement signalée
  comme inconnue, puis ignorée. Aucune clé de ce nom n'existe dans `src/codegen/`.

### 5.4 Table des fonctions en v0.11.0 [V]

`InitializeFunctionTable` place la table de chaque module juste après son image
(`src/kernel/memory.cpp:778-806`) :
- base : `image_base + image_size` ;
- taille : `(code_size + 0x10000) × 2`, où `0x10000` est la réserve de thunks
  (`include/rex/kernel/function_dispatcher.h:95`) ;
- échec de l'allocation : erreur fatale. *Précision d'A3 : l'allocation ne refuse pas
  des pages déjà réservées, elle les reprend (`docs/J2_A3_FUNCTION_TABLE.md` §4.2).*

Pour le disque de l'utilisateur :
- la table de `default.xex` commencerait à `0x821F0000` ;
- `fifadllzf.xex` est chargé à `0x82300000`, soit `0x110000` plus loin ;
- les deux se chevauchent si la taille du code de `default.xex` dépasse `0x78000`
  octets.

Cette taille est **inconnue** [I] : la taille de l'image, `0x1F0000`, ne la donne pas.
Le correctif 0003 est donc probablement encore nécessaire [H]. Il faudra le transposer
avec une nouvelle clé ou un autre mécanisme, à établir en A3. *Traité en A3 :
`docs/J2_A3_FUNCTION_TABLE.md`.*

### 5.5 Premiers constats pour A8 [H]

La piste 1 semble pouvoir couvrir une partie de la validation, **sans programme
nouveau produisant une image** :
- **débuts de fonctions** :
  - générer d'abord sans la configuration du projet A ;
  - comparer les adresses de `kPPCFuncMappings` ou de `codegen.partition.json` aux
    débuts de fonctions et aux pointeurs du projet A ;
  - puis générer avec cette configuration, et relever ses avertissements par entrée ;
- **`setjmp`, `longjmp` et sites des correctifs du jeu** : lire la désassemblée en
  commentaire dans le code généré, qui reste privé.

Limites :
- **les adresses de données** ne sont pas couvertes, car le code généré n'embarque pas
  les données. C'est le cas du registre de `boot_fixes.cpp` et des décalages des
  structures Lua ;
- les outils du projet A ne s'appliquent pas tels quels.

A8 doit chiffrer ces limites.

## 6. Exigences pour les contrôles CP-1 à CP-5

Ces destinations s'ajoutent à celles du `J2_PREREQUISITES.md` §6.1.

Les mesures ci-dessous sont **proposées**, et **aucune n'est encore vérifiée sur la
machine de l'utilisateur**. Seules les redirections `REX_APP_ROOT`, `REX_APP_LOG_ROOT` et
`REX_LOG_FILE` ont été essayées, dans le conteneur et sur des données synthétiques (§2).
Le masque `077` et `ulimit -c 0` réduisent le risque de l'objet `/dev/shm` et des *core
dumps*, sans le supprimer : ce risque reste **sensible** (§4.3).

| Destination ou risque | Mesure avant l'invocation | Contrôle après l'invocation |
|---|---|---|
| Dossier de l'application (journal, `user`, réglages) | `REX_APP_ROOT=$WC2010_PRIVATE_DIR/app`, ou au minimum `REX_APP_LOG_ROOT` dans le dossier privé ; essai 3 | Aucun nouveau fichier sous `~/.config/rexglue` ni à côté de l'exécutable |
| Fichier de réglages lu avant l'environnement | Vérifier l'absence de `~/.config/rexglue/rexglue.toml`, et de `rexglue.toml` à côté de l'exécutable | — |
| Magasin Nix | **Ne jamais lancer `rexglue` ni le jeu en root** ; magasin en lecture seule | `nix store verify` du chemin du SDK |
| Manifeste réécrit, `codegen.d` avec chemins absolus | Manifeste d'instance dans le dossier privé ; le dépôt n'en garde qu'un gabarit (A5) | `git status --porcelain` |
| Dossier de sortie, dont les fichiers « générés » sont supprimés | Dossier dédié sous `$WC2010_PRIVATE_DIR/generated` | — |
| `.xexp` appliqué automatiquement | Vérifier qu'aucun `.xexp` n'est à côté des XEX, sauf décision explicite | Liste des fichiers de `game_root` inchangée |
| Fichier d'exploits sous `game_root` | `game_root` dans le dossier privé, ISO en lecture seule | Empreintes des XEX et de l'ISO inchangées |
| `init achievements` | Non utilisé ; sinon, une sortie dans le dossier privé | — |
| `/dev/shm/xenia_memory_*`, image décodée | Masque `077` pour le processus | Aucun objet `xenia_memory_*` restant après l'arrêt |
| *Core dump* | `ulimit -c 0` pour toute exécution sur les fichiers du jeu | Aucun nouveau *core* (`coredumpctl list`, si systemd-coredump est actif [H]) |
| Journaux partagés | Niveau `info` au plus | Relecture et `check_proprietary_data.py tree` (CP-5) |

## 7. Lacunes et suites

| Lacune ou point | Étape |
|---|---|
| Rien à réécrire pour les chemins, les journaux, les plantages et l'arrêt sur signal : la couche `platform/linux` ne fait que **régler** les chemins de ReXGlue, par exemple vers les dossiers XDG ou le dossier privé | A6 (A5 pour le gabarit) |
| Masque `077`, `ulimit -c 0`, refus du root, variables `REX_*` : ce sont des mesures d'enveloppe, qui ne demandent aucun correctif du SDK | A4 (contrôles), A6 (enveloppe) |
| `log.folder_budget = 0` garde tous les journaux | A5 (réglage du gabarit) |
| `function_table_base` absent, chevauchement possible des tables | A3 |
| Transposer 0001, 0002 et 0004 à 0008 : besoin à confirmer correctif par correctif | A2 |
| Méthode de validation des adresses : constats du §5.5 | A8 |
| Essai de la chaîne sans le jeu : `recompile-tests` part d'assembleur PowerPC (`--bin-dir`, `--asm-dir`) et demande une chaîne de compilation PowerPC [I] | A7 |

## 8. Variables d'environnement lues par le SDK [V]

| Variable | Rôle |
|---|---|
| `REX_<PORTÉE>_<NOM>` | Chaque réglage enregistré : par exemple `REX_APP_ROOT`, `REX_APP_LOG_ROOT`, `REX_LOG_FILE` ou `REX_LOG_LEVEL` |
| `HOME` | Dossier personnel |
| `XDG_CONFIG_HOME` | Dossier de configuration |
| `XDG_DATA_HOME` | Lu seulement par `GetUserFolder`, qui n'a aucun appelant |
| `XDG_RUNTIME_DIR` | Verrou d'instance |
| `XDG_CURRENT_DESKTOP`, `GAMESCOPE_WAYLAND_DISPLAY` | Relance autorisée ou non |
| `APPIMAGE` | Application empaquetée |
| `NO_COLOR` | Outil `rexglue` seulement |

## 9. Points ouverts

1. Le masque de processus, la politique *core dump* et l'éventuel passage de `/dev/shm`
   en mémoire d'échange, sur la machine de l'utilisateur [I].
2. Le montage du magasin Nix en lecture seule sur sa machine [H].
3. Ce que le jeu journalise, et les avertissements produits par sa génération de code
   (phase B) [I].
4. Le comportement des bibliothèques tierces : SDL3, chargeur Vulkan, caches de shaders
   des pilotes sous `~/.cache`, FFmpeg [I].
5. Le traitement d'une adresse configurée au milieu d'une fonction : aucun contrôle
   explicite n'existe, et l'effet dépend de la fusion du graphe [I].

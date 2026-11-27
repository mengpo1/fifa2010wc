# Étape B2 — contrôle de compatibilité : proposition de procédure

> Étape B2 de `docs/J2_PLAN.md` §4.2. Version 3, **proposée à la revue** :
> - la version 2 répond à la revue ciblée de la PR #35 (commentaire 7220519596) ;
> - la version 3 applique les arbitrages du porteur C-a, F-a, T-a et L-a (**D-021**). Elle
>   constate un **conflit entre C-a et F-a**, soumis à un arbitrage distinct (§11.5).
> **B2 n'est pas autorisée** : PB-1 est franchi (D-020), mais B2 reste soumise à un mandat
> distinct. Rien ici n'a lu, décodé ni généré quoi que ce soit du jeu.
> - L'outil est `tools/b2_codegen.py`, empaqueté par le flake (`.#b2-codegen`). C'est le
>   **profil B2 du moteur d'étapes de B1** (`docs/J2_LOCAL_STEP_ENGINE.md`), pas un nouvel
>   outil de confinement.
> - Les essais n'utilisent que des fichiers synthétiques (§10).
> - B2 s'exécutera à la main, **sur la machine du porteur seulement**, après le mandat.
> - PB-2 est décidé par l'orchestrateur, puis le porteur, sur les résultats locaux.
>
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue. Les références
> `fichier:ligne` désignent les sources de ReXGlue v0.11.0 construites par le flake, avec
> le correctif A3.

## 1. Ce que fait B2, et ce qu'elle ne fait pas

**Action** (plan §4.2) : une première génération de code par ReXGlue, sur les deux modules
extraits à B1, avec la configuration du projet A comme **simple entrée de test**.
- ReXGlue décode les modules en mémoire. C'est le **premier déchiffrement du projet**, par
  la voie O3 (D-008) : le SDK amont seul, localement.
- Le code généré va dans `$WC2010_PRIVATE_DIR/generated`. C'est une traduction complète
  du code du jeu : il reste privé (D-007).

**Critères** :
- **C2.1** : 0 `UnresolvedCall`, 0 erreur de validation, lus dans un journal complet
  (§6.1, §6.2) ;
- **complétude de la génération**, distincte de C2.1 : chaque module a ses sorties, toutes
  présentes, et rien d'autre (§6.3) ;
- **contrôles ciblés** : `setjmp` et `longjmp`, sites des correctifs du jeu, par la
  méthode M1 et le comparateur A8-bis (§7).

**Point d'arrêt PB-2** (§8) : un échec écarte la réutilisation telle quelle de la
configuration du projet A ; un succès ne prouve pas l'identité du code.

**Ce que B2 ne fait pas** :
- ni validation des adresses : c'est B3 ;
- ni versionnement d'une adresse : c'est PB-3 ;
- ni édition de liens : c'est B5 ;
- jamais `-f`/`--force`, qui ferait passer outre les erreurs de validation ;
- jamais de niveau de journal `debug` ou `trace` (`J2_A1_SDK_INVENTORY.md` §4.2).

**À savoir** [V] : les SHA-256 des deux modules de l'utilisateur **diffèrent** de ceux du
projet A (`J2_PREREQUISITES.md` §1). Un échec de B2 est donc possible ; il ne serait pas
un défaut de la procédure.

## 2. Ce qui est repris de B1, sans duplication

| Mécanisme | Repris de | Ce qui change pour B2 |
|---|---|---|
| CP-1, composants et parents du dossier privé, sockets et tubes | Moteur (`b1_extract.py`) | Composants en plus : `generated/`, `project/`, `project/config/` |
| Fermeture du magasin (D-019) | Moteur, `b1-closure` du flake | Rien : ce qui tourne dans le bac à sable est le même (Python, le SDK, le moteur) |
| Bac à sable par liste positive | Moteur | **`game/` et `project/config/` en lecture seule**. Inscriptibles : le dossier d'exécution, `generated/`, `project/`, `app/`, `tmp/` (§5.1) |
| Sonde de confinement | Moteur | 30 contrôles au lieu de 26 : `write-denied-game`, `write-denied-project-config`, `writable-generated`, `writable-project`, `shm-private` (§5.1) |
| *Core dumps*, option B (D-018) | Moteur | Rien : limite `1` pour `codegen`. La preuve est liée au profil : **il faut une répétition de B2**, celle de B1 ne vaut pas |
| Montages, CP-3, `preflight`, `postflight` (CP-4), état, reprise, `diagnose` | Moteur | Le repère est `b2.marker`, les dossiers `logs/b2-run-<date>` et `logs/b2-rehearse-<date>` |
| Résumé par liste fixe | Moteur | Faits et codes de B2 ajoutés à la liste (§6.4) |
| Parcours d'une arborescence (`survey_tree`) | Moteur | Le même parcours, avec un **inventaire** optionnel : contenu haché, métadonnées et identité de chaque entrée (§5.2). B1 l'appelle sans, et ses chiffres ne changent pas |
| Manifeste et dossiers de sortie | `private_project.py` (A5) | Appelé tel quel (`check_manifest`) |
| Mesure de C2.1 dans le journal | `address_compare.py` (A8-bis) | `parse_log`, avec l'option `completed` : après un code 0, un journal vide ou tronqué est refusé (§6.2) |
| Contrôles ciblés | `address_compare.py` (A8-bis) | Lancé ensuite par le porteur (§7) |

Ce qui est propre à B2 tient dans `tools/b2_codegen.py` : ses contrôles d'entrée, la
commande `codegen`, ses contrôles d'après et ses lignes de résumé.

## 3. Entrées

### 3.1 `game/`

L'arborescence extraite et validée à B1 (D-020). B2 ne la modifie pas.
- Avant et après, l'outil vérifie ses 49 fichiers, ses 8 dossiers, l'absence d'anomalie
  et les empreintes des deux modules, contre la référence J0.
- Juste avant le repère, puis après la génération, il en prend l'**inventaire** (§5.2) :
  les deux doivent être identiques (`game-changed` sinon).

### 3.2 Le manifeste et les entrées de configuration

`codegen` consomme ces entrées [V, par lecture des sources] :

| Entrée | Résolution par ReXGlue | Exigence de B2 |
|---|---|---|
| `project/wc2010_manifest.toml` | Argument de la commande | `private_project.check_manifest` ; un fichier ordinaire. Il ne peut changer que par sa ligne `sdk_version`, que `codegen` réécrit après un succès (`manifest.cpp:204-261`) |
| `includes` du haut du manifeste (couche partagée) et de chaque binaire | Relatifs au dossier du manifeste (`manifest.cpp:68-160`) | Dans `project/config/` |
| `includes` d'un fichier inclus, **en cascade** | Relatifs au fichier qui inclut, en profondeur d'abord, 32 niveaux au plus, inclusion circulaire refusée (`config.cpp:24`, `428-480`) | Dans `project/config/`, 32 niveaux au plus, sans boucle |
| `template_dir`, où qu'il soit | Relatif au dossier du manifeste ; tous ses fichiers entrent dans l'empreinte (`project_recompiler.cpp:57-75`) | Dans `project/config/` |
| `[project].hook_sources` | Dossiers relatifs au manifeste ; fichiers `.cpp`, `.cc`, `.h`, `.hpp` (`hook_scan.cpp:527-548`) | Dans `project/config/` |

Règles de B2 :
- chaque entrée est atteinte **sans lien symbolique**, et c'est un fichier ordinaire sans
  autre lien physique (`config-outside` sinon). ReXGlue suit les liens
  (`std::filesystem::canonical`) : B2 les refuse ;
- un fichier inclus ne peut pas fixer `file_path`, `out_directory_path`, `guest_path` ni
  `hook_sources`, qui reviennent au manifeste (`test-config-invalid`) ;
- un élément d'`includes` qui n'est pas un chemin est refusé ; ReXGlue l'ignorerait sans
  rien dire ;
- `project/` ne contient que le manifeste et `config/` (`project-unexpected-entry`) ;
- **F-a** (D-021) : aucune configuration consommée ne fixe `function_table_base`, ni le
  manifeste, ni un fichier inclus, à quelque profondeur que ce soit. Une valeur `0` est
  comptée aussi : elle ne remplace pas une valeur héritée (`MergeScalar`,
  `config.cpp:40-41`). Sinon, `table-base-conflict` bloque `run`, et rien n'est modifié.

**Inventaire** : `prepare` fait la liste des fichiers consommés, en cascade, et
l'**inventaire de tout `project/config/`** (§5.2). Le résumé n'en donne que des nombres :
fichiers consommés, profondeur, fichiers de `config/` non consommés, entrées
`[functions]`, `setjmp` et `longjmp`. Les chemins, les adresses et les empreintes restent
dans le rapport local.

**Contre-vérification** : après un succès, `codegen.d`, écrit par ReXGlue, donne les
entrées qu'il a réellement consommées (`project_recompiler.cpp:597-605`).
- Tout ce qu'il liste doit être un module, le manifeste ou un fichier de `project/config/`
  (`codegen-input-unexpected`).
- Toute configuration atteinte depuis un binaire doit y figurer
  (`config-inventory-differs`).
- Limite [V] : les configurations de la couche partagée n'y figurent pas, car ReXGlue ne
  les compte pas dans l'empreinte d'un module (`MergeSharedEntriesIn`, `config.cpp:578`).
  Elles sont inventoriées et protégées comme les autres, mais non contre-vérifiées.

### 3.3 Refusés par l'outil

[V, d'après `J2_A1_SDK_INVENTORY.md` §3.1] :
- un `.xexp` à côté d'un module : ReXGlue l'appliquerait sans le signaler ;
- `app/rexglue.toml` : ReXGlue le lirait ;
- un dossier de sortie absent ou non vide : `codegen` supprime ce qui ressemble à une
  sortie qu'il n'a pas produite.

## 4. Ce que fait `run`, dans l'ordre

Le moteur de B1 (`J2_B1_EXTRACTION.md` §2), avec ces étapes propres :

1. **Contrôles sans écriture** (ceux de `prepare`) :
   - ceux de B1, sauf l'image, `game/` vide et le rapport J0 ;
   - `game-tree` : `game/` est l'arborescence de PB-1 ;
   - `project` : le manifeste passe `private_project.check_manifest`, `project/` ne
     contient que le manifeste et `config/`, les dossiers de sortie existent et sont vides,
     pas de `app/rexglue.toml` ;
   - `test-config` : les entrées de configuration du §3.2, et l'inventaire de
     `project/config/`. Sans fichier consommé (`test-config-absent`), `run` est bloqué,
     pas `rehearse`.
2. **Avant le repère** : sonde (30 contrôles), `game-before` (chiffres de PB-1 et
   inventaire de `game/`), CP-3, identités des dossiers.
3. **`preflight`** avec `--dest` : le dossier d'exécution, `generated/`, `project/`,
   `app/`, `tmp/`.
4. **Avant la génération** (`before-codegen`) :
   - les dossiers de sortie sont toujours vides ;
   - le manifeste est celui contrôlé ;
   - l'inventaire de `project/config/` est **repris et comparé** à celui de `prepare`
     (`config-changed`) ;
   - la preuve vaut toujours.
5. **La génération, dans le bac à sable**, depuis `project/` :

   ```text
   rexglue --log-level info --log-file <dossier d'exécution>/codegen.log codegen <manifeste>
   ```

   Limite de *core dump* `1`, délai (`--timeout`, 2 heures par défaut), signaux : comme
   l'extraction de B1.
6. **Après** : les contrôles du moteur, puis :
   - `game-after` : chiffres de PB-1, et inventaire égal à celui d'avant ;
   - `config-after` : inventaire de `project/config/` inchangé, `project/` sans autre
     entrée ;
   - `manifest-after` : la copie n'a changé que par sa ligne `sdk_version` ;
   - `generated` : inventaire de `generated/` ; anomalies (lien, fichier spécial, lien
     physique, fichier hors des dossiers de sortie) et entrées illisibles ;
   - `outputs` : complétude de la génération (§6.3) ;
   - `codegen-inputs` : contre-vérification par `codegen.d` (§3.2) ;
   - `c21` (§6.1, §6.2).

## 5. Confinement et inventaires

### 5.1 Confinement propre à B2

- **`game/` en lecture seule** [V] : avec le vrai bubblewrap, une écriture dans `game/`,
  dans un module, même à taille et date inchangées, dans le dossier personnel ou dans le
  dépôt donne `EROFS` (`test_real_sandbox_keeps_game_read_only`).
- **`project/config/` en lecture seule** [V] : le moteur remonte les dossiers en lecture
  seule du profil **après** les dossiers inscriptibles. `project/config/` reste donc en
  lecture seule à l'intérieur de `project/`. La sonde le vérifie
  (`write-denied-project-config`), et une écriture dans une configuration incluse donne
  `EROFS`.
- **`project/` reste inscriptible**, et c'est le strict nécessaire : ReXGlue réécrit le
  manifeste par un fichier temporaire du même dossier, puis un renommage (`manifest.cpp:
  204-261`). Un montage du seul fichier ne permettrait pas ce renommage. Tout autre
  changement de `project/` est un constat après coup (`project-unexpected-entry`,
  `manifest-changed`).
- **La mémoire de l'invité**, qui contient l'image décodée (`J2_A1_SDK_INVENTORY.md`
  §4.3), est un objet de `/dev/shm` :
  - [V] dans le bac à sable, `/dev/shm` est un dossier du `/dev` privé, un tmpfs propre au
    bac à sable, vide au départ et invisible de la machine. La sonde le vérifie
    (`shm-private`) ;
  - [V] après le vrai `codegen` du contrôle Nix, aucun objet `xenia_memory_*` ne reste
    dans le `/dev/shm` de la machine ;
  - [H] cette mémoire disparaît avec le bac à sable. Comme tout tmpfs, elle peut aller dans
    l'espace d'échange (`J2_B1_EXTRACTION.md` §3.3).
- **Aucun fichier de l'image décodée** : [V, par lecture] aucun chemin de code de ReXGlue
  ne l'écrit dans un fichier (`J2_A1_SDK_INVENTORY.md` §3.1) ; un *core dump* est empêché
  par la limite `1` (D-018).
- **Journal** au niveau `info`, dans le dossier d'exécution. Il peut contenir des adresses
  et des mots d'instruction : il reste local (CP-5).
- **Pas de réseau**, et la même fermeture du magasin que B1 (D-019).

### 5.2 Ce que les inventaires détectent, et ce qu'ils ne détectent pas

**L'inventaire** d'une arborescence est fait par le parcours du moteur, `survey_tree`, qui
ouvre chaque dossier depuis le descripteur de son parent, sans jamais suivre de lien.
Pour chaque entrée, il relève :
- le chemin, le type et le mode ;
- la taille, les dates de modification et de changement d'état (`mtime`, `ctime`), en
  nanosecondes ;
- le périphérique et l'inode ;
- pour un fichier, le **SHA-256 de son contenu**, lu par un descripteur dont l'identité est
  comparée à celle relevée.

| Inventaire | Quand | Contenu haché |
|---|---|---|
| `game/` | Juste avant le repère, puis après la génération | Oui, chaque fichier |
| `project/config/` | À `prepare`, juste avant la génération, après la génération | Oui, chaque fichier |
| `generated/` | Après la génération | Non : seules les métadonnées comptent pour la complétude (§6.3) |

**Détecté** [V, tests §10] :
- un fichier ajouté, retiré, renommé ou remplacé, même par une copie identique (l'inode
  change) ;
- un contenu changé à **taille et date de modification inchangées** (le SHA-256 et `ctime`
  changent) ;
- un changement de mode ;
- une entrée illisible ou qui change pendant la lecture. Elle n'est **jamais sautée** :
  c'est une anomalie, et un inventaire incomplet est un constat (`tree-unreadable`) ;
- un lien, un fichier spécial, un lien physique, une entrée d'un autre système de fichiers.

**Non détecté, par construction** :
- une modification **faite puis entièrement défaite** entre deux inventaires, contenu et
  dates compris. `ctime` ne se remet pas en arrière sans changer l'horloge du système, ce
  qui demande des droits que l'outil refuse d'avoir (root) ;
- une lecture : l'inventaire ne prouve pas qu'un fichier n'a pas été lu ;
- ce qui se passe hors des moments de l'inventaire.

La **première protection reste le montage en lecture seule** du bac à sable (§5.1) ;
l'inventaire est une preuve, après coup, de ce qu'il a permis. Il ne détecte pas
« toute modification ».

**Coût** : chaque inventaire de `game/` lit tout son contenu, deux fois par exécution
(§11.3).

## 6. C2.1, journal complet et complétude de la génération

### 6.1 Le critère C2.1

- Le journal `codegen.log` est lu par `address_compare.parse_log` (A8-bis), aux formats de
  ReXGlue v0.11.0 :
  - erreurs d'analyse `UnresolvedCall` et *millicode*, avec le résumé « Validation
    failed: N unresolved calls, M millicode errors », dont les nombres doivent
    correspondre ;
  - erreurs de configuration des entrées (`Invalid [functions] entry`, `Function 0x…`) ;
  - diagnostics sur les entrées : « not a function entry point », « outranked by »… Ce
    ne sont pas des erreurs ; leurs niveaux sont l'affaire du §7.
- **C2.1 est atteint** si `codegen` sort avec 0, si le journal est complet (§6.2), sans
  « Validation failed », sans erreur d'analyse ni erreur de configuration.
- Un journal d'un format inconnu, partiel, vide ou tronqué est refusé
  (`codegen-log-refused`) : C2.1 n'est alors **pas mesuré**, et B2 s'arrête.

### 6.2 Un journal complet

Un code de sortie 0 ne suffit pas : un journal vide ou coupé ne montre aucune erreur.

- [V, `codegen_command.cpp:83`] après la génération de tous les modules, ReXGlue écrit une
  seule fois, au niveau `info`, la ligne « Codegen summary: N written, N unchanged,
  N deleted, N module(s) up to date ». Une exécution qui échoue s'arrête avant.
- Avec l'option `completed` (code 0), `parse_log` refuse :
  - un journal vide ;
  - un journal dont la dernière ligne n'est pas terminée ;
  - un journal sans cette ligne, ou qui en a deux ;
  - un journal qui a aussi un résumé « Validation failed ».
- Sans l'option, rien ne change pour les autres utilisateurs du comparateur.

### 6.3 La complétude de la génération

C'est un critère **distinct de C2.1** : C2.1 dit que l'analyse n'a pas d'erreur ; la
complétude dit que les sorties attendues existent. Elle se vérifie sur ce que ReXGlue
écrit [V, par lecture] :

| Élément | Source | Contrôle |
|---|---|---|
| Un `codegen.stamp` par module, dans son dossier de sortie | `project_recompiler.cpp:575-588`, `output_stamp.cpp:18-53` | Fichier ordinaire, JSON de version 1, empreinte non vide, liste non vide de noms simples, sans doublon |
| Les sorties listées par le `codegen.stamp` | `codegen_writer.cpp:442-492` | Toutes présentes |
| Les sortes de sorties d'un module | `codegen_writer.cpp:306-417` | `<préfixe>_pch.h`, `_funcs.h`, `_init.h`, `_init.cpp`, `_register.cpp`, au moins un `_funcs.N.h` et un `_recomp.N.cpp`, `sources.cmake`, `codegen.partition.json`, `codegen.mmio.json` |
| Dans le dossier du module d'entrée | `project_recompiler.cpp:597-709` | `codegen.d`, `codegen.build.stamp` (une empreinte par module, dans l'ordre), `module_registry.cpp` et `dll_targets.cmake` |
| La ligne « Codegen summary » | `codegen_command.cpp:83` | Écrits et inchangés = sorties listées + les 2 fichiers du registre ; 0 inchangé, 0 supprimé, 0 module à jour (les dossiers étaient vides) |
| Rien d'autre | — | Un fichier qu'aucun `codegen.stamp` ne liste est un constat (`generated-unlisted`) |
| Un inventaire complet de `generated/` | §5.2 | Une entrée illisible ou une anomalie rend la complétude impossible à établir |

- Après un code 0, une génération incomplète est un **constat bloquant**
  (`generation-incomplete`), même si C2.1 est atteint.
- Après un échec, la complétude est relevée, sans constat de plus que `codegen-failed`.

### 6.4 Ce qu'en dit le résumé

- Des nombres et `match` ou `DIFFERS` seulement : ni adresse, ni chemin, ni empreinte, ni
  ligne du journal. Les adresses restent dans `report.json`, local, jusqu'à PB-3.
- Deux lignes distinctes : « C2.1 met » et « generation complete », puis
  « B2 result for PB-2 », qui n'est `yes` que si les deux le sont et qu'aucun fichier
  n'est hors liste.

## 7. Contrôles ciblés, par la méthode M1 (A8, A8-bis)

Seulement si C2.1 est atteint :
1. le porteur examine localement le code généré autour de `setjmp`, `longjmp` et des sites
   des correctifs, et consigne ses examens en `[[claim]]` (format de
   `J2_A8BIS_ADDRESS_COMPARE.md` §2) ;
2. il lance le comparateur sur les sorties privées :

   ```bash
   nix run .#address-compare -- --entries function=<configuration incluse> \
     --mappings-with "$WC2010_PRIVATE_DIR"/generated/fifadllzf/wc2010_init.cpp \
     --log "$WC2010_PRIVATE_DIR"/logs/b2-run-<date>/codegen.log \
     --claims <relevé> --out "$WC2010_PRIVATE_DIR"/logs/b2-run-<date>/address-compare.json
   ```

   Chaque binaire prend le nom du projet comme préfixe (`manifest.cpp:59`,
   `codegen_writer.cpp:320`).
3. `setjmp_address` et `longjmp_address` d'une configuration de type `function` y sont
   lus comme entrées `crt` (`tools/address_compare.py`). Sa sortie standard est agrégée :
   des nombres par niveau, sans adresse. `setjmp` ou `longjmp` sous N2 est un arrêt PB-2.

L'outil de B2 ne fait pas cet examen : il est humain, et porte sur du code privé.

## 8. Point d'arrêt PB-2

- **Transmis à l'orchestrateur**, après CP-5 : le `summary.txt` de B2 et la sortie
  standard du comparateur. Jamais `report.json`, le journal ni le code généré.
- **Ce que le résumé permet de décider** : C2.1 (§6.1), la complétude (§6.3), l'absence
  de constat sur les entrées (§3, §5.2). Un succès demande les trois.
- **Décision** : l'orchestrateur, puis le porteur.
  - Succès : B3, la validation des adresses.
  - Échec : nouvelle analyse (`J2_PREREQUISITES.md` §5), méthode M3.
- Un succès ne prouve pas l'identité du code avec le projet A (CP-7).

## 9. Procédure pour le porteur

Sur la machine de l'utilisateur, depuis une copie propre de `main`, avec
`WC2010_PRIVATE_DIR` défini. Les étapes 1 à 7 préparent la demande de mandat ; **seule
l'étape 9 génère du code, et seulement après le mandat**.

**Préparation des entrées (C-a, D-021)**

1. **Construire l'outil** :

   ```bash
   B="$(nix build --no-link --print-out-paths .#b2-codegen)/bin/fifa2010wc-b2-codegen"
   ```

2. **Copier le gabarit**, si ce n'est pas déjà fait (`init` n'écrase jamais une copie) :

   ```bash
   nix run .#private-project -- --repo "$PWD" init
   ```

3. **Cloner le projet A**, hors du dépôt et hors du dossier privé. Le clone ne contient que
   des fichiers publics, mais il ne doit jamais être commité ici :

   ```bash
   git clone https://github.com/CalinGraphics/fifa-world-cup-2010-recompiled "$HOME/project-a"
   ```

4. **Copier la configuration épinglée** dans `project/config/`, et la nommer dans la copie
   privée du manifeste :

   ```bash
   nix run .#private-project -- --repo "$PWD" stage-config --source "$HOME/project-a"
   ```

   `stage-config` (`tools/private_project.py`, `docs/J2_A5_CONFIG_TEMPLATE.md`) :
   - vérifie que le commit `498d18ae09175d4991b24b633a9a5f2e0e1cc73e` existe dans le clone
     et se résout bien en lui-même ;
   - lit, dans les objets de ce commit seulement, le manifeste du projet A et les fichiers
     qu'il inclut pour chaque binaire, en cascade, sans copie de travail ni crochet git ;
   - refuse un lien, un sous-module, un fichier hors de `pc/config/`, une boucle ;
   - copie chaque fichier octet pour octet, sans jamais écraser, puis remplace
     `includes = []` dans les deux tables de binaire de la copie privée ;
   - ne copie pas `pc/fixes/` ;
   - signale, sans rien modifier, tout fichier qui fixe `function_table_base`
     (`CONFLICT with option F-a`).

**Contrôles avant la demande de mandat**

5. **Diagnostic sans écriture** :

   ```bash
   "$B" --repo "$PWD" prepare
   ```

   - `test-config` dit ce que `codegen` consommera : fichiers, profondeur, fichiers non
     consommés, et `table_base_settings`.
   - `resources` relève la mémoire, l'espace d'échange et le disque libre (T-a).
   - **Avec C-a, `table-base-conflict` est attendu** (§11.5). Le porteur s'arrête alors, et
     transmet le résumé pour l'arbitrage distinct. Il ne modifie pas la configuration
     copiée.
6. **Répétition de B2**, une fois le conflit arbitré, qui apporte la preuve de l'option B
   propre au profil B2 :

   ```bash
   "$B" --repo "$PWD" rehearse
   ```

   Si elle échoue : `diagnose --run-folder b2-rehearse-<date>`.
7. **`prepare` final**, qui doit être **sans constat**, puis **partage** des deux
   `summary.txt`, après CP-5. C'est sur eux que l'orchestrateur, puis le porteur, décident
   du mandat réel.

**Après le mandat seulement**

8. La preuve de l'option B vaut pour un démarrage : après un redémarrage, refaire la
   répétition et le `prepare` final.
9. **B2**, dans le même démarrage que la répétition, avec le délai par défaut de deux
   heures (T-a ; au-delà, l'outil refuse) :

   ```bash
   "$B" --repo "$PWD" run
   ```

   Si l'outil est interrompu : `resume --run-folder b2-run-<date>`.
10. **Partage** : `summary.txt` seulement, après CP-5.

## 10. Essais sans données du jeu, et ce qu'ils ne couvrent pas

**Tests** (`tools/test_b2_codegen.py`, 31 tests) : ils reprennent le montage synthétique
des tests de B1 (`tools/test_b1_extract.py`), avec un faux `rexglue codegen` qui écrit les
sorties, `codegen.stamp`, `codegen.d`, `codegen.build.stamp`, le registre et le journal
aux formats de ReXGlue (§6.3).

| Cas | Tests |
|---|---|
| Entrées de `game/` | Plus l'arborescence de PB-1 (fichier en plus, module changé, `.xexp`) ; dossier illisible. Chaque fois, `codegen` ne démarre pas |
| Entrées du projet | Manifeste invalide ; sortie non vide ; `app/rexglue.toml` ; autre fichier dans `project/` ; configuration absente (bloque `run`, pas `rehearse`) ; dossier illisible dans `project/config/` |
| Entrées de configuration (point 1 de la revue) | Inclusions en cascade sur trois niveaux, comptées et retrouvées dans `codegen.d` ; refusés : inclusion hors de `config/`, par un lien, lien vers l'extérieur, fichier absent, élément qui n'est pas un chemin, boucle, 33 niveaux, fichier inclus qui fixe `file_path`, `hook_sources` ou `template_dir` hors de `config/`. Chaque fois, `codegen` ne démarre pas |
| Substitution | Une configuration incluse changée après `prepare`, pendant la sonde : `config-changed` juste avant la génération, qui ne démarre pas. Pendant la génération : changée, changée à taille et date inchangées, fichier ajouté à `project/` : constats après coup |
| Contre-vérification | `codegen.d` qui liste une autre entrée, ou qui omet les configurations : constats |
| Succès | Arguments exacts, sans `-f` ; dossier de travail `project/` ; limite `(1, 1)` ; C2.1 atteint ; génération complète ; `game/` et `project/config/` inchangés ; manifeste changé par `sdk_version` seulement ; second passage refusé |
| C2.1 et journal (point 2) | Appels non résolus et *millicode* : `DIFFERS`, aucune adresse dans le résumé ; journal partiel refusé ; après un code 0, journal sans « Codegen summary », coupé, ou vide : refusé, C2.1 non mesuré |
| Complétude (point 2) | Après un code 0 et un journal propre : aucune sortie, `codegen.stamp` absent ou invalide, sortie listée absente, registre absent, `codegen.build.stamp` dans le désordre, résumé du journal en désaccord, fichier hors liste, dossier illisible, lien. C2.1 reste atteint, B2 ne l'est pas |
| `game/` (point 3) | Un module, puis un autre fichier, changés à taille et date de modification inchangées : `game-changed` |
| Après | Module modifié, autre changement du manifeste, lien dans les sorties : constats |
| Robustesse | Plantage et délai dépassé, avec `postflight` ; outil tué puis repris |
| Preuve | Une preuve de B1, ou d'une autre version du profil, n'ouvre pas B2 ; la répétition de B2 l'apporte |
| Vrai bubblewrap | Sonde à 30 ; écritures dans `game/`, un module, `project/config/`, une configuration, même à taille et date inchangées, le dossier personnel et le dépôt refusées par `EROFS` ; sorties et réécriture du manifeste permises |
| Unitaires | Inventaire : contenu à taille et date inchangées, copie identique (inode), dossier illisible ; `survey_tree` sans inventaire inchangé pour B1 ; formats de `codegen.d` et de `codegen.stamp` |
| Arbitrages D-021 | F-a : `function_table_base` dans une inclusion, dans une inclusion indirecte, ou à `0` dans le manifeste par-dessus une valeur héritée : `table-base-conflict`, `codegen` ne démarre pas, rien n'est modifié. T-a : `--timeout` à 7201 ou à 0 refusé ; ressources relevées depuis un `meminfo` synthétique. L-a : niveau `info`, journal dans le dossier d'exécution. C-a de bout en bout : `stage-config` sur un clone synthétique à la disposition du projet A, puis `prepare` sans constat et `run` réussi |

**Préparation des entrées** (`tools/test_private_project.py`, 6 tests de `stage-config`
sur 38) : sur un clone git synthétique, à la disposition du projet A, aux adresses
inventées :
- copie fidèle des six fichiers, dont une inclusion indirecte, et `includes` posés dans
  les deux tables de binaire ; `pc/fixes/` non copié ;
- conflit F-a signalé, fichier copié tel quel ;
- refusés, sans rien écrire : identifiant de commit abrégé ou inconnu, lien dans le
  commit, inclusion hors de `pc/config/`, boucle, fichier absent, inclusion qui n'est pas
  un chemin ;
- jamais d'écrasement ; une seconde copie refusée ; copie privée absente.

**Comparateur** (`tools/test_address_compare.py`, 31 tests) : le test
`test_a_completed_log_must_be_whole` couvre l'option `completed` ; les 30 autres sont
inchangés.

**Contrôle Nix `b2-codegen-selftest`** : les tests, puis les commandes empaquetées avec
le **vrai** bubblewrap et le **vrai** `rexglue codegen`, sur un projet synthétique.
- La configuration est copiée par la vraie commande `stage-config`, depuis un clone git
  synthétique à la disposition du projet A : cinq fichiers, `project/` sans autre entrée.
- `game/` contient deux fichiers texte aux noms des modules : ReXGlue les refuse à leurs
  premiers octets (« Unknown module magic »), avant tout décodage.
- [V] `prepare` sans constat ; `run` : sonde à 30, inventaire de `game/` (3 fichiers
  hachés), `codegen` sort avec 1, C2.1 non atteint, génération non complète, `game/`,
  `project/config/` et manifeste inchangés, aucune sortie, rien d'écrit hors du dossier
  d'exécution, aucun objet `xenia_memory_*` laissé.
- Quand le bac à sable ne peut pas démarrer (CI) : `run` refuse, rien n'est généré.

**Les tests de B1 passent toujours** : 78 tests, sans changer leurs attentes, sauf la
version de l'outil (7) et deux contextes de test qui portent le profil. Le faux bubblewrap
des tests gagne une clé de plan, `probe_writes`, que B1 n'utilise pas.

**Non couvert, faute des fichiers du jeu** :
- un vrai XEX, le décodage, et une vraie génération réussie [I]. Les noms et formats des
  sorties du §6.3 viennent de la lecture des sources, et ne sont essayés qu'avec le faux
  `codegen` ;
- la durée, la mémoire et le disque d'une vraie génération [I] (§11.3) ;
- la preuve de l'option B avec le vrai systemd-coredump, pour B2 : seul `rehearse`, chez
  le porteur, la fait ;
- les vraies valeurs et la vraie disposition de la configuration du projet A (§11.1).

## 11. Points arbitrés avant le mandat de B2

Chaque point a été présenté par options comparables. **Le porteur a retenu C-a, F-a, T-a
et L-a (D-021).** Les options écartées restent décrites pour mémoire. Le choix de C-a
avec F-a crée un conflit, soumis à un arbitrage distinct (§11.5).

### 11.1 La configuration de test, épinglée

**Ce que l'on sait** [V, audit `docs/audit/EXISTING_PROJECTS.md`, projet A à `498d18a`] :
- un manifeste, `pc/fifawc10_manifest.toml`, pour les deux modules ;
- les configurations `pc/config/default.toml` et `pc/config/fifadllzf.toml` : débuts de
  fonctions, `setjmp` et `longjmp`, et trois valeurs de disposition ;
- des fichiers de pointeurs de code : 663 lignes pour `default.xex`, 17 028 pour
  `fifadllzf.xex` ;
- des correctifs en C++ dans `pc/fixes/`.

**Comment ils s'incluent** [V, lecture lors de l'audit, au commit épinglé] : le manifeste
du projet A inclut, pour `default.xex`, `config/codegen_options.toml`,
`config/default.toml` et `config/default_pointers.toml` ; pour `fifadllzf.xex`,
`config/codegen_options.toml`, `config/fifadllzf.toml` et `config/fifadllzf_pointers.toml`.
Les pointeurs entrent donc par le manifeste, ce qui distingue C-a de C-d. `stage-config`
relit ces listes sur le clone du porteur, et suit les inclusions en cascade [I au-delà].

| Option | Contenu | Pour | Contre |
|---|---|---|---|
| **C-a** | Commit de l'audit `498d18a` : les deux configurations, et tout ce qu'elles incluent, sans les correctifs C++ | Ce qui a été audité ; le contrôle de disposition de `J2_PREREQUISITES.md` §3.1 porte sur ce commit | Peut être en retard sur le projet A |
| **C-b** | C-a, avec les correctifs de `pc/fixes/` en `hook_sources` | Plus proche de la génération du projet A | Des crochets à adresses fixes entrent dans la génération : un échec serait plus difficile à attribuer ; leurs adresses relèvent de B3 |
| **C-c** | Un commit plus récent du projet A, après une mise à jour de l'audit | Corrections éventuelles du projet A | Nouvel audit d'abord ; le contrôle de disposition est à refaire |
| **C-d** | Débuts de fonctions, `setjmp` et `longjmp` seulement, sans les pointeurs | Entrée plus petite | Des appels non résolus attendus, que les pointeurs auraient résolus : C2.1 ne dirait plus rien de la configuration du projet A |

**Choix : C-a** (D-021), au commit **`498d18ae09175d4991b24b633a9a5f2e0e1cc73e`** : les
fichiers que le manifeste du projet A inclut pour chaque binaire, et leurs inclusions en
cascade, sans `pc/fixes/`. Copie par `stage-config` (§9, étapes 3 et 4).

**Épinglage**, commun aux options :
- le porteur clone le projet A **sur sa machine**, se place sur le commit retenu, et en
  relève l'identifiant complet par `git rev-parse HEAD` ;
- il copie les fichiers par `git show <commit>:<chemin>`, sans passer par une copie de
  travail modifiée, dans `project/config/`, avec leur disposition relative ;
- B2 relève localement l'empreinte de chaque fichier consommé (`report.json`) ; le résumé
  n'en donne que des nombres ;
- ce qui peut être publié : l'identifiant du commit et les chemins des fichiers, qui sont
  publics. Ni le contenu, ni les adresses (CP-7).

### 11.2 `function_table_base` pour le test

**Ce que l'on sait** [V, par lecture du correctif A3,
`patches/rexglue-sdk/0001-function-table-base.patch`] :
- la clé n'entre **pas dans l'analyse** : elle ne sert qu'aux données des gabarits du
  code généré (`codegen_writer.cpp`) et à la validation de la configuration ;
- une valeur non alignée sur 64 Kio, ou hors de `0x80000000-0x8FFFFFFF`, est une erreur de
  validation, donc un échec de `codegen` ;
- elle vaut pour un binaire, jamais pour la couche partagée ; une valeur non nulle du
  manifeste l'emporte sur celle d'un fichier inclus (`config.cpp:465`). Une valeur `0`, en
  revanche, ne remplace rien (`MergeScalar`, `config.cpp:40-41`) ;
- elle entre dans l'empreinte du module : la changer plus tard régénère le code.

Elle ne change donc pas C2.1, sauf par une valeur invalide.

| Option | Valeur pour `default.xex` | Justification | Limite |
|---|---|---|---|
| **F-a** | Aucune : table à la fin de l'image | Suit l'étape 1 de `J2_A3_FUNCTION_TABLE.md` §7 : relever d'abord `c_def` et `c_dll` dans le code généré | Si une configuration du projet A fixe la clé, il faut ne pas l'inclure ou la modifier, ce qui l'écarte de l'épinglage du §11.1 [I]. Code à refaire avant toute exécution si `c_def > 0x78000` [I] |
| **F-b** | `0x86C10000` | Valable quelles que soient les tailles de code, sous T-5 (`J2_A3_FUNCTION_TABLE.md` §7) [V calcul] | Choix d'exécution fait avant d'avoir les tailles ; [I] allocations du jeu |
| **F-c** | `0x86100000`, celle du projet A | Celle de la configuration du projet A, sans changement | Valable seulement si `c_dll ≤ 0x12C8000` [I] |

**Choix : F-a** (D-021). **Il est en conflit avec C-a** : voir §11.5.

### 11.3 Délai et ressources, mesurés sur synthétique

**Mesures** [V, sur des données synthétiques, dans le conteneur de Claude Code, pas sur la
machine du porteur] :

| Mesure | Résultat | Ce qu'elle dit |
|---|---|---|
| Inventaire avec hachage (`survey_tree`, `content`), sur un arbre de 49 fichiers et 1 Gio (un gros fichier et 48 petits), 4 processeurs | 0,85 s, environ 1 200 Mio/s, meilleur de 3 essais, **depuis le cache de pages** | Le coût du hachage. Sur la machine du porteur, la première lecture de `game/` peut être limitée par le disque. B2 lit `game/` en entier deux fois (avant le repère, après la génération), et les deux modules une fois de plus à chaque contrôle des chiffres de PB-1 |
| Inventaire sans hachage, même arbre | 0,1 ms | Le coût du parcours seul |
| Taille du `/dev/shm` du bac à sable (`statvfs`, dans un bac à sable `--dev /dev`) | 8 434 335 744 octets, la moitié des 16 473 316 Kio de la machine | La taille par défaut d'un tmpfs. Elle suit la mémoire de la machine |
| Le vrai `codegen` du contrôle Nix | Il refuse les faux modules dès leurs premiers octets | Rien sur la durée ni la mémoire d'une vraie génération |

**Conséquence** [H] : la mémoire de l'invité réserve environ 4,5 Gio, alloués de façon
creuse (`J2_A1_SDK_INVENTORY.md` §4.3). Seules les pages écrites comptent dans le tmpfs.
Si la génération en écrit plus que la moitié de la mémoire de la machine, elle s'arrête
sur une erreur de bus : `codegen-crashed`. Le nombre de pages écrites est inconnu [I].

**Limites** : aucune de ces mesures ne vaut pour une vraie génération. La durée, la mémoire
et le disque d'une vraie génération des deux modules sont inconnus [I]. Le projet A ne
publie que la durée de construction de son SDK, pas celle de sa génération.

| Option | Délai | Pour | Contre |
|---|---|---|---|
| **T-a** | 2 heures, par défaut | Arrête une génération bloquée | Peut couper une génération longue : `codegen-timeout`, à refaire sur des dossiers vides |
| **T-b** | Plus long, par `--timeout` | Moins de risque de coupure | Une génération bloquée occupe la machine plus longtemps |

Dans les deux cas, le porteur relève avant la répétition la mémoire de la machine et le
disque libre du dossier privé. Ce ne sont que deux nombres, partageables après relecture.

**Choix : T-a** (D-021) : deux heures au plus. L'outil refuse `--timeout` au-delà, ou nul
(`timeout-above-t-a`). `prepare` relève, dans l'étape `resources`, en Mio : la mémoire
totale et disponible, l'espace d'échange, le disque libre du dossier privé, et la taille
par défaut du `/dev/shm` du bac à sable (la moitié de la mémoire). Ce ne sont que des
relevés : **les besoins d'une vraie génération restent inconnus** [I], et l'outil n'en
déduit aucun seuil.

### 11.4 Le niveau du journal

| Option | Effet | Compatible avec la procédure |
|---|---|---|
| **L-a** `info` | Contient la ligne « Codegen summary », écrite au niveau `info` (`codegen_command.cpp:83`). Contient aussi le bilan de génération, les chemins des modules, les versions d'un `.xexp` (`J2_A1_SDK_INVENTORY.md` §4.2) : il reste local | Oui : c'est le niveau qui permet de refuser un journal vide ou tronqué (§6.2) |
| **L-b** `warn` | Moins de choses localement. Mais la ligne « Codegen summary » n'y est plus : une génération réussie et un journal coupé ne se distinguent plus | Non, sauf à renoncer au contrôle du §6.2 |
| **L-c** `debug`, `trace` | Noms de classes RTTI, imports et exports, chemins complets | Non : exclus par CP-5 (`J2_A1_SDK_INVENTORY.md` §4.2) |

Les erreurs et diagnostics que lit C2.1 sont écrits aux niveaux `error` et `warn`
(`analyze.cpp:108-128`, `phase_validate.cpp:57`) : ils sont dans le journal avec L-a comme
avec L-b. Seule la preuve d'un journal complet demande `info`.

**Choix : L-a** (D-021). La commande fixe `--log-level info` ; le journal reste dans le
dossier d'exécution, local ; `debug` et `trace` sont exclus.

### 11.5 Conflit entre C-a et F-a : arbitrage distinct demandé

**Constat** [V, lecture du projet A lors de l'audit ; `J2_A3_FUNCTION_TABLE.md` §1] : au
commit épinglé, `pc/config/default.toml`, que le manifeste du projet A inclut pour
`default.xex`, fixe `function_table_base` (la valeur du projet A, examinée en A3). Avec
C-a, cette valeur est donc héritée.

**Pourquoi F-a ne peut pas l'annuler** [V, `config.cpp:40-41`, `465`] : une valeur `0`
dans le manifeste ne remplace pas une valeur non nulle héritée. Ne rien imposer
demanderait de ne pas copier ce fichier, ou de le modifier.

**Ce que fait l'outil**, conformément à D-021 :
- `stage-config` copie le fichier tel quel et signale le conflit ;
- `prepare` donne `table_base_settings 1` et `table-base-conflict`. **`run` est bloqué** ;
- rien n'est modifié en silence, et ni F-b ni F-c n'est substitué.

**Effet sur le contrôle de compatibilité** [V, lecture du correctif A3] : la clé n'entre
pas dans l'analyse. C2.1 serait le même avec chacune des options ci-dessous ; seuls les
gabarits du code généré, et donc l'exécution future, en dépendent.

**Options pour l'arbitrage distinct**, comparables, **aucune retenue** :

| Option | Ce qui est fait | Conséquence sur C-a | Conséquence sur F-a |
|---|---|---|---|
| **G-1** | Garder la valeur héritée | Inchangée | Abandonnée : revient à F-c |
| **G-2** | Fixer une valeur non nulle dans la table du binaire de la copie privée, qui l'emporte | Inchangée | Abandonnée : revient à F-b |
| **G-3** | Copier `default.toml` sans sa seule ligne `function_table_base`, écart consigné | Modifiée, d'un écart unique et documenté | Tenue |
| **G-4** | Renoncer à `default.toml` | Amputée de ses débuts de fonctions | Tenue, mais C2.1 ne dirait plus rien de la configuration du projet A |

Quelle que soit l'option retenue, l'outil devra être aligné sur elle dans une PR, avant
la demande de mandat. Le contrôle `table-base-conflict` reste en place tant que F-a
s'applique.

## 12. Ce qui revient dans le dépôt après B2

Seul le contenu de `summary.txt`, après la décision PB-2 : des nombres, des statuts, des
codes, `match` ou `DIFFERS`.

Ne reviennent jamais dans le dépôt : le code généré, les journaux, la désassemblée, et
les adresses avant PB-3 (D-007).

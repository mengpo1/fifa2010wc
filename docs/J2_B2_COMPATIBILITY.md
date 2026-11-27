# Étape B2 — contrôle de compatibilité : proposition de procédure

> Étape B2 de `docs/J2_PLAN.md` §4.2. Version 1, **proposée à la revue**.
> **B2 n'est pas autorisée** : PB-1 est franchi (D-020), mais B2 reste soumise à un mandat
> distinct. Rien ici n'a lu, décodé ni généré quoi que ce soit du jeu.
> - L'outil est `tools/b2_codegen.py`, empaqueté par le flake (`.#b2-codegen`). C'est le
>   **profil B2 du moteur d'étapes de B1** (`docs/J2_LOCAL_STEP_ENGINE.md`), pas un nouvel
>   outil de confinement.
> - Les essais n'utilisent que des fichiers synthétiques (§10).
> - B2 s'exécutera à la main, **sur la machine du porteur seulement**, après le mandat.
> - PB-2 est décidé par l'orchestrateur, puis le porteur, sur les résultats locaux.
>
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Ce que fait B2, et ce qu'elle ne fait pas

**Action** (plan §4.2) : une première génération de code par ReXGlue, sur les deux modules
extraits à B1, avec la configuration du projet A comme **simple entrée de test**.
- ReXGlue décode les modules en mémoire. C'est le **premier déchiffrement du projet**, par
  la voie O3 (D-008) : le SDK amont seul, localement.
- Le code généré va dans `$WC2010_PRIVATE_DIR/generated`. C'est une traduction complète
  du code du jeu : il reste privé (D-007).

**Critères** :
- **C2.1** : 0 `UnresolvedCall`, 0 erreur de validation (§6) ;
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
| CP-1, composants et parents du dossier privé, sockets et tubes | Moteur (`b1_extract.py`) | Composants en plus : `generated/`, `project/` |
| Fermeture du magasin (D-019) | Moteur, `b1-closure` du flake | Rien : ce qui tourne dans le bac à sable est le même (Python, le SDK, le moteur) |
| Bac à sable par liste positive | Moteur | **`game/` en lecture seule**. Inscriptibles : le dossier d'exécution, `generated/`, `project/`, `app/`, `tmp/` |
| Sonde de confinement | Moteur | 29 contrôles au lieu de 26 : `write-denied-game`, `writable-generated`, `writable-project`, `shm-private` (§5) |
| *Core dumps*, option B (D-018) | Moteur | Rien : limite `1` pour `codegen`. La preuve est liée au profil : **il faut une répétition de B2**, celle de B1 ne vaut pas |
| Montages, CP-3, `preflight`, `postflight` (CP-4), état, reprise, `diagnose` | Moteur | Le repère est `b2.marker`, les dossiers `logs/b2-run-<date>` et `logs/b2-rehearse-<date>` |
| Résumé par liste fixe | Moteur | Faits et codes de B2 ajoutés à la liste (§6) |
| Chiffres de PB-1 | Moteur (`survey_tree`) | `game/` doit rester **l'arborescence validée à PB-1**, avant et après |
| Manifeste et dossiers de sortie | `private_project.py` (A5) | Appelé tel quel (`check_manifest`) |
| Mesure de C2.1 dans le journal | `address_compare.py` (A8-bis) | Appelé tel quel (`parse_log`) |
| Contrôles ciblés | `address_compare.py` (A8-bis) | Lancé ensuite par le porteur (§7) |

Ce qui est propre à B2 tient dans `tools/b2_codegen.py` : ses contrôles d'entrée, la
commande `codegen`, ses contrôles d'après et ses lignes de résumé.

## 3. Entrées

1. **`game/`** : l'arborescence extraite et validée à B1 (D-020). B2 ne la modifie pas.
   L'outil vérifie, avant et après, ses 49 fichiers, ses 8 dossiers, l'absence
   d'anomalie et les empreintes des deux modules, contre la référence J0.
2. **`project/wc2010_manifest.toml`** : la copie privée du gabarit A5, faite par
   `private-project init`, qui crée aussi `generated/default/` et `generated/fifadllzf/`.
3. **La configuration de test du projet A** :
   - ses fichiers de configuration de génération, récupérés par le porteur depuis le dépôt
     public du projet A (`docs/audit/EXISTING_PROJECTS.md` : `CalinGraphics/fifa-world-cup-2010-recompiled`) ;
   - placés **dans le dossier privé seulement** (`project/config/`), jamais dans ce dépôt
     (CP-7), et nommés dans `includes` de chaque module de la copie privée ;
   - l'outil ne les lit que pour en compter les entrées : `[functions]`,
     `setjmp_address`, `longjmp_address`. Les adresses restent locales.
   - Le choix exact des fichiers et de leur version est un **point à arbitrer** (§11).
4. **Refusés par l'outil** [V, d'après `J2_A1_SDK_INVENTORY.md` §3.1] :
   - un `.xexp` à côté d'un module : ReXGlue l'appliquerait sans le signaler ;
   - `app/rexglue.toml` : ReXGlue le lirait ;
   - un dossier de sortie absent ou non vide : `codegen` supprime ce qui ressemble à une
     sortie qu'il n'a pas produite.

## 4. Ce que fait `run`, dans l'ordre

Le moteur de B1 (`J2_B1_EXTRACTION.md` §2), avec ces étapes propres :

1. **Contrôles sans écriture** (ceux de `prepare`) :
   - ceux de B1, sauf l'image, `game/` vide et le rapport J0 ;
   - `game-tree` : `game/` est l'arborescence de PB-1 ;
   - `project` : le manifeste passe `private_project.check_manifest`, les dossiers de
     sortie existent et sont vides, pas de `app/rexglue.toml` ;
   - `test-config` : les configurations incluses existent et sont du TOML. Leur absence
     (`test-config-absent`) bloque `run`, pas `rehearse`.
2. **Avant le repère** : sonde (29 contrôles), `game-before` (chiffres et liste de
   `game/`), CP-3, identités des dossiers.
3. **`preflight`** avec `--dest` : le dossier d'exécution, `generated/`, `project/`,
   `app/`, `tmp/`.
4. **Avant la génération** (`before-codegen`) : les dossiers de sortie sont toujours vides,
   le manifeste est celui contrôlé, la preuve vaut toujours.
5. **La génération, dans le bac à sable**, depuis `project/` :

   ```text
   rexglue --log-level info --log-file <dossier d'exécution>/codegen.log codegen <manifeste>
   ```

   Limite de *core dump* `1`, délai (`--timeout`, 2 heures par défaut), signaux : comme
   l'extraction de B1.
6. **Après** : les contrôles du moteur, puis :
   - `game-after` : `game/` inchangé, chiffres de PB-1 et liste ;
   - `manifest-after` : la copie n'a changé que par sa ligne `sdk_version`, que `codegen`
     réécrit après un succès ;
   - `generated` : nombre de fichiers, de dossiers de sortie avec `codegen.stamp`, et
     anomalies (lien, fichier spécial, fichier hors des dossiers de sortie) ;
   - `c21` (§6).

## 5. Confinement propre à B2

- **`game/` en lecture seule** [V] : avec le vrai bubblewrap, une écriture dans `game/`,
  dans un module, dans le dossier personnel ou dans le dépôt donne `EROFS`
  (`test_real_sandbox_keeps_game_read_only`).
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

## 6. Le critère C2.1, et ce qu'en dit le résumé

- Le journal `codegen.log` est lu par `address_compare.parse_log` (A8-bis), aux formats de
  ReXGlue v0.11.0 :
  - erreurs d'analyse `UnresolvedCall` et *millicode*, avec le résumé « Validation
    failed: N unresolved calls, M millicode errors », dont les nombres doivent
    correspondre ;
  - erreurs de configuration des entrées (`Invalid [functions] entry`, `Function 0x…`) ;
  - diagnostics sur les entrées : « not a function entry point », « outranked by »… Ce
    ne sont pas des erreurs ; leurs niveaux sont l'affaire du §7.
- **C2.1 est atteint** si `codegen` sort avec 0, sans « Validation failed », sans erreur
  d'analyse ni erreur de configuration.
- Un journal d'un format inconnu ou partiel est refusé (`codegen-log-refused`) : C2.1
  n'est alors **pas mesuré**, et B2 s'arrête.
- **Le résumé ne donne que des nombres et `match` ou `DIFFERS`** : ni adresse, ni ligne
  du journal. Les adresses restent dans `report.json`, local, jusqu'à PB-3.

## 7. Contrôles ciblés, par la méthode M1 (A8, A8-bis)

Seulement si C2.1 est atteint :
1. le porteur examine localement le code généré autour de `setjmp`, `longjmp` et des sites
   des correctifs, et consigne ses examens en `[[claim]]` (format de
   `J2_A8BIS_ADDRESS_COMPARE.md` §2) ;
2. il lance le comparateur sur les sorties privées :

   ```bash
   nix run .#address-compare -- --entries function=<configuration incluse> \
     --mappings-with "$WC2010_PRIVATE_DIR"/generated/fifadllzf/fifadllzf_init.cpp \
     --log "$WC2010_PRIVATE_DIR"/logs/b2-run-<date>/codegen.log \
     --claims <relevé> --out "$WC2010_PRIVATE_DIR"/logs/b2-run-<date>/address-compare.json
   ```

3. `setjmp_address` et `longjmp_address` d'une configuration de type `function` y sont
   lus comme entrées `crt` (`tools/address_compare.py`). Sa sortie standard est agrégée :
   des nombres par niveau, sans adresse. `setjmp` ou `longjmp` sous N2 est un arrêt PB-2.

L'outil de B2 ne fait pas cet examen : il est humain, et porte sur du code privé.

## 8. Point d'arrêt PB-2

- **Transmis à l'orchestrateur**, après CP-5 : le `summary.txt` de B2 et la sortie
  standard du comparateur. Jamais `report.json`, le journal ni le code généré.
- **Décision** : l'orchestrateur, puis le porteur.
  - Succès : B3, la validation des adresses.
  - Échec : nouvelle analyse (`J2_PREREQUISITES.md` §5), méthode M3.
- Un succès ne prouve pas l'identité du code avec le projet A (CP-7).

## 9. Procédure pour le porteur, après le mandat de B2

Sur la machine de l'utilisateur, depuis une copie propre de `main`.

1. **Construire l'outil** :

   ```bash
   B="$(nix build --no-link --print-out-paths .#b2-codegen)/bin/fifa2010wc-b2-codegen"
   ```

2. **Copier le gabarit**, si ce n'est pas déjà fait (`init` n'écrase jamais une copie ;
   `WC2010_PRIVATE_DIR` doit être défini) :

   ```bash
   nix run .#private-project -- --repo "$PWD" init
   ```

3. **Placer la configuration de test** du projet A dans `project/config/`, et la nommer
   dans `includes` de la copie privée (§3).
4. **Diagnostic sans écriture** :

   ```bash
   "$B" --repo "$PWD" prepare
   ```

5. **Répétition de B2**, qui apporte sa propre preuve de l'option B :

   ```bash
   "$B" --repo "$PWD" rehearse
   ```

6. **B2**, dans le même démarrage :

   ```bash
   "$B" --repo "$PWD" run
   ```

7. Si la répétition échoue : `diagnose --run-folder b2-rehearse-<date>`. Si l'outil est
   interrompu : `resume --run-folder b2-run-<date>`.
8. **Partage** : `summary.txt` seulement, après CP-5.

## 10. Essais sans données du jeu, et ce qu'ils ne couvrent pas

**Tests** (`tools/test_b2_codegen.py`, 15 tests) : ils reprennent le montage synthétique
des tests de B1 (`tools/test_b1_extract.py`), avec un faux `rexglue codegen` qui écrit des
sorties et un journal aux formats de ReXGlue.

| Cas | Tests |
|---|---|
| Entrées | `game/` qui n'est plus l'arborescence de PB-1 (fichier en plus, module changé, `.xexp`) ; manifeste invalide ; sortie non vide ; `app/rexglue.toml` ; configuration de test absente (bloque `run`, pas `rehearse`). Chaque fois, `codegen` ne démarre pas |
| Succès | Arguments exacts, sans `-f` ; dossier de travail `project/` ; limite `(1, 1)` ; C2.1 atteint ; `game/` inchangé ; manifeste changé par `sdk_version` seulement ; second passage refusé |
| C2.1 | Appels non résolus et *millicode* : `DIFFERS`, aucune adresse dans le résumé ; journal partiel refusé, C2.1 non mesuré |
| Après | Module modifié, autre changement du manifeste, lien dans les sorties : constats |
| Robustesse | Plantage et délai dépassé, avec `postflight` ; outil tué puis repris |
| Preuve | Une preuve de B1, ou d'une autre version du profil, n'ouvre pas B2 ; la répétition de B2 l'apporte |
| Vrai bubblewrap | Sonde à 29 ; écritures dans `game/`, un module, le dossier personnel et le dépôt refusées par `EROFS` ; sorties et réécriture du manifeste permises |

**Contrôle Nix `b2-codegen-selftest`** : les tests, puis la commande empaquetée avec le
**vrai** bubblewrap et le **vrai** `rexglue codegen`, sur un projet synthétique.
- `game/` contient deux fichiers texte aux noms des modules : ReXGlue les refuse à leurs
  premiers octets (« Unknown module magic »), avant tout décodage.
- [V] `prepare` sans constat ; `run` : sonde à 29, `codegen` sort avec 1, C2.1 non atteint,
  `game/` inchangé, manifeste inchangé, aucune sortie, rien d'écrit hors du dossier
  d'exécution, aucun objet `xenia_memory_*` laissé.
- Quand le bac à sable ne peut pas démarrer (CI) : `run` refuse, rien n'est généré.

**Les tests de B1 passent toujours** : 78 tests, sans changer leurs attentes, sauf la
version de l'outil (7) et deux contextes de test qui portent le profil.

**Non couvert, faute des fichiers du jeu** :
- un vrai XEX, le décodage, et une vraie génération réussie (sorties réelles, durée,
  mémoire et disque) [I] ;
- la preuve de l'option B avec le vrai systemd-coredump, pour B2 : seul `rehearse`, chez
  le porteur, la fait ;
- les vraies valeurs de la configuration du projet A.

## 11. Points à arbitrer avant le mandat de B2

1. **La configuration de test** : quels fichiers du projet A (`pc/config/default.toml`,
   `fifadllzf.toml`, fichiers de pointeurs), de quel commit (celui de l'audit, `498d18a`,
   ou un autre), et récupérés comment, hors de ce dépôt.
2. **`function_table_base`** : le SDK du projet accepte la clé (correctif A3). La garder
   pour le test avec la valeur du projet A, `0x86100000`, ou avec `0x86C10000`, qui
   convient à toute taille de code (`J2_A3_FUNCTION_TABLE.md` §7), ou la laisser hors de B2.
3. **Le délai** (2 heures par défaut) et les **ressources** : mémoire de l'invité dans le
   tmpfs du bac à sable, taille du code généré sur le disque [I].
4. **Le niveau du journal** : `info` proposé ; `warn` réduirait ce qui reste localement.

## 12. Ce qui revient dans le dépôt après B2

Seul le contenu de `summary.txt`, après la décision PB-2 : des nombres, des statuts, des
codes, `match` ou `DIFFERS`.

Ne reviennent jamais dans le dépôt : le code généré, les journaux, la désassemblée, et
les adresses avant PB-3 (D-007).

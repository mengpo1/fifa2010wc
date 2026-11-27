# Le moteur des étapes locales sur données privées

> Architecture née de B1 (`J2_B1_EXTRACTION.md`) et étendue pour B2
> (`J2_B2_COMPATIBILITY.md`). Elle sert aux étapes suivantes de J2 et peut servir à
> d'autres projets de portage qui lancent un outil tiers sur des données privées.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Le principe

Une **étape locale** lance **une commande d'un outil tiers** (ici ReXGlue) sur des données
privées, sur la machine du porteur, avec des contrôles avant et après. Les étapes
diffèrent par leur commande, leurs entrées et leurs sorties. Leurs protections sont les
mêmes.

Le travail est donc partagé ainsi :
- **le moteur** (`tools/b1_extract.py`) fait tout ce qui est commun ;
- **un profil** décrit une étape : ses dossiers, ses contrôles, sa commande, ses chiffres.

## 2. Ce que fait le moteur

| Mécanisme | Référence |
|---|---|
| Refus du root ; masque `077` ; variables `REX_*` retirées | `J2_B1_EXTRACTION.md` §2 |
| CP-1 par `private_guard` ; composants, parents, sockets et tubes du dossier privé | §2, §4.2 |
| Fermeture du magasin, construite par Nix, et refus sans elle (D-019) | §3.4 |
| Bac à sable bubblewrap par liste positive, sans réseau ; les dossiers en lecture seule du profil sont remontés après les dossiers inscriptibles, et peuvent donc être à l'intérieur de l'un d'eux | §3.1 |
| Sonde de confinement, dans le même bac à sable | §3.2 |
| *Core dumps* : mode tube seul, limite `1` pour la commande, preuve locale par `rehearse` (D-018) | §6 |
| Montages par identité et par événements ; CP-3 ; `preflight` et `postflight` (CP-4) | §4, §5, §2 |
| Commande lancée et surveillée dans le bac à sable : délai, signaux, état (`supervise`) | §2, §10 |
| État persistant, contrôles d'après isolés, reprise, `diagnose` | §10, §6.4 |
| Parcours d'une arborescence sans suivre de lien (`survey_tree`) : chiffres, anomalies jamais sautées, et **inventaire** optionnel (contenu haché, métadonnées, identité de chaque entrée) | §5 ; `J2_B2_COMPATIBILITY.md` §5.2 |
| Résumé par liste fixe : faits validés, codes de constats, jamais de texte libre | §9 |

## 3. Ce que décrit un profil

Un profil est une classe dérivée de `Profile` (`tools/b1_extract.py`). B1 est le profil par
défaut, défini dans le moteur lui-même.

| Élément | Rôle | B1 | B2 |
|---|---|---|---|
| `name`, `title`, `tool` | Dossiers `logs/<name>-run-<date>`, repère `<name>.marker`, titre du résumé | `b1` | `b2` |
| `writable`, `read_only` | Dossiers que le bac à sable peut écrire, ou doit refuser d'écrire | `game`, `app`, `tmp` | `generated`, `project`, `app`, `tmp` ; `game` et `project/config` refusés |
| `components`, `required` | Dossiers privés contrôlés, et ceux qui doivent exister | Disposition de CP-1 | Plus `generated`, `project`, `project/config` |
| `probe_checks()` | Contrôles de la sonde, dérivés des dossiers | 26 | 30, avec `write-denied-project-config` et `shm-private` |
| `prepare_inputs`, `prepare_last` | Contrôles des entrées, sans écriture | Image, `game/` vide, rapport J0 | Arborescence de PB-1, manifeste, entrées de configuration en cascade, inventaire de `project/config/` |
| `before_marker`, `before_run` | Juste avant `preflight`, puis juste avant la commande | Empreinte de l'image ; `game/` vide | Inventaire de `game/` ; sorties vides, manifeste et inventaire de `project/config/` inchangés |
| `run` | La commande, par `supervise` | `rexglue vfs dump` | `rexglue codegen` |
| `after_controls`, `result`, `summary_lines` | Contrôles d'après propres à l'étape, et ses lignes du résumé | Image, chiffres de PB-1 | Inventaires de `game/` et de `project/config/`, manifeste, `generated/`, complétude, `codegen.d`, C2.1 |
| `file` | Fichier du profil, auquel la preuve de l'option B est liée | Le moteur | `tools/b2_codegen.py` |

Un profil ajoute aussi ses noms d'étapes, ses codes de constats et ses faits aux listes
fixes du moteur (`STEP_NAMES`, `FINDING_CODES`, `SUMMARY_FACTS`, `PROBE_CHECK_NAMES`).
Sans cela, le résumé les écarte comme invalides.

## 4. Règles pour une nouvelle étape

1. **Un nouveau fichier de profil**, qui réutilise le moteur et les outils existants comme
   modules, sans les copier. B2 réutilise ainsi `private_project.py` (manifeste) et
   `address_compare.py` (C2.1).
2. **Ce qui tourne dans le bac à sable doit être dans la fermeture du magasin.** Si une
   étape y lance un autre programme, il faut l'ajouter aux racines de la fermeture du
   flake, jamais lier le magasin entier (D-019).
3. **La preuve de l'option B est propre au profil** : sa répétition est obligatoire, celle
   d'une autre étape ne vaut pas.
4. **Les tests réutilisent le montage synthétique de B1** (`tools/test_b1_extract.py`),
   comme `tools/test_b2_codegen.py`, avec un faux outil aux formats réels, et un essai avec
   le vrai bubblewrap.
5. **Un contrôle Nix** lance la commande empaquetée, si possible avec le vrai outil sur
   une entrée synthétique, comme `b2-codegen-selftest`.
6. **Les entrées et les sorties s'inventorient par `survey_tree`**, avec `listing` et, pour
   une entrée, `content`, et non par un parcours propre à l'étape. Une entrée illisible est
   un constat, jamais une entrée sautée.
7. **Un succès de l'outil tiers se prouve par ses sorties**, pas seulement par son code de
   sortie : ce qu'il écrit, et une ligne de fin de son journal (B2 : `codegen.stamp`,
   `codegen.d`, « Codegen summary »).

## 5. Ce qui reste propre à ce projet

Dans le moteur, ces éléments sont propres à `fifa2010wc` :
- la variable `WC2010_PRIVATE_DIR` et la disposition du dossier privé ;
- la référence J0 (49 fichiers, 8 dossiers, deux modules) et le nom de l'image ;
- l'entrée déjà relevée par CP-3 dans le magasin ;
- la garde `private_guard.py` et les renvois aux décisions du projet.

Tout le reste est générique : bac à sable, fermeture, preuve, montages, état, résumé.

**Hors du périmètre de cette étape, proposé seulement** : déplacer le moteur dans un
module neutre, et rendre ces éléments paramétrables, pour un autre projet de portage.
Aujourd'hui, seule la jonction entre moteur et profil est faite. B1 garde son
comportement : ses 78 tests passent, sa liste de sonde est inchangée
(`test_probe_checks_of_b2`), et `survey_tree` sans inventaire rend les mêmes chiffres
(`test_survey_tree_is_unchanged_without_listing`).

## 6. Limites

- Le moteur garde son nom, `b1_extract.py`, pour ne pas toucher aux renvois de B1, une
  étape validée (D-020).
- Les listes fixes sont globales au module : un processus ne fait tourner qu'un profil.
- Le moteur vaut pour les outils dont la commande s'exécute en une fois, sans
  interaction.

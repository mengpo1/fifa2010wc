# Étape B1 — extraction contrôlée de l'arborescence du disque

> Étape B1 de `docs/J2_PLAN.md` §4.1, [ticket #32](https://github.com/mengpo1/fifa2010wc/issues/32).
> PB-0 est franchi depuis le 2026-11-24 (D-017). **Ce document et son outil ne valent ni
> exécution de B1, ni PB-1.**
> - Ils ont été préparés sans aucune donnée du jeu : ni ISO, ni XEX, ni journal du jeu.
> - Les essais n'utilisent que des images et des fichiers synthétiques.
> - B1 s'exécute à la main, **sur la machine de l'utilisateur seulement**, une fois cette
>   procédure fusionnée.
> - PB-1 est décidé par l'orchestrateur, sur les résultats locaux.
>
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

L'outil est `tools/b1_extract.py`, empaqueté par le flake (`.#b1-extract`). Il enchaîne
dans un ordre fixe :
- les contrôles CP-1, CP-3 et CP-4 (`docs/J2_PHASE_B_CONTROLS.md`) ;
- l'extraction par `rexglue vfs dump` ;
- les chiffres de PB-1.

| Commande | Écrit | Lit l'image | Ce qu'elle fait |
|---|---|---|---|
| `prepare` | Rien | Non : seulement ses droits et sa taille | Diagnostic avant tout : CP-1 (`private_guard check-dir`) ; l'image `iso/fifa2010wc.iso` est un vrai fichier en lecture seule ; `game/` et `logs/` sont de vrais dossiers, ni liens ni points de montage, et `game/` est vide ; le SDK est construit ; le dépôt est propre ; les emplacements surveillés sont lisibles ; réglage des *core dumps* |
| `rehearse` | Un dossier d'exécution sous `logs/` | Non | Tous les contrôles de `run`, sans l'extraction : pour essayer la surveillance avant le vrai passage |
| `run` | `game/` et un dossier d'exécution sous `logs/` | Oui, pour son empreinte, et par `rexglue` | B1 : `prepare`, puis le §2 |
| `verify` | Rien | Non | Les chiffres de PB-1 de `game/`, à relire plus tard |

**L'outil ne supprime, ne déplace et n'écrase rien**, même après un échec. Il refuse de
tourner en root.

Codes de sortie :
- `0` : aucun constat, et, pour `run` et `verify`, des chiffres de PB-1 conformes ;
- `1` : au moins un constat ;
- `2` : erreur d'utilisation.

## 1. `rexglue vfs dump` en v0.11.0 [V]

**Syntaxe.** Elle a été relevée dans l'aide, dans le bac à sable de Nix, sans aucune image,
puis confirmée par le code (`src/rexglue/command/vfs_command.cpp`) :

```
rexglue vfs dump [OPTIONS] source destination

POSITIONALS:
  source PATH REQUIRED        Container file, or a folder that holds 1
  destination PATH REQUIRED   Folder to extract into
```

- Les deux arguments sont positionnels et obligatoires. Sans eux, la commande sort en
  `106` (« source is required »), sans rien écrire.
- La commande n'a pas d'option propre.
- Les options générales de `rexglue` ne sont pas utilisées : `--log-level`,
  `--log-file`, `-v` et `-f` (`src/rexglue/main.cpp`). Le niveau du journal reste donc
  `info`.
- L'outil lance exactement `rexglue vfs dump <image> <dossier game>`, sans `nix run`,
  par le chemin du SDK dans le magasin.

**Ce que fait la commande :**
1. Elle démarre l'application (`tools.Start()`) : réglages, puis journal.
2. Elle ouvre l'image en lecture seule (`MappedMemory::Mode::kRead`,
   `src/filesystem/container.cpp`). Une image XDVDFS est un conteneur `GDFX`.
3. Elle écrit sur **stderr** un bloc `Extracting container:`. Il contient :
   - `Source`, le chemin de l'image : l'outil ne le lit jamais ;
   - `Type` ;
   - `Nodes`, le nombre de nœuds, **racine comprise** : c'est le premier nœud ;
   - `Bytes`, la somme des tailles de tous les nœuds, **tables des dossiers comprises**.
     Dans le contrôle Nix, elle vaut 9197 pour 5101 octets de fichiers : elle n'est donc
     pas comparée.
4. Elle extrait (`Container::Extract`) :
   - le dossier de destination est créé s'il manque ;
   - chaque nom passe `IsSafeName` : pas de nom vide, `.`, `..`, ni `\`, `/` ou `:` ;
   - un fichier existant est **écrasé** (`std::ios::trunc`), et un lien serait suivi.
     C'est pourquoi l'outil exige un dossier `game/` vide ;
   - **après un échec**, la commande supprime elle-même ce qu'elle a écrit. Elle
     supprime aussi le dossier de destination s'il n'existait pas avant elle. L'outil, lui,
     ne supprime rien, et `game/` existe toujours avant l'extraction.
5. Elle sort en `0` si tout réussit, en `1` sinon.

**Aucun décodage des XEX** : `vfs dump` copie des fichiers. Il n'appelle pas le chargeur des
modules (`docs/J2_A1_SDK_INVENTORY.md` §3.3).

**Destinations et effets annexes**, avec l'environnement de l'outil (§2) :

| Destination | Source | Constat |
|---|---|---|
| `game/` | L'arborescence extraite | [V] contrôle Nix : fichiers en `0600`, dossiers créés sous le masque `077` |
| `logs/b1-run-<date>/rexglue_NNN.log` | Le journal de l'application, par `REX_APP_LOG_ROOT` | [V] contrôle Nix ; niveau `info` |
| `app/` (`REX_APP_ROOT`), `tmp/` (`TMPDIR`) | Dossiers de l'application, déclarés par précaution | [V] rien n'y est écrit dans le contrôle Nix |
| Dossier de l'exécutable, dans le magasin | Le test d'écriture `.rex_write_check_<pid>_<n>` | [V] A1 §2 : sans privilèges, l'essai échoue et ne laisse rien. `nix store verify` le contrôle après |
| `/dev/shm` | — | [V] A1 §3.3 : aucun objet. `private_guard` le vérifie |
| Dossier personnel, XDG | — | [V] contrôle Nix : rien |

## 2. Ce que fait `run`, dans l'ordre

1. **Refus du root**, avant tout.
2. **`prepare`** (voir le tableau). Un constat arrête tout : rien n'est créé.
3. **Réglages de l'étape**, hérités par chaque commande lancée ensuite :
   - masque `077` ;
   - *core dumps* désactivés : limite `RLIMIT_CORE` à `0`, souple **et** stricte, ce qui
     empêche `rexglue` de la relever ;
   - dossier de travail : le dossier privé ;
   - `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` et `REX_APP_ROOT`
     dans le dossier privé, comme au `docs/J2_PHASE_B_CONTROLS.md` §2 ;
   - **toute variable `REX_*` héritée du shell est retirée**, par exemple un
     `REX_LOG_LEVEL=trace`. Seules celles de l'outil restent, dont `REX_APP_LOG_ROOT` ;
   - `NO_COLOR=1`.
4. **Dossier d'exécution** : `logs/b1-run-<date UTC>`, créé en `0700`. Un dossier qui
   existe déjà n'est jamais réutilisé. Tous les fichiers de l'outil y sont créés en `0600`,
   sans écraser ni suivre de lien.
5. **Points de montage**, relevés avant l'étape (§3).
6. **Empreinte de l'image** avant l'étape : SHA-256, et son identité (appareil, inode,
   taille, dates, droits).
7. **CP-3 avant** (§4). Un constat arrête tout, avant `preflight`.
8. **`preflight`**, avec :
   - `--dest` pour `game`, `logs`, `app` et `tmp`. Ce sont toutes les destinations
     possibles : `game` et `logs` sont celles observées (§1) ;
   - `--game-root game`, `--sdk-bin` et `--marker` dans le dossier d'exécution.

   S'il ne répond pas `OK`, rien n'est lancé ; sans repère, `postflight` est noté
   « non lancé ».
9. **À partir du repère, `postflight` s'exécute dans tous les cas** : réussite, échec,
   plantage, délai dépassé, interruption ou erreur de l'outil.
   1. Le SDK était construit avant le début des contrôles : sa date de changement d'état
      précède le début. `game/` est encore vide.
   2. **`rexglue vfs dump`**. Sa sortie standard et ses erreurs vont **seulement** dans le
      dossier d'exécution. Délai par défaut : 2 heures (`--timeout`).
      - Un code non nul, un signal, un délai dépassé ou une interruption est un constat.
      - Le code et le signal sont consignés.
   3. **`postflight`**, avec `--sdk` (`nix store verify`), `--repo` (`git status`),
      `--watch "$HOME"`, `--watch /tmp`, et un `--watch` par point de montage (§3).
      `/dev/shm` est toujours contrôlé.
10. **Points de montage après l'étape** : comparés à ceux d'avant.
11. ***Core dumps*** (§5).
12. **CP-3 après**, comparé au relevé d'avant.
13. **Empreinte de l'image après**, comparée à celle d'avant.
14. **Chiffres de PB-1** (§6).

**Chaque étape a un statut** :
- `ok` ;
- `finding` : un constat ;
- `skipped` : non lancée, avec la raison.

Le code de sortie de chaque commande est consigné : `check-dir`, `preflight`, `postflight`,
`find`, `rexglue` et `coredumpctl`. **Aucun `set -e`** : un constat n'interrompt pas les
contrôles suivants, qui ne font que lire. Un contrôle qui ne peut pas s'exécuter est un
constat, jamais un `OK`.

**Règle d'arrêt.** Après un constat, B1 est arrêtée, et B2 ne commence pas :
- on ne supprime rien ;
- on garde le dossier d'exécution comme preuve locale ;
- on rapporte le résumé (§7).

## 3. Emplacements surveillés et points de montage

- **`postflight` surveille** :
  - le dossier personnel ;
  - `/tmp` ;
  - le dépôt (`--repo`) ;
  - chaque point de montage situé sous l'un d'eux.
- **Les points de montage** viennent de `findmnt -rn -o TARGET`, lu à chaque exécution.
  - Ni leur nombre ni leur liste ne sont écrits dans le dépôt. Le porteur en a relevé 31
    sous son dossier personnel à l'essai à blanc de CP-4.
  - Les octets protégés par `findmnt` (`\x20` pour une espace, par exemple) sont décodés.
- **Ce qui est fait de chaque point de montage**, sous le dossier personnel, `/tmp` ou le
  dépôt :

  | Point de montage | Traitement |
  |---|---|
  | Un dossier | Surveillé à part, par `--watch`. `private_guard` le cherche entièrement, et ne le compte plus comme un constat sous son dossier parent (`docs/J2_PHASE_B_CONTROLS.md` §3.1) |
  | Un fichier monté seul | Il est vu, avec ses dates, dans son dossier parent, qui est cherché |
  | Absent | Passé quand même à `--watch` : `postflight` en fait un constat |
  | Dans le dossier privé | Non surveillé, comme tout le dossier privé. Il est compté |

- **Sont des constats bloquants** :
  - un point de montage apparu ou disparu pendant l'étape ;
  - un point de montage illisible : `prepare` le signale déjà ;
  - un dossier d'un autre système de fichiers qui ne serait pas dans la liste.
- **Aucune exclusion au cas par cas.** La seule exception reste celle des dossiers
  `PrivateTmp` de systemd vérifiés (#30).
- Les autres points de montage, hors de ces emplacements, ne sont pas comparés : ils ne
  sont pas surveillés non plus.

## 4. CP-3 : relevé du magasin Nix

Ce sont les deux recherches de `docs/J0_ISO_IDENTIFICATION.md` §6, lancées telles quelles
avant et après l'étape :

```bash
find /nix/store -maxdepth 1 -type f -size +100M
```

```bash
find /nix/store -maxdepth 3 -type f \( -iname '*.xex' -o \( -iname '*.iso' -size +100M \) \)
```

- `find` ne lit que des noms et des tailles : **aucun fichier du magasin n'est ouvert**.
- Le fichier `nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude`, déjà relevé, n'est ni ouvert ni
  supprimé. Le résumé dit seulement s'il figure dans la liste.
- **Constats** :
  - une recherche qui sort avec un code non nul : l'outil s'arrête avant `preflight` ;
  - une correspondance nouvelle après l'étape.
- Une correspondance disparue n'est qu'une note.
- Ces recherches **ne sont pas exhaustives** : extension, taille, profondeur. Elles
  donnent des indices, pas une preuve.

## 5. *Core dumps* et systemd-coredump

**Sur la machine du porteur** (CP-4, D-017) :
- `kernel.core_pattern` transmet les *core dumps* par un tube à systemd-coredump ;
- l'essai à blanc d'un `SIGSEGV` sous `ulimit -c 0` a donné `COREFILE none`.

**Ce que cela veut dire** (`docs/J2_A6_LINUX_GAPS.md` §5.2) :
- [V] avec un tube, le noyau n'applique pas `RLIMIT_CORE` (`core(5)`) : il transmet le
  plantage au programme du tube ;
- [V] systemd-coredump ne traite le *core dump* que si la limite du processus le permet
  (`systemd-coredump(8)`). [H] Avec `0`, il ne garde rien : c'est ce qu'a montré
  `COREFILE none`, pour un plantage ;
- [V] il note toujours un résumé dans le journal du système : signal, ligne de commande,
  dossier de travail, carte mémoire. Ce sont des chemins et des métadonnées, pas le
  contenu de la mémoire, mais ils sortent du dossier privé.

`ulimit -c 0` seul ne garantit donc pas qu'aucune donnée du processus ne soit traitée lors
d'un plantage.

**Ce que fait l'outil** :
- il lit `/proc/sys/kernel/core_pattern` et `/proc/sys/fs/suid_dumpable`. Il ne garde que
  l'existence d'un tube et le nom de son programme ;
- il fixe `RLIMIT_CORE` à `0`, en limite souple et stricte ;
- après l'étape, il lance `coredumpctl list --no-pager --since=@<début>`. **Toute
  entrée est un constat**, même celle d'un autre programme : elle est examinée
  localement, jamais partagée ;
- si les *core dumps* vont à systemd-coredump et que `coredumpctl` manque, c'est un
  constat.

**Ce que l'outil ne fait pas** :
- **aucune modification du système** ;
- **aucune commande non essayée** n'est proposée. Le réglage `Storage=none
  ProcessSizeMax=0` de `coredump.conf` reste une décision du porteur
  (`docs/J2_PHASE_B_CONTROLS.md` §5).

**Piste non essayée, non appliquée** [H] : d'après le code du noyau, non vérifié dans ce
dépôt, un *core dump* par tube est abandonné quand la limite vaut exactement `1`
(`do_coredump()`, `fs/coredump.c`). Ce serait une mesure propre au processus. Elle
demanderait :
- de changer `private_guard`, qui exige `0` ;
- un essai sur la machine du porteur.

C'est à l'orchestrateur d'en décider.

## 6. Chiffres de PB-1

Les références sont celles du rapport J0 (`docs/reports/J0_IDENTIFICATION.md` §2). Elles
sont écrites dans l'outil, et un test vérifie qu'elles sont celles du rapport :
- 49 fichiers et 8 dossiers ;
- les SHA-256 de `default.xex` et `fifadllzf.xex`.

**Comptage de `game/`** :
- **la racine n'est pas comptée**, comme dans l'outil J0, qui compte les entrées sous la
  racine du disque. ReXGlue, lui, la compte : l'outil vérifie que
  `Nodes = fichiers + dossiers + 1` ;
- les noms qui commencent par un point **sont comptés**, et leur nombre est donné ;
- chaque dossier est ouvert par `O_NOFOLLOW`, à partir du descripteur de son parent :
  **un lien n'est jamais suivi**.

**Anomalies**, jamais comptées, et chacune un constat :
- un lien ;
- un fichier spécial ;
- un fichier à plusieurs liens physiques ;
- une entrée d'un autre système de fichiers ;
- une entrée illisible ;
- une entrée changée pendant le comptage ;
- deux noms pour un même module, qui ne diffèrent que par la casse.

**Modules** : `default.xex` et `fifadllzf.xex` sont cherchés à la racine de `game/`, sans
tenir compte de la casse. Ils sont lus par `O_NOFOLLOW`.

**Image** :
- son SHA-256 et son identité doivent être les mêmes avant et après l'étape ;
- le rapport J0 public ne donne pas l'empreinte de l'image. Si le rapport J0 local existe,
  `--j0-report` la compare aussi : c'est le fichier JSON écrit par `iso-identify --json`.

**Critères et décision** :
- chaque critère est donné avec sa valeur attendue, sa valeur trouvée et `match` ou
  `DIFFERS` ;
- **l'outil ne déclare jamais PB-1**. L'orchestrateur décide, sur le résumé.

## 7. Procédure pour le porteur du projet

Après la fusion de cette procédure, sur la machine de l'utilisateur, depuis une copie
propre du dépôt, hors du dossier privé.

1. **Fermer** le navigateur, l'éditeur et tout programme qui écrit dans le dossier
   personnel pendant l'étape.
2. **Construire l'outil**, ce qui construit aussi le SDK, **avant** tout contrôle :

   ```bash
   B="$(nix build --no-link --print-out-paths .#b1-extract)/bin/fifa2010wc-b1-extract"
   ```

3. **Diagnostic**, qui n'écrit rien :

   ```bash
   "$B" --repo "$PWD" prepare
   ```

4. **Essai de la surveillance**, sans extraction :

   ```bash
   "$B" --repo "$PWD" rehearse
   ```

5. **B1**, seulement si les deux commandes précédentes répondent `outcome: no finding`.
   - Avec le rapport J0 local, s'il existe à cet endroit :

     ```bash
     "$B" --repo "$PWD" --j0-report "$WC2010_PRIVATE_DIR/logs/j0-identification.json" run
     ```

   - Sinon, sans `--j0-report` :

     ```bash
     "$B" --repo "$PWD" run
     ```

6. **Partage** (CP-5, `docs/J2_PHASE_B_CONTROLS.md` §4) : seulement `summary.txt`, après
   le contrôle `tree` et une relecture.
   - Il ne contient que des nombres, des statuts, les empreintes autorisées (D-007) et le
     *genre* de chaque constat.
   - Il ne contient ni chemin local, ni nom de fichier du jeu autre que les deux modules,
     ni sortie de `rexglue`.
   - **Ne jamais partager** `report.json` ni les autres fichiers du dossier d'exécution.
     Ils nomment des chemins locaux, et les sorties de `rexglue` nomment l'image.

**Variable requise** : `WC2010_PRIVATE_DIR`, comme pour `private_guard`.

**L'outil ne refait pas** :
- la vérification de `core.hooksPath` et du contrôle du dépôt (CP-6) ;
- celle des adresses (CP-7).

Elles restent à faire comme au `docs/J2_PHASE_B_CONTROLS.md` §1 et §5.

## 8. Essais sans données du jeu, et ce qu'ils ne couvrent pas

**Tests unitaires** (`tools/test_b1_extract.py`), lancés par le contrôle Nix
`b1-extract-selftest` sous l'utilisateur sans privilèges du bac à sable :
- **ce qui est simulé** : `rexglue`, `findmnt`, `coredumpctl` et `nix` sont remplacés par
  de petits scripts qui notent leurs arguments ;
- **ce qui est réel** : `private_guard`, `find` et `git` ;
- **ce qu'ils couvrent** :

  | Domaine | Cas |
  |---|---|
  | Extraction | Réussite ; échec ; plantage par signal ; délai dépassé |
  | Gardes | Constat de `preflight` ; codes 2 et 3 de `private_guard` ; échec de `nix store verify` |
  | Image | Absente, inscriptible, lien, changée pendant l'étape |
  | Dossiers | `game/` non vide, et un second passage refusé ; `game/` ou `logs/` en lien ; dépôt modifié ; SDK hors du magasin, absent ou d'une autre version |
  | Points de montage | Dossiers, fichier monté, nom avec espace, absent, illisible, apparu pendant l'étape, `findmnt` en échec |
  | CP-3 | Fichier connu, inchangé ; correspondance nouvelle ; erreur de `find` |
  | *Core dumps* | Entrée consignée |
  | PB-1 | Nombres et empreintes différents ; module absent ; anomalies ; nœuds et type de ReXGlue ; rapport J0 local |
  | Confinement | Écritures hors du dossier privé : dossier personnel, `/tmp`, point de montage, dépôt. Destinations déclarées. Environnement de `rexglue` : masque, limite, dossier de travail, variables. Sortie console courte, sans chemin local |
  | Envoi | Aucun programme d'envoi lancé (`curl`, `wget`, `ssh`, `scp`, `rsync`, `nc`, `gh`, `nix-store`) ; `git` seulement pour `status` et `rev-parse` ; `nix` seulement pour `store verify` ; aucun module réseau importé |
  | Root | Refusé avant tout (simulé) |

**Contrôle Nix `b1-extract-selftest`** :
- **avec le vrai `rexglue vfs dump`**, par la commande empaquetée, sur une image XDVDFS
  synthétique, faite de fichiers texte, dont deux portent le nom des modules :
  - les chiffres de PB-1 concordent ;
  - `Nodes` vaut 9 pour 5 fichiers et 3 dossiers ;
  - le bloc de ReXGlue est sur stderr, et son journal est dans le dossier d'exécution ;
  - rien n'est écrit ailleurs que dans `game/` et le dossier d'exécution, ni dans le
    dossier personnel ;
- **un second passage** est refusé ;
- **un fichier qui n'est pas un conteneur** : `rexglue` échoue, `postflight` passe, et
  `game/` reste vide.

**Non couvert, faute de root ou de la machine du porteur** :
- **un vrai autre système de fichiers** ou un vrai point de montage : il faut root. Les
  numéros d'appareil sont simulés dans les tests unitaires. Les 31 points de montage ne
  sont essayés que par `rehearse`, chez le porteur ;
- **un vrai enregistrement de systemd-coredump**, et un vrai `SIGSEGV` de `rexglue` : un
  plantage réel transmettrait un *core dump* au système de la CI. Le plantage est simulé
  par `SIGKILL` ;
- **`nix store verify` et `coredumpctl` réels** : ils ne fonctionnent pas dans le bac à
  sable, qui n'a ni démon Nix ni journal. Des scripts vérifient seulement leurs arguments ;
- **`/tmp`** : le bac à sable de Nix en fournit un dossier à part, donné par une option de
  test ;
- **le refus du root** : simulé, car les tests tournent sans privilèges ;
- **le comportement de `rexglue` sur l'image réelle** : taille, temps, journal. Il n'est
  connaissable qu'en B1.

## 9. Ce qui revient dans le dépôt après B1

Seul le contenu de `summary.txt`, ou ses chiffres :
- les nombres ;
- les statuts et les codes de sortie ;
- les empreintes des deux modules et de l'image ;
- le genre et le nombre des constats.

Le tout, sous `docs/reports/`, après la décision de l'orchestrateur sur PB-1.

Ne reviennent jamais dans le dépôt :
- l'arborescence ;
- les noms des fichiers du jeu ;
- les journaux ;
- les sorties de `rexglue`.

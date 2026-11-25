# Étape B1 — extraction contrôlée de l'arborescence du disque

> Étape B1 de `docs/J2_PLAN.md` §4.1, [ticket #32](https://github.com/mengpo1/fifa2010wc/issues/32).
> Version 3 :
> - corrections de la revue de l'orchestrateur sur la PR #33 (constats B1-R01 à B1-R07) ;
> - arbitrages du porteur, D-018 : option B pour les plantages, rapport J0 local
>   obligatoire.
> PB-0 est franchi depuis le 2026-11-24 (D-017). **Ce document et son outil ne valent ni
> exécution de B1, ni PB-1.**
> - Ils ont été préparés sans aucune donnée du jeu : ni ISO, ni XEX, ni journal du jeu.
> - Les essais n'utilisent que des images et des fichiers synthétiques.
> - B1 s'exécute à la main, **sur la machine de l'utilisateur seulement**, une fois cette
>   procédure fusionnée.
> - **`run` reste bloqué** tant que `rehearse` n'a pas apporté, sur la machine du porteur
>   et dans le même démarrage, la preuve locale du §6.
> - PB-1 est décidé par l'orchestrateur, sur les résultats locaux.
>
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

L'outil est `tools/b1_extract.py`, empaqueté par le flake (`.#b1-extract`). Il enchaîne
dans un ordre fixe :
- les contrôles CP-1, CP-3 et CP-4 (`docs/J2_PHASE_B_CONTROLS.md`) ;
- l'extraction par `rexglue vfs dump`, **confinée** dans un bac à sable bubblewrap (§3) ;
- les chiffres de PB-1.

| Commande | Écrit | Lit l'image | Ce qu'elle fait |
|---|---|---|---|
| `prepare` | Rien | Non : seulement ses droits et sa taille | Diagnostic : tous les contrôles qui n'écrivent rien (§2, étape 2) |
| `rehearse` | Un dossier d'exécution sous `logs/` | Non | Tous les contrôles de `run`, la sonde de confinement et, en mode tube, la preuve locale de l'option B : deux plantages synthétiques (§6). Pas d'extraction |
| `run` | `game/` et un dossier d'exécution | Oui, pour son empreinte, et par `rexglue` dans le bac à sable | B1 |
| `verify` | Rien | Non | Les chiffres de PB-1 de `game/`, à relire plus tard |
| `resume` | Des fichiers `-resume` dans le dossier d'exécution | Oui, pour l'empreinte d'après | Les contrôles d'après l'extraction, pour un passage interrompu sans eux (§10). Ne relance jamais l'extraction |

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
- L'outil lance exactement `rexglue vfs dump <image> <dossier game>`, par le chemin du SDK
  dans le magasin, dans le bac à sable du §3. Jamais par `nix run`.

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
     pas comparée (arbitrage de la revue).
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

**Destinations et effets annexes**, avec l'environnement et le bac à sable de l'outil :

| Destination | Source | Constat |
|---|---|---|
| `game/` | L'arborescence extraite | [V] contrôle Nix : fichiers en `0600` |
| `logs/b1-run-<date>/rexglue_NNN.log` | Le journal de l'application, par `REX_APP_LOG_ROOT` | [V] contrôle Nix ; niveau `info` |
| `app/` (`REX_APP_ROOT`), `tmp/` (`TMPDIR`) | Dossiers de l'application, inscriptibles par précaution | [V] rien n'y est écrit dans le contrôle Nix |
| Tout le reste | — | Lecture seule dans le bac à sable (§3) |

## 2. Ce que fait `run`, dans l'ordre

1. **Refus du root**, avant tout.
2. **Contrôles sans écriture** (ceux de `prepare`). Un constat arrête tout, et rien n'est
   créé :
   - CP-1 : `private_guard check-dir` ;
   - aucun passage précédent inachevé (§10) ;
   - l'image : un vrai fichier, en lecture seule, à son chemin canonique ;
   - le dossier privé, composant par composant (§4.2) ;
   - le SDK construit, le dépôt propre ;
   - la table des montages et les emplacements surveillés (§4.1) ;
   - le réglage des *core dumps* et la preuve locale de l'option B (§6) ;
   - le rapport J0 local (§7).
3. **Réglages de l'étape**, hérités par chaque commande lancée ensuite :
   - masque `077` ;
   - `RLIMIT_CORE` de l'outil : `0` en limite souple, ce que `private_guard` contrôle, et
     `1` en limite stricte, pour pouvoir donner `1` au bac à sable (§6) ;
   - `TMPDIR`, les dossiers XDG et `REX_APP_ROOT` dans le dossier privé, et
     `REX_APP_LOG_ROOT` dans le dossier d'exécution ;
   - **toute variable `REX_*` héritée du shell est retirée**.
4. **Dossier d'exécution** `logs/b1-run-<date UTC>`, créé en `0700`, avec `state.json`
   (§10).
5. **Avant le repère** :
   1. la table des montages, et l'ouverture de `/proc/self/mountinfo` pour les événements
      (§4.1) ;
   2. **la sonde de confinement** dans le bac à sable (§3.2). Un échec arrête tout ;
   3. l'empreinte de l'image, comparée au rapport J0 local : **une différence arrête tout,
      avant `rexglue`** ;
   4. CP-3 avant (§5).
6. **`preflight`**, avec :
   - `--dest` : le dossier d'exécution, `game/`, `app/` et `tmp/` ;
   - `--game-root game`, `--sdk-bin`, et `--marker` dans le dossier d'exécution.
7. **Le repère décide** :
   - absent, alors que `preflight` a répondu `OK` : constat `preflight-no-marker` ;
   - présent, **`postflight` s'exécute dans tous les cas**, même si `preflight` a trouvé
     quelque chose. L'extraction, elle, n'a lieu que sans aucun constat.
8. **L'extraction**, dans le bac à sable :
   - le SDK était construit avant le début des contrôles, `game/` est encore vide, aucun
     dossier du dossier privé n'a été remplacé, et la preuve du §6 vaut toujours ;
   - `RLIMIT_CORE` à **`1`**, souple et stricte, pour ce seul processus (§6) ;
   - sortie standard et erreurs dans le dossier d'exécution seulement ;
   - un code non nul, un signal, un délai dépassé (2 heures par défaut, `--timeout`) ou
     une interruption est un constat.
9. **Après** : `postflight` (le dossier personnel, `/tmp`, le dépôt, chaque montage
   surveillé, `/dev/shm`, `--sdk`), puis :
   - les montages, comparés, et leurs événements ;
   - les *core dumps* consignés ;
   - CP-3 après ;
   - l'identité des dossiers privés ;
   - l'empreinte de l'image, comparée à celle d'avant et au rapport J0 ;
   - les chiffres de PB-1 (§8).
10. **Le rapport** : `report.json` (local), `summary.txt` (§9), et `state.json` à
    `complete`.

**Statuts** : `ok`, `finding` ou `skipped`, avec le code de sortie de chaque commande.
**Aucun `set -e`** : après le repère, un constat n'interrompt pas les contrôles suivants,
qui ne font que lire. Un contrôle qui ne peut pas s'exécuter est un constat, jamais un `OK`.

**Règle d'arrêt.** Après un constat, B1 est arrêtée, et B2 ne commence pas : on ne
supprime rien, on garde le dossier d'exécution, on rapporte le résumé.

## 3. Confinement de l'extraction (B1-R02)

La surveillance par `postflight` constate après coup. Le bac à sable **empêche** : seul le
processus d'extraction est confiné, sans privilèges et sans modifier le système.

### 3.1 Le bac à sable

[V] bubblewrap 0.12.0 de nixpkgs (`DEPENDENCIES.md`), sans setuid. Il demande que le
système permette les espaces de noms utilisateur sans privilèges, ce que NixOS fait par
défaut. Sinon, `run` refuse (`sandbox-unavailable`).

| Option | Effet |
|---|---|
| `--unshare-all --unshare-user` | Nouveaux espaces de noms : utilisateur, montages, processus, IPC, UTS, cgroup, et **réseau**. Le bac à sable n'a qu'une boucle locale à lui |
| `--disable-userns` | Aucun nouvel espace de noms utilisateur à l'intérieur |
| `--die-with-parent`, `--new-session` | Le bac à sable meurt avec l'outil ; pas d'accès au terminal |
| `--ro-bind / /` | **Tout le système de fichiers en lecture seule**, dont le dossier personnel, le magasin et le dépôt |
| `--dev /dev`, `--proc /proc` | Un `/dev` minimal et le `/proc` du bac à sable |
| `--tmpfs` de 16 Mio | Sur `/tmp`, `/run`, `/var/tmp` et `/nix/var/nix/daemon-socket`, quand ils existent : ils cachent les sockets des services (D-Bus, journal, démon Nix, session) et les fichiers temporaires partagés |
| `--tmpfs` de 1 Mio sur le dossier personnel, puis `--remount-ro` | **Le dossier personnel est vide et en lecture seule** : ses fichiers et ses sockets sont hors d'atteinte. Seul le chemin du dossier privé y est recréé |
| `--ro-bind` du dossier privé | Le dossier privé en lecture seule, même sous `/tmp` |
| `--bind` | **Seuls inscriptibles** : le dossier d'exécution, `game/`, `app/` et `tmp/` |

### 3.2 La sonde de confinement

Avant le repère, un programme synthétique est lancé dans **le même bac à sable**, avec les
mêmes options et la même limite de *core dump*. Il ne contient aucune donnée du jeu. Ses
23 contrôles :

| Contrôles | Attendu |
|---|---|
| `write-denied-home`, `-private-root`, `-iso`, `-store`, `-repo` | Création d'un fichier refusée |
| `write-allowed-run-folder`, `writable-game`, `writable-app`, `writable-tmp` | Écriture permise |
| `image-read-only` | L'image est lisible et non inscriptible |
| `tmp-private-empty`, `run-hidden`, `nix-daemon-socket-hidden` | Dossiers cachés vides, socket du démon Nix absente |
| `home-hidden` | Le dossier personnel ne montre que le chemin du dossier privé |
| `net-loopback-only` | Seule l'interface `lo` |
| `net-tcp-host-unreachable` | Une socket TCP que l'outil écoute sur la boucle locale de la machine est injoignable |
| `net-tcp-remote-unreachable`, `net-udp-unreachable` | Une adresse de test (`192.0.2.1`) est injoignable, sans délai d'attente : il n'y a pas de route |
| `net-abstract-unix-isolated` | Une socket abstraite que l'outil écoute est injoignable |
| `userns-disabled` | Un nouvel espace de noms utilisateur est refusé |
| `core-limit-one` | `RLIMIT_CORE` vaut `(1, 1)` à l'intérieur (§6) |
| `no-capabilities`, `pid-isolated` | Aucune capacité ; seuls les processus du bac à sable |

Un seul contrôle en échec est un constat `sandbox-probe-failed`, et rien n'est extrait.
`rehearse` fait la même sonde : c'est l'essai du confinement sur la machine du porteur.

[V] Dans le contrôle Nix `b1-extract-selftest`, la sonde passe ses 23 contrôles, et le vrai
`rexglue vfs dump` extrait l'image synthétique dans ce bac à sable. Le test
`test_real_sandbox_confines_the_extraction` lance un faux `rexglue` qui tente d'écrire dans
le dossier personnel, le dossier privé, `iso/`, le dépôt et l'image : **chaque écriture est
refusée par `EROFS`**, et rien n'apparaît sur la machine.

### 3.3 Ce que le confinement ne couvre pas

À arbitrer ; aucun de ces points n'est présenté comme couvert :
- **lecture** : le processus lit tout ce que l'utilisateur peut lire. Il ne peut ni l'écrire
  ailleurs que dans ses destinations, ni l'envoyer sur le réseau ;
- **sockets Unix de fichier** : celles du dossier personnel, de `/run` (D-Bus, journal,
  session, sockets de l'utilisateur sous `$XDG_RUNTIME_DIR`), de `/tmp` (X11) et du démon Nix
  sont cachées. Une socket posée ailleurs reste joignable, par exemple sous `/var/lib` ou
  sous un point de montage hors du dossier personnel. Les sockets abstraites sont isolées
  par l'espace de noms réseau ;
- **l'outil doit être hors du dossier personnel** : le bac à sable le cache. La commande
  empaquetée, dans `/nix/store`, convient ; un lancement depuis une copie du dépôt sous le
  dossier personnel est refusé (`sandbox-unavailable`) ;
- **tmpfs** : ce qui y est écrit reste en mémoire, et peut aller dans l'espace d'échange,
  comme toute mémoire de processus. Il disparaît à la fin du bac à sable ;
- **les outils de contrôle** (`private_guard`, `find`, `findmnt`, `git`, `coredumpctl`,
  `nix`) ne sont pas confinés. Ils ne lisent aucune donnée du jeu ;
- **un plantage** : voir le §6.

## 4. Montages et dossier privé

### 4.1 Identité des montages (B1-R01)

- **Source** : `findmnt --list --json --output` avec ces colonnes : identifiant, identifiant
  unique, parent, `MAJ:MIN`, racine dans le système de fichiers, cible, type, source,
  options VFS et du système de fichiers, propagation. Une sortie illisible ou un échec est
  un constat.
- **Portée** : un montage est dans la portée quand sa cible est un des emplacements
  surveillés (le dossier personnel, `/tmp`, le dépôt) ou le dossier privé, ou bien sous l'un
  d'eux, ou bien un de leurs parents, comme `/` ou `/home`.
- **Surveillés à part par `postflight`** (`--watch`) : les dossiers montés sous le dossier
  personnel, `/tmp` ou le dépôt, hors du dossier privé. Ni leur nombre ni leur liste ne sont
  écrits dans le dépôt. Le porteur en a relevé 31 à l'essai à blanc de CP-4.
- **Comparés avant et après**, par cible et par **tous** ces attributs : un montage apparu,
  disparu, remplacé au même chemin (autre identifiant), remonté (autres options) ou lié
  ailleurs (autre racine) est un constat `mount-changed`.
- **Événements** : `/proc/self/mountinfo` est ouvert avant le premier relevé. Le noyau le
  signale (`POLLPRI`) à chaque montage ou démontage de cet espace de noms. Un changement est
  donc vu même s'il a été défait avant le second relevé : c'est le constat `mount-events`.
- **Limites dans le temps** : la fenêtre va de l'ouverture de `mountinfo`, avant la sonde,
  jusqu'au relevé d'après `postflight`. Un événement est vu dans tout l'espace de noms :
  un montage sans rapport avec B1, fait par le système pendant ce temps, est aussi un
  constat. Il est à expliquer avant de continuer.
- Un montage qui n'est pas un dossier, comme un fichier lié, est cherché comme entrée de
  son dossier parent.

### 4.2 Dossier privé (B1-R07)

- **Parents** : chaque dossier parent du dossier privé appartient à root ou à
  l'utilisateur, et personne d'autre ne peut le modifier, sauf un dossier « sticky » de root
  comme `/tmp`. Sinon : `ancestor-unsafe`. Dans un espace de noms où root n'est pas
  « mappé », comme le bac à sable de construction de Nix, ses fichiers apparaissent sous
  l'uid de débordement, accepté là seulement.
- **Composants** : `iso`, `game`, `logs`, `tmp`, `app`, `xdg` et ses sous-dossiers
  `config`, `data` et `cache` doivent être de vrais dossiers, ni liens ni points de
  montage, à l'utilisateur.
  - Le numéro d'appareil ne suffit pas : un montage lié sur le même système de fichiers
    garde le même. La table des montages complète ce contrôle, et **tout montage dans le
    dossier privé est un constat** (`private-mount`). Le dossier privé lui-même peut être
    un point de montage : c'est noté.
- **Remplacement** : l'appareil et l'inode du dossier privé, de ses composants et du
  dossier d'exécution sont relevés avant le repère. Ils sont comparés avant l'extraction,
  puis à la fin. Un écart est le constat `folder-replaced`.
- **Limite de concurrence** : ces contrôles constatent, ils n'empêchent pas. Un processus
  du même utilisateur pourrait remplacer un dossier entre deux relevés. Dans le bac à sable,
  en revanche, rien n'est inscriptible hors des destinations (§3).

## 5. CP-3 : relevé du magasin Nix

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
- **Constats** : une recherche qui sort avec un code non nul, ce qui arrête tout avant
  `preflight` ; une correspondance nouvelle après l'étape.
- Une correspondance disparue n'est qu'une note.
- Ces recherches **ne sont pas exhaustives** : extension, taille, profondeur.

## 6. *Core dumps* (B1-R03, D-018 option B)

### 6.1 Ce qui est vérifié dans le code

- [V] **Noyau** (`fs/coredump.c`, v6.12 et v6.18) :
  - avec un fichier comme destination, aucun *core* n'est écrit quand la limite est sous
    la taille minimale, donc à `0` ou à `1` ;
  - avec un programme (`|`), la limite est ignorée, et le programme reçoit le plantage,
    **sauf** si la limite vaut exactement `1` : le *core dump* est alors abandonné avant de
    lancer le programme (« RLIMIT_CORE is set to 1, aborting core ») ;
  - avec une socket (`@`, depuis 6.16), la limite n'est pas consultée.
- [V] **systemd-coredump 260.5** (nixpkgs, `src/coredump/coredump-submit.c`) : avec une
  limite sous la taille d'une page, il ne lit ni ne stocke le contenu, mais il journalise
  les métadonnées. Avec la limite `1`, il n'est pas lancé du tout.
- [V] **Sur la machine du porteur** (D-017) : les plantages vont par tube à
  systemd-coredump.

### 6.2 La décision : option B (D-018)

- **Seul le mode tube est accepté.** Un mode socket ou fichier est refusé
  (`core-mode-refused`), même si le mode fichier ne garde rien sous la limite.
- **La limite `1`, souple et stricte, vaut pour le seul processus confiné** :
  l'extraction et la sonde de confinement. L'outil garde une limite souple de `0`, et
  `private_guard` contrôle toujours `0` pour lui et pour ses contrôles : il n'est pas
  modifié, et aucun de ses contrôles n'est affaibli. Seule la limite stricte de l'outil
  passe à `1`, pour qu'il puisse donner `1` au bac à sable. Dans les modes fichier et tube,
  `1` ne garde pas plus de *core* que `0`.
- **`run` reste bloqué sans preuve locale** (`core-proof-missing`).

### 6.3 La preuve locale, faite par `rehearse`

Avec des programmes synthétiques seulement, dans le bac à sable de l'extraction, depuis `/`
et avec un environnement vide, pour que le journal ne nomme aucun chemin privé :
1. **plantage témoin**, à la limite `0` : `coredumpctl --json=short list` doit le lister.
   Cela montre que le programme du tube et `coredumpctl` fonctionnent ;
2. **plantage à la limite `1`**, une seconde plus tard : **aucune** entrée ne doit
   apparaître, après au moins 5 s et trois fois le délai du témoin.

La preuve n'est acquise que si :
- les deux programmes meurent par `SIGSEGV` ;
- le témoin a son entrée, et l'essai à la limite `1` n'en a pas ;
- la répétition n'a aucun autre constat que les verrous d'extraction (`core-proof-missing`
  au début, rapport J0).

Elle est enregistrée dans `state.json` de la répétition. Elle vaut pour **ce démarrage**
(`boot_id`), **ce noyau** (version et compilation), **ce `core_pattern`** (son SHA-256) et
**ce `suid_dumpable`**. `run` la cherche, puis la revérifie juste avant l'extraction
(`core-changed`). Un redémarrage, un autre noyau ou un autre réglage demandent une nouvelle
répétition.

**Ce qui reste** :
- le plantage témoin laisse une entrée dans le journal du système, avec les métadonnées
  d'un programme synthétique : sa ligne de commande dans `/nix/store`, `/` comme dossier
  de travail, un environnement vide ;
- après l'étape, toute entrée de `coredumpctl` depuis le début reste un constat, sauf les
  deux plantages de la preuve.
- **Aucune modification du système.**

## 7. Le rapport J0 local (B1-R06, D-018)

**Décision du porteur (D-018) : pas de B1 sans rapport J0 local.** Un rapport valide et
concordant est obligatoire. Son absence, une erreur ou un écart bloquent l'extraction.

- **Où** : `$WC2010_PRIVATE_DIR/logs/j0-identification.json`, là où
  `docs/J0_ISO_IDENTIFICATION.md` l'écrit, ou `--j0-report`, dans le dossier privé.
- **Contrôles**, tous avant le lancement de `rexglue` :
  - un vrai fichier JSON, au plus 16 Mio ;
  - un rapport d'image (`source.kind`), avec son SHA-256 et sa taille ;
  - 49 fichiers, 8 dossiers et les SHA-256 des deux modules, comme le rapport J0 public ;
  - la même taille que l'image ;
  - **puis l'empreinte de l'image, calculée avant le repère, égale à celle du rapport**.
- **Constats bloquants** : `j0-report-absent`, `j0-report-invalid`, `j0-report-mismatch`,
  `j0-image-mismatch`.
- Après l'étape, l'empreinte de l'image est encore comparée au rapport.

## 8. Chiffres de PB-1

Les références sont celles du rapport J0 (`docs/reports/J0_IDENTIFICATION.md` §2). Elles
sont écrites dans l'outil, et un test vérifie qu'elles sont celles du rapport :
- 49 fichiers et 8 dossiers ;
- les SHA-256 de `default.xex` et `fifadllzf.xex`.

**Comptage de `game/`** (arbitrage de la revue : accepté) :
- **la racine n'est pas comptée**, comme dans l'outil J0. ReXGlue, lui, la compte : l'outil
  vérifie que `Nodes = fichiers + dossiers + 1` ;
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
- deux noms pour un même module.

**Empreintes** : le résumé ne donne que `match` ou `DIFFERS` pour les modules et pour
l'image. Les valeurs, attendues ou inattendues, restent dans `report.json`.

**L'outil ne déclare jamais PB-1.** L'orchestrateur décide, sur le résumé.

## 9. Le résumé partageable (B1-R04)

`summary.txt` et la console ne reprennent **que des champs d'une liste fixe** :
- les noms des étapes, leurs statuts et leurs codes de sortie ;
- par étape, les faits de `SUMMARY_FACTS`, chacun contrôlé : entier, booléen, valeur d'une
  liste, date ou commit. Un fait invalide s'affiche `invalid`, sans sa valeur ;
- **les codes des constats**, d'une liste fixe (`FINDING_CODES`), et leur nombre. Le détail
  d'un constat, qui peut nommer un chemin, reste dans `report.json` ;
- les lignes de PB-1 : des nombres pour les comptes, `match` ou `DIFFERS` pour le reste.

N'y figurent jamais : un chemin, un nom de fichier du jeu, le texte d'une commande, d'un
argument ou d'une exception, une empreinte de l'image ni une empreinte inattendue. Le test
`test_summary_holds_no_free_text` place des chaînes sentinelles dans chaque chemin, dans un
constat de `private_guard`, dans le bloc de `rexglue` et dans une cible de montage. Aucune
n'atteint le résumé ni la console.

Même ainsi, **CP-5 s'applique** avant tout partage (`docs/J2_PHASE_B_CONTROLS.md` §4).

## 10. Interruptions, état et reprise (B1-R05)

- **Signaux** : `SIGINT`, `SIGTERM` et `SIGHUP`.
  - Avant le repère, le premier arrête l'étape.
  - Pendant l'extraction, il l'arrête : `SIGTERM` au processus du bac à sable, puis, après
    30 s, `SIGKILL` à bubblewrap, dont le bac à sable meurt avec lui.
  - Ensuite, les contrôles finissent : les signaux suivants ne sont que comptés.
  - Les commandes lancées ont leur propre session : un `Ctrl-C` du terminal ne les arrête
    pas.
- **`SIGKILL` de l'outil**, ou une coupure : aucun `finally` ne peut s'exécuter.
  - Le bac à sable meurt avec l'outil (`--die-with-parent`).
  - `state.json` garde la phase atteinte : `started`, `marker`, `extracting`,
    `extracted`, `postflight`, `complete`. Il est remplacé atomiquement à chaque phase.
  - Toute commande voit alors un passage inachevé (`incomplete-run`), et `run` refuse.
- **Reprise** :

  ```bash
  "$B" --repo "$PWD" resume --run-folder b1-run-<date>
  ```

  - Elle refuse tant que le bac à sable de l'extraction vit encore (`still-running`).
  - Elle refait `postflight`, les montages, les *core dumps*, CP-3, l'identité des
    dossiers, l'empreinte de l'image et les chiffres de PB-1.
  - Elle écrit `report-resume.json` et `summary-resume.txt`.
  - Elle ne relance jamais l'extraction et ne supprime rien.
  - Elle signale que les événements de montage de la période n'ont pas pu être suivis.

## 11. Procédure pour le porteur du projet

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

   Il se termine par `core-proof-missing` tant qu'aucune répétition de ce démarrage n'a
   apporté la preuve.
4. **Répétition** : confinement, surveillance et preuve de l'option B, sans extraction :

   ```bash
   "$B" --repo "$PWD" rehearse
   ```

   Le résumé doit montrer `proof_acquired True`.
5. **B1**, dans le même démarrage, seulement après une répétition sans autre constat que
   `core-proof-missing`, et une fois cette procédure revue et fusionnée :

   ```bash
   "$B" --repo "$PWD" run
   ```

6. **Partage** : seulement `summary.txt`, après CP-5. **Ne jamais partager** `report.json`
   ni les autres fichiers du dossier d'exécution.

**Variable requise** : `WC2010_PRIVATE_DIR`. Le rapport J0 local doit être à sa place
(§7). CP-6 et CP-7 restent à faire comme au `docs/J2_PHASE_B_CONTROLS.md` §1 et §5.

## 12. Essais sans données du jeu, et ce qu'ils ne couvrent pas

**Tests unitaires** (`tools/test_b1_extract.py`, 59 tests), lancés par le contrôle Nix
`b1-extract-selftest` sous l'utilisateur sans privilèges du bac à sable, **sans aucun saut**.
- **Simulés** : `rexglue`, `findmnt`, `coredumpctl`, `nix` et, pour l'orchestration,
  `bwrap`. Le faux `bwrap` vérifie les options du bac à sable et répond à la sonde et au
  plantage.
- **Réels** : `private_guard`, `find`, `git` et, pour le confinement, **bubblewrap**.

| Constat de la revue | Tests |
|---|---|
| R01 | Remplacement au même chemin, remontage, liaison, parent changé, montage apparu ou disparu ; `findmnt` en échec ou illisible ; événements de `mountinfo` |
| R02 | Vrai bac à sable : sonde complète, écritures hors périmètre refusées par `EROFS` ; faux bac à sable : bubblewrap absent, trop ancien, qui ne démarre pas, contrôle en échec ; jamais d'extraction ni de lecture de l'image |
| R03, D-018 | Réglages illisibles ; socket et fichier refusés ; pas de preuve, preuve d'un autre démarrage, noyau, réglage ou `suid_dumpable`, ou d'une répétition avec constats : `run` refuse et `rexglue` ne démarre pas ; preuve acquise puis acceptée par `run` ; témoin sans entrée, limite `1` ignorée, `coredumpctl` en échec : pas de preuve ; *core dump* consigné ; limite `(1, 1)` reçue par l'extraction |
| R04 | Sentinelles dans les chemins, un constat de la garde, le bloc de `rexglue` et les montages ; validateurs ; codes inconnus |
| R05 | Repère absent après un `OK` ; repère présent avec un constat ; `SIGTERM` puis deux signaux pendant les contrôles ; `SIGKILL` de l'outil, état inachevé, refus, `still-running`, reprise sans relance ni suppression |
| R06, D-018 | Rapport absent, illisible, d'un dossier, d'autres comptes ; empreinte de l'image différente : `rexglue` jamais lancé |
| R07 | Liens à la place de `game`, `logs`, `xdg/config` et `app` ; parent modifiable par d'autres ; montage dans le dossier privé ; autre appareil |

**Contrôle Nix `b1-extract-selftest`** : la commande empaquetée, avec le **vrai** bubblewrap
et le **vrai** `rexglue vfs dump`, sur une image XDVDFS synthétique et un rapport J0
synthétique.
- La preuve de l'option B y est écrite par les fonctions de l'outil, sur un réglage
  synthétique en mode tube : seul `rehearse`, chez le porteur, fait la vraie.
- **Quand le bac à sable peut démarrer** : sonde à 23 sur 23 ; `Nodes` 9 pour 5 fichiers
  et 3 dossiers ; écritures seulement dans `game/` et le dossier d'exécution ; second
  passage refusé ; échec de `rexglue` sur un fichier qui n'est pas un conteneur, avec
  `postflight`.
- **Sinon** : `run` refuse, sans rien extraire.
- `sandbox-mode.txt` dit quel cas a tourné.

**Non couvert, faute de root ou de la machine du porteur** :
- **un vrai point de montage** ou un autre système de fichiers : il faut root. Les tables
  et les numéros d'appareil sont simulés ;
- **la preuve de l'option B avec un vrai systemd-coredump** : dans les tests, le programme
  du tube est simulé par le faux `bwrap`, qui ne « reçoit » le plantage qu'à la limite `0`.
  Un vrai plantage synthétique dans le vrai bac à sable a été essayé dans ce conteneur, où
  les *core dumps* vont dans un fichier : `SIGSEGV` aux limites `0` et `1`, aucun fichier
  *core*. Seul `rehearse` fait la preuve avec le vrai programme du tube, chez le porteur ;
- **`nix store verify` et `coredumpctl` réels** : le bac à sable de construction n'a ni
  démon Nix ni journal ;
- **les 31 montages et `/run`** de la machine du porteur : seul `rehearse` les essaie ;
- **le comportement de `rexglue` sur l'image réelle**.

## 13. Ce qui revient dans le dépôt après B1

Seul le contenu de `summary.txt`, après la décision de l'orchestrateur sur PB-1, sous
`docs/reports/` :
- les nombres ;
- les statuts, les codes de sortie et les codes des constats ;
- `match` ou `DIFFERS` pour les empreintes, sauf autorisation explicite et vérifiée de
  publier une valeur (D-007, CP-5).

Ne reviennent jamais dans le dépôt :
- l'arborescence ;
- les noms des fichiers du jeu ;
- les journaux ;
- les sorties de `rexglue`.

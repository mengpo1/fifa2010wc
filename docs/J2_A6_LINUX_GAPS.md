# J2, étape A6 — Lacunes Linux de la chaîne J2

> Étape A6 de `docs/J2_PLAN.md` (§3.6) et ticket #21, sous l'autorisation PA-0 (D-015).
> **Phase A : aucune donnée du jeu.** Les essais n'utilisent qu'une image de disque
> synthétique, faite de deux fichiers texte.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Conclusion

- **A6 ne change rien au runtime.** Aucune couche `platform/linux` n'est écrite : aucun
  manque ne justifie du code [V, §3].
- ReXGlue v0.11.0 fournit déjà les chemins réglables, les journaux, le rapport de plantage
  et l'arrêt sur signal (`docs/J2_A1_SDK_INVENTORY.md` §2). Ce qu'il ne fait pas se règle
  par l'environnement du processus : refus du root, masque `077`, *core dumps* désactivés,
  dossiers XDG et `REX_APP_ROOT` dans le dossier privé.
- Ces réglages sont **déjà contrôlés** :
  - la procédure de phase B les pose (`docs/J2_PHASE_B_CONTROLS.md` §2) ;
  - `private_guard preflight` refuse l'étape s'il en manque un ;
  - `private_guard postflight` signale ce qui serait écrit hors du dossier privé (A4).
- **Nouveau** : un contrôle Nix, `linux-confinement`, rejoue la procédure de bout en bout
  avec le vrai `rexglue`, sur l'image synthétique (§4). Il montre que les réglages
  confinent ce que la commande écrit, et que leur absence est vue avant puis après
  l'étape.
- **Deux points restent** sans correctif (§5) :
  - l'objet de mémoire de l'invité ne peut pas quitter `/dev/shm` ;
  - le noyau ignore `ulimit -c 0` pour un *core dump* transmis par tube, par exemple à
    `systemd-coredump` : le comportement du système est à vérifier une fois sur la
    machine de l'utilisateur.

## 2. Méthode

- Source : ReXGlue v0.11.0 à la révision `a3e1d82`. Les références `fichier:ligne`
  désignent cette source, avant correctif.
- Recherches sur `src/` et `include/` de ReXGlue :
  - `RLIMIT_CORE`, `PR_SET_DUMPABLE`, `MADV_DONTDUMP`, `prctl` : aucun résultat ;
  - `geteuid` : aucun résultat. `getuid` n'est lu que pour trouver le dossier personnel
    (`src/base/platform/file_posix.cpp:69`) ;
  - `temp_directory_path`, `TMPDIR`, `mkstemp`, `mkdtemp` : aucun résultat.
- Les essais tournent dans le bac à sable de Nix, sous l'utilisateur de construction, qui
  n'est pas root.

## 3. Matrice

| Point | Ce que fait ReXGlue | Statut | Mesure | Vérification |
|---|---|---|---|---|
| Lancement sans root | Rien ne refuse le root. En root, sur un magasin inscriptible, le dossier de l'application est celui de l'exécutable, donc le magasin (`src/base/platform/file.cpp:43-49`, `file_posix.cpp:107-139`) | **Configuration suffisante** | Jamais en root ; `preflight` le refuse | `test_root_is_refused` (A4) ; incident de l'essai 3 d'A1 |
| Masque `077` | L'objet de `/dev/shm` est créé en `0777` moins le masque (`src/base/memory_posix.cpp:375`) ; les fichiers suivent le masque | **Configuration suffisante** | `umask 077` ; `preflight` le refuse sinon | `linux-confinement`, cas 1 : arbre extrait et journal en mode `600` ; cas 3 : masque `022` refusé |
| *Core dumps* | Ni `RLIMIT_CORE`, ni `PR_SET_DUMPABLE`, ni `MADV_DONTDUMP` (§2) | **Configuration suffisante**, avec une réserve (§5.2) | `ulimit -c 0` ; `preflight` le refuse sinon | `test_umask_and_core_dumps_are_checked` (A4) ; §5.2 à vérifier sur la machine |
| `TMPDIR` | Jamais lu par ReXGlue (§2). Les écritures atomiques passent par `<fichier>.tmp`, dans le dossier visé (`src/base/platform/file.cpp:98-127`) | **Fourni**, sans objet pour ReXGlue | Pointé dans le dossier privé, pour les outils et les bibliothèques tierces | `preflight` le refuse hors du dossier privé (cas 2) |
| `XDG_CONFIG_HOME` | Dossier de l'application de repli quand celui de l'exécutable n'est pas inscriptible (`file_posix.cpp:107-122`) | **Fourni** | Pointé dans le dossier privé | Cas 2 : sans lui et sans `REX_APP_ROOT`, le journal va dans `$HOME/.config/rexglue/logs/` |
| `XDG_DATA_HOME`, `XDG_CACHE_HOME` | Le premier n'a aucun appelant ; le second n'est pas lu (`docs/J2_A1_SDK_INVENTORY.md` §2) | **Sans objet pour ReXGlue** | Pointés dans le dossier privé, pour les bibliothèques tierces (caches de shaders, J3) | `preflight` (cas 2) |
| `REX_APP_ROOT`, `REX_APP_LOG_ROOT`, `REX_APP_USER_ROOT`, `REX_APP_CACHE_ROOT` | Réglages de chemins (`include/rex/app/app.h:75-81`, `include/rex/path_settings.h:25-30`) | **Fourni** | `REX_APP_ROOT` dans le dossier privé | Cas 1 : le journal va sous `REX_APP_ROOT` |
| Journaux | Fichier créé par défaut sous `app.log_root`, tous gardés (`include/rex/logging/logger.h:218-232`, `src/base/log_file.cpp:80-93`) ; `REX_LOG_FILE=false` le supprime | **Fourni** | Sous `REX_APP_ROOT`, relus avant tout partage (CP-5) | Cas 1 et 2 |
| Répertoire de travail | Les chemins viennent des arguments et du manifeste, résolus depuis son dossier (`docs/J2_A5_CONFIG_TEMPLATE.md` §2) | **Configuration suffisante** | `cd` dans le dossier privé ; `preflight` le vérifie | `test_working_folder_outside_is_refused` (A4) |
| Fichiers de réglages lus avant l'environnement | `{app.root}/rexglue.toml` (`src/app/app.cpp:396-403`) | **Configuration suffisante** | `preflight` cherche un `rexglue.toml` parasite | `test_stray_settings_file_is_reported`, `test_settings_file_next_to_the_executable_is_reported` (A4) |
| `/dev/shm` | Objet `xenia_memory_<pid>_<aléa>`, avec l'image décodée, supprimé à l'arrêt ; un objet laissé par un plantage est supprimé au lancement suivant (`memory_posix.cpp:375,393-423`) | **Manque prouvé**, sans correctif nécessaire (§5.1) | Masque `077` : objet en `0700`. `preflight` et `postflight` signalent un objet restant | `test_left_guest_memory_object_is_reported` et `test_left_guest_memory_object_is_found` (A4) ; `vfs dump` n'en crée pas (A1 §3.3) |
| Rapport de plantage | `write(2)` sur la sortie d'erreur et dans le journal, sans fichier de vidage (`src/base/crash_posix.cpp`) | **Fourni** | Le journal est dans le dossier privé | A1 §2 |

## 4. Contrôle `linux-confinement`

Il est défini dans `nix/checks.nix`, et ses traces sont dans sa sortie.

**Préparation** :
- un dossier privé synthétique, en `0700`, avec ses sous-dossiers ;
- un dossier personnel distinct, hors du dossier privé ;
- une image XDVDFS synthétique, faite par les fonctions de test de J0
  (`tools/test_iso_identify.py`, `write_image`) : deux fichiers texte. Elle est placée en
  lecture seule dans `iso/`.

**Cas 1, selon la procédure** (`1-procedure.txt`) :
- environnement du §2 de `docs/J2_PHASE_B_CONTROLS.md` : `umask 077`, `ulimit -c 0`,
  `TMPDIR`, XDG et `REX_APP_ROOT` dans le dossier privé, travail dans le dossier privé ;
- `preflight --dest game --game-root game`, puis `rexglue vfs dump iso/synthetic.iso game`,
  puis `postflight --watch <dossier personnel> --watch <dossier extérieur>` ;
- résultats [V] :
  - `preflight` et `postflight` répondent `OK` ;
  - l'arbre est extrait dans `game/`, avec le contenu attendu ;
  - le journal est sous `REX_APP_ROOT` ;
  - fichiers extraits et journal en mode `600` ;
  - le dossier personnel reste vide.

**Cas 2, sans les réglages de la procédure** (`2-without-settings.txt`) :
- seul `HOME` est posé, comme dans un shell ordinaire, et `TMPDIR` vise un dossier
  extérieur ;
- `preflight` refuse, avec cinq constats : `TMPDIR` hors du dossier privé ;
  `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` et `REX_APP_ROOT` non posés ;
- l'étape est **quand même** lancée, comme le ferait quelqu'un qui passerait outre ;
- ReXGlue écrit alors son journal dans `$HOME/.config/rexglue/logs/rexglue_001.log`. **C'est
  la preuve du besoin de ces réglages** [V] ;
- `postflight` le signale : « file written outside the private folder », code de sortie 1.

**Cas 3** (`3-umask.txt`) : avec `umask 022`, `preflight` refuse.

Ce contrôle ne prouve pas l'absence de toute écriture ailleurs : il couvre les dossiers
surveillés (`docs/J2_PREREQUISITES.md` §6.1). Il ne lance pas `rexglue codegen` sur un XEX,
faute de données du jeu. La lecture du manifeste par `codegen`, qui s'arrête avant de lire
le jeu, est couverte par A5 (`private-project-selftest`, PR #20).

## 5. Points sans correctif

### 5.1 La mémoire de l'invité dans `/dev/shm` [V]

- `shm_open` place toujours l'objet dans `/dev/shm`. Aucun réglage ne le déplace dans le
  dossier privé.
- **Mesures en place** :
  - le masque `077` met l'objet en `0700`, illisible des autres utilisateurs ;
  - il est supprimé à l'arrêt. Après un plantage, le lancement suivant le supprime
    (`memory_posix.cpp:393-423`) ;
  - `preflight` et `postflight` signalent tout objet `xenia_memory_*` restant.
- **Non couvert** :
  - root peut le lire ;
  - `/dev/shm` peut être placé en mémoire d'échange par le système [I, A1 §9].
- Un espace de noms de montage privé (un `/dev/shm` propre au processus) le confinerait
  davantage. Ce n'est pas nécessaire au confinement des chemins, et ce n'est pas écrit.
  C'est à décider si le besoin apparaît.

### 5.2 *Core dumps* transmis par tube

- [V] Avec `ulimit -c 0`, le noyau n'écrit pas de fichier *core*. Mais il ignore la limite
  quand `kernel.core_pattern` est un tube vers un programme. Le texte de `core(5)`
  (man-pages 6.19) : « The RLIMIT_CORE limit is not enforced for core dumps that are piped
  to a program via this mechanism. »
- [H] C'est le cas avec `systemd-coredump`, réglage courant sous NixOS. Le réglage de la
  machine de l'utilisateur est inconnu [I].
- [V] `systemd-coredump(8)` dit seulement : « the core dump will only be processed when the
  related process resource limits (RLIMIT_CORE) are sufficient ». [H] Une limite nulle
  suffirait donc à ce qu'il ne garde rien, sans que la page le dise explicitement.
- [V] Il note dans le journal du système un résumé de l'événement, avec des champs
  enregistrés « (if known) ». En font partie le numéro de processus, le signal, la limite
  (`COREDUMP_RLIMIT`), la ligne de commande (`COREDUMP_CMDLINE`), le dossier de travail
  (`COREDUMP_CWD`) et la carte mémoire du processus (`COREDUMP_PROC_MAPS`).
  - Ce sont des chemins et des métadonnées du dossier privé, pas le contenu de la mémoire.
  - Ces métadonnées sortent cependant du dossier privé.
- Désactivation au niveau du système, citée par la même page : `Storage=none
  ProcessSizeMax=0` dans `coredump.conf(5)`.
- **Vérification proposée, une fois, sur la machine de l'utilisateur, avant PB-0**, sans
  aucune donnée du jeu :

```bash
sysctl kernel.core_pattern fs.suid_dumpable
```

```bash
bash -c 'ulimit -c 0; kill -SEGV $$'; coredumpctl list --since=-2min
```

  Le second essai fait planter un shell, sans rien du jeu. Il doit montrer que rien n'est
  stocké (colonne `COREFILE` à `none`). À défaut, la désactivation ci-dessus sera à décider
  par le porteur du projet, car c'est un réglage de son système.

Sources lues le 2026-11-23 : <https://man7.org/linux/man-pages/man5/core.5.html> et
<https://man7.org/linux/man-pages/man8/systemd-coredump.8.html>.

## 6. Effets sur CP-1 à CP-7

| Contrôle | Effet |
|---|---|
| CP-1 | Aucun |
| CP-2 | Aucun : rien ne vient du jeu dans Nix ; l'image de l'essai est synthétique et faite dans le bac à sable |
| CP-3 | Aucun |
| CP-4 | Confirmé par l'essai de bout en bout (§4). Ajout proposé : la vérification du §5.2, une fois, avant PB-0 |
| CP-5 | Aucun : le journal reste à relire avant tout partage |
| CP-6 | Aucun |
| CP-7 | Aucun |

## 7. Limites

- Les bibliothèques tierces (SDL3, chargeur Vulkan, pilotes GPU, FFmpeg) ne sont pas
  auditées. La génération de code et `vfs dump` n'utilisent pas de pilote graphique (A1
  §3.1). Les caches de shaders relèvent de J3 [I].
- L'essai tourne dans le bac à sable de Nix, pas sur la machine de l'utilisateur. La
  procédure y sera rejouée en phase B, avec `postflight --sdk` et la recherche du magasin
  de CP-3.

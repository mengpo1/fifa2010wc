# Contrôles avant et après chaque étape de la phase B (CP-1 à CP-7)

> Étape A4 de `docs/J2_PLAN.md`, sous l'autorisation PA-0 (D-015). Cette procédure se
> déroule **sur la machine de l'utilisateur**. Elle ne lit le contenu d'aucun fichier du
> jeu : seulement des chemins, des droits, des dates et des réglages de processus.
> **Elle ne vaut pas PB-0** (`docs/J2_PLAN.md` §2).
> Les contrôles sont définis dans `docs/J2_PREREQUISITES.md` §6. Les destinations
> d'écriture de ReXGlue sont dans `docs/J2_A1_SDK_INVENTORY.md` §6.

L'outil est `tools/private_guard.py`, empaqueté par le flake. Il a trois commandes :

| Commande | Contrôle | Ce qu'elle vérifie |
|---|---|---|
| `check-dir` | CP-1 | Le dossier privé est absolu. Il n'est ni dans `/nix/store`, ni dans le dépôt, ni dans un dépôt git. Il appartient à l'utilisateur, en mode `0700` ou plus strict. Ses sous-dossiers existent, et les fichiers de `iso/` sont en lecture seule |
| `preflight` | CP-1, puis CP-4 avant | Destinations **obligatoires** (`--dest`, ou `--no-writes` pour une étape qui n'écrit rien), dossier de travail, `TMPDIR`, dossiers XDG et `REX_APP_ROOT` dans le dossier privé. Pas de root, masque `077`, *core dumps* désactivés. Aucun réglage de ReXGlue lu avant l'environnement, aucun `.xexp` imprévu, aucun objet `xenia_memory_*` restant |
| `postflight` | CP-4 après | Fichiers créés, modifiés ou déplacés depuis le repère, hors du dossier privé, dans les emplacements surveillés. Objets `xenia_memory_*` restants. `nix store verify` du SDK et `git status` du dépôt, si on le demande |

**Un contrôle qui ne peut pas s'exécuter en entier est un constat, jamais un `OK`** :
- `/dev/shm` illisible ;
- un emplacement surveillé absent, sauf s'il est déclaré par `--optional-watch` ;
- un dossier ou un fichier illisible sous un emplacement surveillé.

L'outil ne lit pas le contenu de ces emplacements : il ne regarde que leurs noms et leurs
dates.

Codes de sortie :
- `0` : rien trouvé ;
- `1` : au moins un constat ;
- `2` : erreur d'utilisation.

L'outil ne supprime et ne déplace rien. Il écrit seulement le fichier repère, dans le
dossier privé.

## 1. Une fois : préparer le dossier privé (CP-1, CP-6)

Depuis la copie du dépôt, hors du dossier privé :

```bash
export WC2010_PRIVATE_DIR="$HOME/.local/share/wc2010-port/private"
```

```bash
mkdir -p "$WC2010_PRIVATE_DIR"/{iso,game,xex,generated,cache,saves,logs}
```

```bash
chmod 700 "$WC2010_PRIVATE_DIR"
```

Rendre l'image en lecture seule, une fois qu'elle est dans `iso/` :

```bash
chmod a-w "$WC2010_PRIVATE_DIR"/iso/*
```

Construire l'outil **avant** toute étape. Cela évite que Nix écrive dans les caches
pendant l'étape surveillée :

```bash
G="$(nix build --no-link --print-out-paths .#private-guard)/bin/fifa2010wc-private-guard"
```

Retenir aussi le chemin du dépôt et celui du SDK :

```bash
REPO="$PWD"; SDK="$(nix build --no-link --print-out-paths .#rexglue-sdk)"
```

Contrôler le dossier privé (CP-1) :

```bash
"$G" --repo "$REPO" check-dir
```

Contrôler le dépôt (CP-6) : le crochet doit valoir `.githooks`, et le contrôle du dépôt
doit passer.

```bash
git config --get core.hooksPath
```

```bash
python3 -I tools/check_proprietary_data.py repo
```

## 2. Avant chaque étape (CP-3, CP-4)

**CP-3.** Faire les recherches du magasin de `docs/J0_ISO_IDENTIFICATION.md` §6, et noter
leurs résultats :
- le critère : aucune nouvelle correspondance suspecte imputable aux opérations du jeu ;
- les différences sans lien avec le projet sont replacées dans leur contexte ;
- rien n'est supprimé ;
- le fichier `nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude` déjà relevé n'est pas examiné.

**CP-4.** Préparer l'environnement de l'étape, dans un **nouveau shell** ; jamais en root.
Les deux premières lignes règlent le masque et désactivent les *core dumps* :

```bash
umask 077
ulimit -c 0
P="$WC2010_PRIVATE_DIR"
export TMPDIR="$P/tmp" XDG_CONFIG_HOME="$P/xdg/config" XDG_DATA_HOME="$P/xdg/data" XDG_CACHE_HOME="$P/xdg/cache" REX_APP_ROOT="$P/app"
mkdir -p "$TMPDIR" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$REX_APP_ROOT"
cd "$P"
```

Lancer le contrôle préalable. Il écrit le repère s'il ne trouve rien.

**Options qui dépendent de l'étape :**
- **`--dest`, obligatoire** : chaque dossier ou fichier que l'étape écrit. Une étape qui
  n'écrit rien le déclare par `--no-writes` ;
- **`--game-root`, requis** pour la génération de code et pour toute étape qui lit le
  dossier du jeu. Sans lui, la recherche des `.xexp` n'a pas lieu.

L'exemple vaut pour la génération de code :

```bash
"$G" --repo "$REPO" preflight --dest "$P/generated" --game-root "$P/game" --sdk-bin "$SDK/bin" --marker "$P/logs/step.marker"
```

**N'exécuter l'étape que si ce contrôle répond `OK`.** Un `.xexp` voulu se déclare par
`--allow-xexp`. Un fichier de réglages voulu se déclare par `--allow-settings CHEMIN`.

## 3. Après chaque étape (CP-4, CP-3)

Depuis le même shell :

```bash
"$G" --repo "$REPO" postflight --marker "$P/logs/step.marker" --sdk "$SDK" --watch "$HOME" --watch /tmp
```

- **Emplacements surveillés** : sans `--watch`, ce sont le dossier personnel et `/tmp`,
  plus le dépôt avec `--repo`. `/dev/shm` est toujours contrôlé.
  - Chaque emplacement `--watch` doit exister et être lisible en entier.
  - Un emplacement qui peut manquer sans conséquence se déclare par `--optional-watch` ;
    son absence n'est alors qu'une note.
- **Contrôle incomplet** : il faut l'expliquer avant de continuer, par exemple pour un
  dossier illisible. Réduire `--watch` pour l'éviter réduit la couverture. Ce choix est
  consigné.
- **Fichier signalé** : on l'examine localement, sans le partager. S'il peut contenir des
  données du jeu, c'est un **arrêt immédiat** (`docs/J2_PLAN.md` §2). Il n'est supprimé
  qu'après une décision explicite.
- **Faux positifs** : d'autres programmes écrivent aussi dans le dossier personnel,
  comme un navigateur ou un éditeur. Il vaut mieux les fermer pendant l'étape, et
  identifier chaque fichier signalé.
- **CP-3** : refaire les recherches du magasin, puis comparer avec celles d'avant l'étape.

**Limite** : ces contrôles couvrent les destinations déclarées et les emplacements
surveillés. Ils ne prouvent pas qu'aucune sortie n'a été écrite ailleurs.

## 4. Avant de partager quoi que ce soit (CP-5)

1. Copier ce qui doit être partagé dans un dossier à part, par exemple
   `$WC2010_PRIVATE_DIR/logs/share`.
2. Lancer le contrôle sur ce dossier :

   ```bash
   python3 -I tools/check_proprietary_data.py tree "$WC2010_PRIVATE_DIR/logs/share"
   ```

3. Relire chaque fichier.
   - **Jamais** de journal de niveau `debug` ou `trace` : il peut contenir des noms RTTI,
     d'imports ou de sections (`docs/J2_A1_SDK_INVENTORY.md` §4.2).
   - Pas de code généré, de vidage mémoire, de chaîne ni de ressource du jeu, au-delà de
     quelques lignes de contexte.
   - Les nombres, statuts, empreintes et adresses sont autorisés (D-007).
4. Rien ne part en CI.

## 5. Autres contrôles

| N° | Comment |
|---|---|
| CP-2 | Les chemins du jeu ne sont que des arguments d'exécution. `git grep -n WC2010_PRIVATE_DIR -- '*.nix'` ne doit montrer que des commentaires ou des usages à l'exécution, et `nix flake check` passe sur une copie propre, sans le dossier privé |
| CP-6 | Ci-dessus (§1), puis `python3 -I tools/check_proprietary_data.py staged` avant chaque commit, par le crochet |
| CP-7 | Aucun fichier d'adresses du projet A n'entre dans le dépôt avant la validation des adresses (`docs/J2_PREREQUISITES.md` §3.2), et `git status` le confirme |
| CP-4, une fois avant PB-0 | **Core dumps transmis par tube** (`docs/J2_A6_LINUX_GAPS.md` §5.2) : le noyau ignore `ulimit -c 0` quand `kernel.core_pattern` est un tube. Relever `sysctl kernel.core_pattern fs.suid_dumpable`, puis faire planter un shell sans rien du jeu, `bash -c 'ulimit -c 0; kill -SEGV $$'`, et vérifier avec `coredumpctl list --since=-2min` que rien n'est stocké. À défaut, le porteur du projet décide d'un réglage du système (`Storage=none ProcessSizeMax=0` dans `coredump.conf`) |

## 6. Ce qui est consigné

Pour chaque étape, et sans contenu propriétaire :
- la date ;
- le commit du dépôt ;
- la sortie de `check-dir`, de `preflight` et de `postflight` : `OK`, ou la liste des
  constats ;
- les résultats de CP-3 ;
- la décision prise sur chaque constat.

Ces résultats vont dans le rapport de l'étape, sous `docs/reports/`.

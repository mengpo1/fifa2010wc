# J0 — Identification locale de l'image du disque, sous NixOS

> Préparé le 2026-11-22. Ce document et l'outil `tools/iso_identify.py` préparent
> l'identification. **L'identification elle-même se fait sur la machine de l'utilisateur,
> avec sa propre copie du disque.** Aucun résultat d'identification n'est déclaré ici.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Objet et limites

Objectif du jalon J0 (`ROADMAP.md` §2) : savoir quelle version du jeu possède
l'utilisateur avant tout travail de code, et répondre à la question « disque Europe
(En, Es, Nl) du projet A, oui ou non ? » (`audit/ISO_REQUIREMENTS.md` §3, risque R-02).

L'outil `iso-identify` :

- **lit** l'image en place, en lecture seule : format du disque (volume XDVDFS),
  arborescence des fichiers, champs **en clair** des en-têtes XEX ;
- **calcule en mémoire** les SHA-256, SHA-1 et CRC32 de l'image, et les SHA-256 et
  SHA-1 de chaque module `.xex` ;
- **compare** les SHA-256 de `default.xex` et de `fifadllzf.xex` à celles du disque
  Europe du projet A, et l'identifiant du titre à `454108E4` ;
- **écrit** un rapport en Markdown (et en JSON sur demande) qui ne contient que des
  empreintes, des noms et tailles de fichiers et des métadonnées d'en-tête. D-007 autorise
  ce contenu.

Il ne fait pas :

- **aucun déchiffrement**. Il ne lit jamais les données d'image d'un XEX, chiffrées sur
  les disques du commerce [H]. Il ne lit pas non plus ses champs de clé et de signature :
  clé AES chiffrée, clé LAN, identifiant de média de 128 bits, signature RSA, empreintes
  internes ;
- **aucune extraction**. Aucun fichier du disque n'est copié sur le disque dur ; les
  modules sont lus en mémoire pour leurs empreintes ;
- **aucune écriture** hors des rapports demandés ; **aucun accès réseau** ;
- **rien dans `/nix/store`**. L'image est un argument donné à l'exécution, jamais une
  entrée Nix ; l'outil refuse une image ou un rapport situés dans `/nix/store` ;
- aucun MD5. Ses 32 chiffres hexadécimaux ressemblent à une clé de 128 bits pour le
  contrôle de données du dépôt ; SHA-1 et CRC32 suffisent à la comparaison avec Redump.

**D-008 n'est pas tranchée par cette étape.** Le rapport fournit seulement l'information
dont la décision a besoin : le type de chiffrement de chaque module, lu en clair dans son
en-tête *file format info*.

### Pourquoi un outil du projet plutôt que ReXGlue

ReXGlue v0.11.0 ne fournit aucune commande qui fasse ce travail sans déchiffrer ni
extraire [V] :

- `rexglue codegen` et `rexglue init achievements` chargent le module, donc le
  déchiffrent (`XEXImage::Decode`, `src/filesystem/xex.cpp`) ;
- `rexglue vfs dump` extrait **tout** le conteneur vers un dossier (plusieurs Go). Il ne
  déchiffre rien : `gdfx.cpp`, `stfs.cpp`, `svod.cpp` et la commande `vfs` ne contiennent
  aucun code de déchiffrement ;
- aucune commande n'affiche l'en-tête XEX ni la liste des fichiers d'une image.

L'outil ne réimplémente donc que la lecture des formats, sur les définitions de
ReXGlue : `include/rex/kernel/types/xex.h` (en-têtes XEX2), `src/filesystem/xex.cpp`
(table des noms des bibliothèques importées), `src/filesystem/gdfx.cpp` (XDVDFS). Son
lecteur XDVDFS est recoupé avec l'image de test synthétique de ReXGlue (§9).

## 2. Préparer le dossier privé (une seule fois)

Le dossier privé suit `audit/ISO_REQUIREMENTS.md` §6 : hors du dépôt, accessible au seul
utilisateur. Dans chaque nouveau terminal, définir la variable :

```bash
export WC2010_PRIVATE_DIR="$HOME/.local/share/wc2010-port/private"
```

Créer le dossier, ses sous-dossiers `iso/` et `logs/`, en mode 700 :

```bash
install -d -m 700 "$WC2010_PRIVATE_DIR" "$WC2010_PRIVATE_DIR/iso" "$WC2010_PRIVATE_DIR/logs"
```

Y déplacer l'image du disque (remplacer le chemin source par le vôtre) :

```bash
mv /chemin/vers/votre-image.iso "$WC2010_PRIVATE_DIR/iso/"
```

La protéger en écriture :

```bash
chmod a-w "$WC2010_PRIVATE_DIR"/iso/*.iso
```

Règles à respecter (D-007) :

- l'image n'est jamais dans le clone du dépôt, ni dans un dossier synchronisé avec un
  service en ligne ;
- jamais de `git add` d'un fichier du jeu (le hook `.githooks/pre-commit` le bloque) ;
- l'image n'entre jamais dans le magasin Nix. Cela exclut : `nix-store --add`,
  `nix-store --add-fixed`, `nix store add-file`, `nix store add-path`,
  `nix-prefetch-url file://…`, un chemin `./…` ou `builtins.path` dans une expression
  Nix, et toute référence de flake `path:…`. Une telle référence copie le dossier entier
  dans le magasin, fichiers non suivis par git compris. Utiliser `.#…` dans le clone git
  du dépôt : seuls les fichiers suivis par git sont alors copiés.

## 3. Récupérer l'outil

Prérequis : Nix 2.34 ou plus récent, avec `nix-command` et `flakes` (comme pour J1).

Cloner le dépôt, ou réutiliser le clone de J1 :

```bash
git clone https://github.com/mengpo1/fifa2010wc.git
```

```bash
cd fifa2010wc
```

Tant que la PR de J0 n'est pas fusionnée, se placer sur sa branche (après la fusion,
rester sur `main`) :

```bash
git fetch origin claude/j0-iso-identification
```

```bash
git switch claude/j0-iso-identification
```

Construire l'outil. Ce n'est qu'un script Python de la bibliothèque standard et
l'interpréteur Python de nixpkgs 26.05 ; le SDK n'est pas recompilé :

```bash
nix build .#iso-identify
```

## 4. Lancer l'identification

Depuis le clone, remplacer `VOTRE-IMAGE.iso` par le nom du fichier :

```bash
nix run .#iso-identify -- --json "$WC2010_PRIVATE_DIR/logs/j0-identification.json" --markdown "$WC2010_PRIVATE_DIR/logs/j0-identification.md" "$WC2010_PRIVATE_DIR/iso/VOTRE-IMAGE.iso"
```

- Le rapport s'affiche aussi dans le terminal.
- Durée : le calcul des empreintes de l'image lit toute l'image (environ 7 à 8 Go pour
  un disque XGD2 complet [H]), soit quelques minutes selon le disque dur. Une
  progression s'affiche. L'option `--no-image-hash` saute ce calcul ; les empreintes des
  modules XEX sont toujours calculées.
- Code de sortie :
  - `0` : identification complète ;
  - `3` : image lue, mais identification incomplète, sans volume XDVDFS, sans
    `default.xex` ou avec un en-tête illisible (voir « Anomalies ») ;
  - `2` : erreur d'utilisation ou de lecture, chemin refusé, ou rapport refusé par la
    dernière vérification (§5) ; dans ce cas, aucun rapport n'est écrit.

Cas particuliers :

- **Dossier déjà extrait** (par exemple par extract-xiso) : passer le dossier au lieu de
  l'image. Les empreintes des modules sont les mêmes ; seules celles de l'image manquent.
- **Conteneur Games on Demand (STFS)** au lieu d'une image de disque : l'outil le signale.
  L'extraire alors avec ReXGlue, qui ne déchiffre rien pour cette opération, dans le
  dossier privé :

  ```bash
  nix shell .#rexglue-sdk -c rexglue vfs dump "$WC2010_PRIVATE_DIR/iso/VOTRE-CONTENEUR" "$WC2010_PRIVATE_DIR/game"
  ```

  puis lancer l'identification sur `"$WC2010_PRIVATE_DIR/game"`. Cette commande compile
  le SDK si le magasin Nix ne le contient pas encore.

## 5. Relire le rapport avant de le partager

Le rapport contient :

- la taille, les SHA-256, SHA-1 et CRC32 de l'image ;
- le format du disque, le nombre de fichiers et de dossiers, et la racine du disque (noms
  et tailles) ;
- pour chaque module `.xex` : taille, SHA-256, SHA-1, comparaison avec le projet A ;
- les champs en clair de l'en-tête : identifiant du titre et du média, version, numéro de
  disque, chiffrement et compression, régions, médias autorisés, drapeaux, adresse de
  chargement, point d'entrée, nom PE d'origine, date d'édition de liens, bibliothèques
  importées et statiques avec leurs versions, liste des en-têtes optionnels présents ;
- le verdict et les anomalies.

Il ne contient pas le chemin local de l'image : un nom d'utilisateur ou de dossier n'y
apparaît pas.

Protections intégrées : un jeton hexadécimal isolé de 128 bits (taille d'une clé AES) est
masqué dans les valeurs du rapport, et l'outil s'arrête si un tel jeton atteint malgré
tout le texte final. Contrôle supplémentaire avec le script du dépôt, depuis le clone :

```bash
nix shell --inputs-from . nixpkgs#python3 -c python3 -I tools/check_proprietary_data.py tree "$WC2010_PRIVATE_DIR/logs"
```

(`--inputs-from .` prend le Python du nixpkgs épinglé par `flake.lock`.)

Résultat attendu : `OK: 2 files checked, no proprietary data found`. Le nombre est plus
grand si `logs/` contient d'autres fichiers.

## 6. Vérifier que rien n'est entré dans le magasin Nix

`nix run` ne construit que l'outil ; l'image est ouverte à l'exécution par son chemin.
Pour le vérifier, aucune des deux commandes suivantes ne doit afficher de ligne.

Fichiers de plus de 100 Mo à la racine du magasin (une image ajoutée par
`nix-store --add` y serait) :

```bash
find /nix/store -maxdepth 1 -type f -size +100M
```

Modules XEX, et images de plus de 100 Mo, dans les dossiers du magasin (une copie par
une référence `path:` y serait) :

```bash
find /nix/store -maxdepth 3 -type f \( -iname '*.xex' -o \( -iname '*.iso' -size +100M \) \)
```

L'image de test synthétique de ReXGlue (`tests/fixtures/filesystem/gdfx.iso`, 80 Kio)
n'apparaît pas, à cause du seuil de taille. Si une ligne apparaît malgré tout, supprimer
le chemin avec `nix-store --delete` (`nix-store --query --roots` montre ce qui le retient).

## 7. Ce qu'il faut transmettre

- Le fichier `j0-identification.md`, relu (§5), collé dans la conversation ou en
  commentaire de la PR de J0. Le JSON peut l'accompagner.
- Facultatif, mais utile au recoupement : la région et les langues imprimées sur la
  jaquette, et la façon dont l'image a été produite à partir du disque (outil, lecteur).
- **Jamais** : l'image, un module XEX ou un extrait, un fichier du jeu, une capture.

## 8. Interprétation du verdict

| Résultat | Conséquence |
|---|---|
| Identifiant du titre `454108E4` | C'est bien le jeu ; sinon, il s'agit d'une autre édition ou d'un autre titre |
| Disque Europe du projet A : oui | La configuration d'analyse du projet A s'applique telle quelle (R-02 levé) |
| Disque Europe du projet A : non | Analyse à refaire pour J2, avec les outils du projet A (`ISO_REQUIREMENTS.md` §3, étape 6) |
| Modules chiffrés | Confirme ou infirme l'hypothèse [H] de D-008 ; si un module n'est pas chiffré, l'option O2 est à réexaminer |
| Fichiers au-delà de la fin de l'image | Image tronquée ou incomplète : produire une nouvelle image du disque |
| Autres anomalies | À signaler telles quelles, avec le rapport |

La suite (prochaine mission) : consigner le rapport dans `docs/reports/`, puis trancher
D-008. Ce document ne crée pas ce rapport.

## 9. Validation de l'outil (sans le jeu)

Les commandes et résultats suivants ont été exécutés pendant la préparation [V] :

- `python3 -I tools/test_iso_identify.py` : 21 tests, dont 20 sur des images XDVDFS et
  des modules XEX2 synthétiques fabriqués à l'exécution, et un recoupement sur l'image de
  test de ReXGlue (sauté hors de Nix, faute de source ReXGlue).
- Le check `iso-identify-selftest` de `nix flake check` lance ces tests dans le bac à
  sable Nix, recoupement compris. Il échoue si le recoupement n'a pas tourné.
- Le recoupement : sur `tests/fixtures/filesystem/gdfx.iso` de ReXGlue, l'outil trouve
  `a.txt`, `big.bin`, `folder` et `folder/c.txt`, avec les contenus qu'attend le test de
  ReXGlue (`tests/unit/filesystem/providers_test.cpp`).
- Les tests couvrent :
  - les partitions XDVDFS nue, XGD3 et XGD2 ;
  - les en-têtes XEX2 : informations d'exécution, format, sécurité, bibliothèques ;
  - le verdict du projet A ;
  - une image tronquée, une table de dossier en boucle ou hors limites, un en-tête
    optionnel corrompu, un module non XEX2, un conteneur STFS ;
  - un dossier extrait, qui donne le même résultat que l'image ;
  - les refus de `/nix/store` et les codes de sortie.
- Les champs de clé et de signature des modules synthétiques sont remplis d'octets
  marqueurs. Un test vérifie qu'aucun de ces octets n'atteint le rapport, et que le
  rapport passe `check_proprietary_data.py`.
- Test par mutation : une version modifiée de l'outil qui publie 8 octets de la clé AES
  chiffrée fait échouer ce test. Une version qui publie la clé entière, 32 chiffres
  hexadécimaux, voit la clé masquée par la protection du §5.

Non vérifié, et seulement vérifiable par l'utilisateur :

- **[I]** la lecture des en-têtes XEX **réels**. Les dispositions viennent de ReXGlue,
  mais aucun module du commerce n'a été lu. Un champ mal interprété apparaîtrait comme
  une valeur incohérente ou une anomalie, sans arrêt de l'outil ;
- **[I]** le format exact de l'image de l'utilisateur : image complète XGD2 ou XGD3, ou
  image réduite.

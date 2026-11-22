# Audit — Exigences sur l'ISO et outillage d'analyse

> Mission 001, révision « Linux prioritaire » — audit du 2026-11-21.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue (voir
> `EXISTING_PROJECTS.md`).

## 1. Principes non négociables

1. **Aucune ressource propriétaire dans le dépôt.** Cela vaut pour l'ISO, les XEX (même
   partiellement), les images mémoire déchiffrées, le code C++ généré depuis le jeu
   (c'est une traduction du code du jeu), les caches de shaders (dérivés des shaders du
   jeu), les captures d'écran, les sons et vidéos du jeu, les sauvegardes, les DLC et les
   journaux qui recopient de la mémoire du jeu.
2. **Aucune ressource propriétaire dans le magasin Nix.** Tout ce qui entre dans
   `/nix/store` y devient lisible par tous les utilisateurs de la machine et peut être
   poussé vers un cache binaire. L'ISO et ce qui en dérive restent hors du magasin
   (voir `LINUX_FEASIBILITY.md` §5).
3. **Aucune ressource propriétaire en CI ni sur un service tiers.** La CI publique ne
   compile que ce qui ne dépend pas du jeu (SDK, outils, tests unitaires).
4. **Aucun contournement de protection technique engagé par le projet** tant que la
   décision D-008 n'est pas tranchée (§5).
5. **Ce qui peut être versionné** : notre code, la documentation, les empreintes SHA-256
   des fichiers attendus, les métadonnées d'en-tête (identifiant du titre, version), les
   fichiers de configuration d'analyse (adresses de fonctions, pointeurs). Ce sont des
   faits sur le binaire, pas son contenu. Le projet A publie d'ailleurs ce même type de
   données sous BSD 3-Clause [V].

## 2. Ce dont le portage a besoin

| Élément | Origine | Utilisé à | Fait |
|---|---|---|---|
| `default.xex` | Racine du disque | Génération de code **et** chaque lancement | [V] manifestes des projets A et B, documentation ReXGlue |
| `fifadllzf.xex` | Racine du disque | Génération de code et chargement par le jeu (`XexLoadImage`) | [V] |
| Arborescence des données (`data/`, `audiodata/`, `data/movies/`…) | Disque | Exécution, montée en `game:` | [V] pour les noms cités dans les notes du projet B ; liste complète [I] |
| Mise à jour du titre (`.xexp`) | Console de l'utilisateur, jamais sur le disque | Optionnelle | Existence d'une mise à jour pour ce jeu [I] |
| DLC et sauvegardes (STFS) | Console de l'utilisateur | Optionnels, hors premier jalon | [V] pris en charge par le projet B |

**[V]** La documentation ReXGlue (`runtime/lifecycle.md`) indique que
`TitleRuntime::Load` monte `title.game_root` en `game:` puis charge `game:\default.xex`
à chaque lancement. Le XEX est donc lu à l'exécution, pas seulement à la compilation.

**[V]** En ReXGlue v0.11.0, `title.game_root` doit être un dossier. La lecture directe
de l'ISO dépend du correctif 0005 du projet A ; sans lui, il faut extraire l'ISO dans un
dossier local.

## 3. Identification de l'ISO (étape J0, sans aucun déchiffrement)

Objectif : savoir **avant tout travail de code** quelle version du jeu possède
l'utilisateur. Toutes les étapes ci-dessous lisent des données **en clair**.

> Mise en œuvre (préparation de J0, 2026-11-22) : les étapes 1, 2, 4, 5 et 6 sont
> automatisées par `nix run .#iso-identify` (`tools/iso_identify.py`), qui lit les modules
> en mémoire, sans extraction : l'étape 3 n'est plus nécessaire. Procédure :
> `docs/J0_ISO_IDENTIFICATION.md`.

1. **Format du disque.** Chercher la signature `MICROSOFT*XBOX*MEDIA` au secteur 32
   (secteurs de 2 048 octets) de la partition de jeu, aux décalages `0x0` (XDVDFS nu),
   `0x2080000` (XGD3), `0xFD90000` (XGD2) et `0x18300000` (XGD1). C'est la méthode de
   `tools/disc.py` du projet A [V].
2. **Liste des fichiers.** Lister l'arborescence (extract-xiso `-l`, ou `disc.py list`),
   sans rien extraire.
3. **Extraction ciblée** des deux XEX vers un dossier privé (§6). *Inutile avec l'outil de
   J0, qui calcule les empreintes en mémoire.*
4. **Empreintes.** Calculer le SHA-256 de `default.xex` et de `fifadllzf.xex`, puis les
   comparer à celles du disque Europe (En, Es, Nl) publiées par le projet A [V] :

   | Fichier | SHA-256 (disque Europe En/Es/Nl, projet A) |
   |---|---|
   | `default.xex` | `D0DF5465E077EAEBEADDA252C786D9322551AB13EF23AAD461836E510971337D` |
   | `fifadllzf.xex` | `462676F9FBAB83530C2659E79AA43E3DBE81B43DC917DB9299933C19FA34905D` |

5. **En-têtes XEX en clair** (magie `XEX2`, en-têtes optionnels) [V] (format lu par
   `tools/xexinfo.py` du projet A) :
   - *execution info* (`0x00040006` ; correction du 2026-11-22 : l'audit indiquait
     `0x000183FF`, qui est l'en-tête *original PE name*, d'après
     `include/rex/kernel/types/xex.h` de ReXGlue v0.11.0 [V]) : identifiant du titre (attendu : `454108E4`,
     identifiant visible dans l'adresse de la fiche Xbox Marketplace et dans les chemins
     de contenu du projet B [V]), identifiant du média, version, version de base,
     numéro de disque ;
   - *file format info* (`0x000003FF`) : type de chiffrement et de compression. Ce champ
     est lu en clair et indique si le XEX est chiffré **sans le déchiffrer** ;
   - *import libraries* (`0x000103FF`) : bibliothèques système importées, ce qui donne une
     première liste des services Xbox 360 utilisés ;
   - informations de sécurité : régions de jeu autorisées.
6. **Verdict de compatibilité** (consigné localement, puis résumé dans un document
   versionné sans contenu propriétaire) :
   - empreintes identiques à celles du projet A : la configuration d'analyse du projet A
     s'applique telle quelle ;
   - empreintes différentes : la configuration du projet A ne peut pas être supposée
     valable. Elle est à revalider sur le code, sans conclure à partir des seules
     empreintes, qui couvrent aussi l'en-tête et des données chiffrées. Si la
     revalidation échoue, l'analyse est à refaire avec les outils du projet A
     (`autofix_codegen.py`, `find_code_pointers.py`, `find_setjmp.py`), pour un coût
     estimé de quelques jours à quelques semaines [H]. C'est le cas du disque de
     l'utilisateur depuis J0 (`docs/J2_PREREQUISITES.md`).

**[V]** (J0, 2026-11-22) Disque XGD2, région PAL, titre `454108E4`, version `0.0.0.3`.
Les empreintes des deux modules diffèrent de celles du projet A
(`docs/reports/J0_IDENTIFICATION.md`).

## 4. Outils d'analyse

| Outil | Rôle | Licence | Disponibilité NixOS 26.05 | Déchiffre ? |
|---|---|---|---|---|
| `sha256sum` (coreutils) | Empreintes | GPL-3.0 | [V] | Non |
| extract-xiso | Lister et extraire XDVDFS (Xbox, Xbox 360) | Type BSD avec clause de publicité [V] | `extract-xiso` 202505152050 [V] | Non |
| xdvdfs-cli | Lister et extraire XDVDFS | [I] | `xdvdfs-cli` 0.8.3 [V] | Non ; prise en charge des disques 360 [I] |
| `tools/disc.py` (projet A) | Détecter, lister, extraire | BSD 3-Clause [V] | Python 3.13 [V] | **Oui pour PS3** (clé de disque) ; inutile ici |
| `tools/xexinfo.py` (projet A) | En-têtes XEX en clair | BSD 3-Clause [V] | Python [V] | Non |
| `tools/xeximage.py` (projet A) | Image mémoire du XEX | BSD 3-Clause [V] | Python + `cryptography` | **Oui** (clé « retail » en dur) [V] |
| `rexglue` (SDK) | Création de projet, génération de code, lecture du XEX | BSD 3-Clause [V] | À compiler (§1 de `LINUX_FEASIBILITY.md`) | **Oui** (clés maîtresses intégrées, `src/filesystem/xex.cpp`) [V] |
| XenonAnalyse / XenonRecomp | Tables de sauts, génération de code | MIT [V] | Compilé sous Linux pendant l'audit [V] | **Oui** (dépendance tiny-AES-c) [V] |
| capstone | Désassemblage PowerPC | BSD [H] | `capstone` 5.0.7 [V] | Non |
| Ghidra + chargeur XEX | Rétro-ingénierie interactive | Apache-2.0 pour Ghidra [H] ; chargeur [I] | [I] | Le chargeur, probablement [H] |
| Xenia | Oracle de développement (comparaison), **jamais à l'exécution du portage** | BSD [H] | [I] | Oui [H] |

Usage recommandé : l'identification (§3) n'utilise que des outils qui **ne déchiffrent
pas** (`sha256sum`, extract-xiso, `xexinfo.py`). Les outils marqués « Oui » ne servent
qu'après la décision D-008.

## 5. Chiffrement des XEX et protections techniques (point bloquant)

### Faits vérifiés

- **[V]** Les XEX commerciaux peuvent être chiffrés en AES et compressés en LZX. Le
  type figure en clair dans l'en-tête *file format info*.
- **[V]** ReXGlue intègre les clés maîtresses XEX et déchiffre les modules avec ExCrypt
  (`src/filesystem/xex.cpp`, sous-module `thirdparty/excrypt`). Il le fait à la
  génération de code et à chaque chargement par le runtime (§2).
- **[V]** `tools/xeximage.py` du projet A contient la clé « retail » en clair.
- **[V]** XenonRecomp dépend de `tiny-AES-c` pour la même opération.
- **[V]** (J0, 2026-11-22) Les deux XEX du disque de l'utilisateur sont chiffrés (AES)
  et compressés (LZX), d'après leur en-tête *file format info*, lu en clair à l'étape 5
  sans déchiffrement.

### Analyse

Toute recompilation statique a besoin du code machine en clair. Si les XEX sont chiffrés,
produire ce code revient à lever une mesure de chiffrement. La contrainte de la mission
interdit d'« engager un contournement des protections techniques ».

**[I] Juridique, hors de la compétence de cet audit**, à soumettre à un juriste du
pays de l'utilisateur. Le pays lui-même est une inconnue. Textes à examiner, à titre
indicatif :
- Directive 2001/29/CE, art. 6 (mesures techniques) ; Directive 2009/24/CE, art. 5 à 7
  (logiciels : actes autorisés, décompilation pour l'interopérabilité, moyens de
  neutralisation) ;
- en droit français : CPI L.122-6, L.122-6-1 (actes de l'utilisateur légitime,
  décompilation), L.122-6-2, L.331-5 et suivants ;
- CJUE, 23 janvier 2014, *Nintendo c/ PC Box*, C-355/12 : un jeu vidéo est une œuvre
  complexe, et la protection des mesures techniques peut s'appliquer à l'ensemble.

**[H]** Que les clés soient publiques ne change probablement pas, à elle seule, la
qualification de mesure technique.

### Options (décision D-008, à trancher par l'orchestrateur ou l'utilisateur)

| Option | Description | Conséquence pour le projet |
|---|---|---|
| O1 — Attente | Aucun déchiffrement tant qu'un avis juridique n'est pas obtenu | Les jalons J0 (identification) et J1 (chaîne de compilation, sans jeu) restent possibles ; J2 et la suite sont bloqués |
| O2 — Entrée fournie | L'utilisateur fournit lui-même, sous sa responsabilité, des XEX dont l'en-tête indique « non chiffré » ; le projet ne contient ni clé ni code de déchiffrement | Il faut vérifier que ReXGlue accepte un XEX non chiffré [H] ; le runtime recharge le XEX à chaque lancement (§2), il faut donc la même entrée à l'exécution ; la question juridique demeure pour l'utilisateur |
| O3 — Dépendance | Utiliser ReXGlue tel quel ; le déchiffrement est fait par la dépendance, sur la machine de l'utilisateur, pour sa copie | C'est la pratique des projets A et B ; elle est contraire à la lettre de la contrainte de la mission, sauf si l'orchestrateur la requalifie |

Recommandation de l'audit : **O1 jusqu'à décision**. J0 et J1 n'en dépendent pas.

Analyse préalable à la décision (2026-11-22, ticket #8), sans décision :
`docs/D-008_DECISION_NOTE.md`. Elle porte notamment sur la faisabilité d'O2, établie par
lecture du code de ReXGlue seulement : le module non chiffré est accepté, mais une clé de
session est toujours dérivée.

## 6. Organisation locale des fichiers privés

Proposition (à valider, voir D-007) :

```
$WC2010_PRIVATE_DIR            # hors dépôt, par défaut ~/.local/share/wc2010-port/private
├── iso/                       # l'ISO de l'utilisateur, en lecture seule (chmod a-w)
├── game/                      # extraction éventuelle de l'arborescence (game_root)
├── xex/                       # copies des deux XEX pour la génération de code
├── generated/                 # C++ généré (jamais versionné)
├── cache/                     # caches de shaders
├── saves/                     # sauvegardes et profil
└── logs/                      # journaux (à relire avant tout partage)
```

- Les chemins sont lus dans une variable d'environnement ou dans un fichier TOML local,
  jamais en dur dans le dépôt.
- Le `.gitignore` du futur projet doit bloquer au minimum `*.iso`, `*.xex`, `*.xexp`,
  `*.bin`, `*.big`, `generated/`, `out/` et `*.dmp`. Le projet A bloque ces motifs et
  d'autres [V].
- Un journal destiné à un rapport de bogue doit être relu : il ne doit contenir ni
  vidage mémoire, ni chaînes ou ressources du jeu au-delà de quelques lignes de contexte.

## 7. Inconnues à lever

1. **[V]** (levée à J0) Région, version et empreintes de l'ISO de l'utilisateur : PAL,
   `0.0.0.3`, empreintes différentes de celles du projet A
   (`docs/reports/J0_IDENTIFICATION.md`). Reste **[I]** : identité du code machine avec
   celui du projet A (`docs/J2_PREREQUISITES.md` §3).
2. **[V]** (levée à J0) Chiffrement effectif des deux XEX : AES, avec compression LZX.
3. **[I]** Existence d'une mise à jour du titre et pertinence de l'appliquer.
4. **[I]** Statut juridique du déchiffrement dans le pays de l'utilisateur (§5).
5. **[H]** Acceptation par ReXGlue d'un XEX non chiffré, pour l'option O2. La source de
   v0.11.0 l'accepte (`XEXImage::DecodeWith`, lu sans exécution), après une dérivation
   de clé de session faite dans tous les cas (`XEXImage::Decode`). Ce n'est pas
   vérifié par une exécution.

## Sources

- https://github.com/CalinGraphics/fifa-world-cup-2010-recompiled (README, `tools/`)
- https://github.com/RamiChaaben8/Fifa_World_Cup_2010_PC_Port (README)
- https://github.com/rexglue/rexglue-sdk (`docs/site/pages/runtime/lifecycle.md`,
  `docs/site/pages/filesystem/folders-and-storage.md`, `src/filesystem/xex.cpp`)
- https://github.com/hedge-dev/XenonRecomp (`.gitmodules`)
- https://marketplace.xbox.com/en-US/games/media/66acd000-77fe-1000-9115-d802454108e4/
- https://github.com/XboxDev/extract-xiso

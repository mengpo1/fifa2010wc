# Rapport du jalon J0 — Identification de l'image du disque

> Mission « J0 — exploitation des résultats de l'ISO », 2026-11-22. Branche
> `claude/j0-results-analysis`, issue de `main` au commit `b429667` (fusion de la PR #3).
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.
>
> Ce rapport ne s'appuie que sur les métadonnées du rapport J0 de l'utilisateur, telles
> que l'orchestrateur les a transmises.
>
> Mise à jour du 2026-11-22 : C0.1 à C0.4 sont validés par l'utilisateur et
> l'orchestrateur (§5). C0.5, c'est-à-dire D-008, reste ouvert et bloquant. Aucun fichier du jeu n'a été lu, demandé, transmis
> ou déchiffré pour l'écrire. Aucun code n'a été généré. J2 n'est pas commencé.

## 1. Source des résultats

- **Outil** : `tools/iso_identify.py` version 1 (`nix run .#iso-identify`), tel que
  fusionné sur `main` (PR #3, commit `e45dbef`). Il lit l'image en place, sans
  déchiffrement ni extraction (`docs/J0_ISO_IDENTIFICATION.md`).
- **Exécution** : par l'utilisateur, sur sa machine NixOS, avec sa propre image.
- **Transmission** : les métadonnées du rapport original de l'utilisateur, en deux
  envois de l'orchestrateur, sans qu'aucune valeur ait été redemandée :
  - la synthèse de la mission ;
  - les compléments de sa revue de la PR #4 (2026-11-22) : arborescence, bibliothèques
    importées, champs de chargement.

  Ni l'image, ni les modules, ni le rapport local complet ne sont dans le dépôt. Les
  valeurs reprises ci-dessous (empreintes, identifiants, noms, tailles, adresses, champs
  d'en-tête en clair) sont autorisées par D-007.

## 2. Résultats

### 2.1 Image du disque

| Champ | Valeur | Statut |
|---|---|---|
| Format | XGD2 | [V] rapport J0 |
| Arborescence | 49 fichiers, 8 dossiers | [V] rapport J0 |
| Fichiers au-delà de la fin de l'image | 0 | [V] rapport J0 |
| Anomalies | Aucune | [V] rapport J0 |

Ces résultats montrent que l'arborescence XDVDFS est lue entièrement et que l'image n'est
pas tronquée. Ils ne démontrent **pas** l'intégrité du contenu de chaque fichier : aucune
empreinte de référence n'existe pour les fichiers autres que les deux modules [I].

### 2.2 Modules XEX

| Champ | `default.xex` | `fifadllzf.xex` | Statut |
|---|---|---|---|
| SHA-256 | `dce08ce39dd11a6f45c74064d8f6c181326de1999b86bbd4ddcaf0feaa6de287` | `788474d3ee970d1777bbaf2f2ef950e937dd56ac7fc57a5a9e5c0d2874736485` | [V] rapport J0 |
| Empreinte du projet A (disque Europe En, Es, Nl) | Différente | Différente | [V] comparaison à `ISO_REQUIREMENTS.md` §3 |
| Chiffrement (*file format info*) | Normal (AES) | Normal (AES) | [V] en-tête en clair |
| Compression (*file format info*) | Normale (LZX) | Normale (LZX) | [V] en-tête en clair |
| Adresse de chargement | `0x82000000` | `0x82300000` | [V] rapport J0 (informations de sécurité) |
| Taille de l'image chargée | 2 031 616 octets (`0x1F0000`) | 25 493 504 octets (`0x1850000`) | [V] rapport J0 |
| Fin de l'image (chargement + taille) | `0x821F0000` | `0x83B50000` | [V] calcul |
| Bibliothèques importées | `xam.xex`, `xboxkrnl.exe` | `xam.xex`, `xboxkrnl.exe` | [V] rapport J0 |
| Versions des bibliothèques importées (minimale) | 2.0.9328.0 (2.0.8955.0) | 2.0.9328.0 (2.0.8955.0) | [V] rapport J0 |

### 2.3 Champs d'en-tête du titre

| Champ | Valeur | Statut |
|---|---|---|
| Identifiant du titre | `454108E4` (la valeur attendue) | [V] rapport J0 |
| Identifiant du média | `6CCD3565` | [V] rapport J0 |
| Région | PAL, `0x00FF0000` : tous les bits PAL (Europe, Australie et Nouvelle-Zélande), aucun bit NTSC | [V] rapport J0 ; décodage des bits selon `XEXRegionFlags` de ReXGlue |
| Version | `0.0.0.3` | [V] rapport J0, décodée selon la disposition `XEXVersion` de ReXGlue (QFE dans les 8 bits de poids faible) |
| Approbation des bibliothèques statiques | `64` | [V] valeur brute ; analyse au §4 |

Ce que ce rapport ne suppose pas :

- **[I]** La région et les langues exactes du disque (inscription de la jaquette).
- **[I]** La version, l'identifiant de média, la région et la taille de l'image de
  `fifadllzf.xex` du disque du projet A. Le projet A ne publie que les deux SHA-256 de ses
  modules, la mention « Europe (En, Es, Nl) » et trois valeurs de disposition (§3.2).

## 3. Ce que la différence d'empreintes permet de conclure, et ce qu'elle ne permet pas

### 3.1 Empreintes

**Faits [V]** :

- Le disque de l'utilisateur n'est **pas** l'exemplaire dont le projet A a publié les
  empreintes : aucun des deux modules n'est identique, octet pour octet, à celui du
  projet A.
- L'identifiant du titre est celui du jeu (`454108E4`), et la région est PAL. Le disque
  du projet A est lui aussi européen, mais sa région exacte n'est pas publiée [I].
- Les deux modules sont chiffrés (AES) et compressés (LZX), comme l'indique leur en-tête
  en clair.

**Ce qu'on ne peut pas conclure** : que le code machine des deux disques diffère. Le
SHA-256 d'un fichier XEX couvre tout le fichier :

1. L'en-tête contient :
   - les informations d'exécution, dont l'identifiant du média et la version ;
   - les informations de sécurité : régions, types de média, clé de fichier chiffrée,
     empreintes internes, signature.

   Deux disques d'un même code, édités pour des marchés ou des pressages différents, ont
   des en-têtes différents dès qu'un seul de ces champs change.
2. Les données d'image sont chiffrées avec une clé propre au fichier : la clé de fichier
   de l'en-tête. Avec deux clés différentes, des images en clair identiques donnent des
   octets chiffrés entièrement différents.
3. La compression LZX ajoute ses propres blocs et empreintes de blocs.

Une seule de ces différences suffit à changer le SHA-256 du fichier, que le code soit
identique ou non. **[I]** L'identité ou la différence du code machine reste donc à
établir :

- les empreintes des fichiers ne permettent pas de la trancher ;
- le déchiffrement ne la prouverait pas non plus à lui seul. Il donnerait accès à
  l'image en clair, ce qui permettrait de comparer le code, par exemple à la
  configuration d'analyse publiée par le projet A ;
- **le déchiffrement reste interdit** tant que D-008 est ouverte.

Les méthodes de validation sont décrites dans `docs/J2_PREREQUISITES.md` §3.

### 3.2 Disposition en mémoire, comparée sans déchiffrement

Le projet A publie trois valeurs de disposition dans `pc/config/default.toml` (BSD
3-Clause) [V] : l'adresse de chargement de `default.xex`, la fin de son image et
l'adresse de chargement de `fifadllzf.xex`.

| Valeur | Disque de l'utilisateur (rapport J0) | Projet A (`pc/config/default.toml`) | Résultat |
|---|---|---|---|
| Chargement de `default.xex` | `0x82000000` | `0x82000000` | **Concordante** |
| Fin de l'image de `default.xex` | `0x821F0000` (taille `0x1F0000`) | `0x821F0000` | **Concordante** |
| Chargement de `fifadllzf.xex` | `0x82300000` | `0x82300000` | **Concordante** |
| Taille de l'image de `fifadllzf.xex` | `0x1850000` | Non publiée dans ce fichier | Non comparable [I] |

Contrôle complémentaire, sur les seules données publiques du projet A [V] : toutes les
adresses de sa configuration d'analyse tombent dans l'image du module correspondant du
disque de l'utilisateur. Ces fichiers sont :

- `default.toml` et `default_pointers.toml` : 1 980 adresses, toutes dans
  `[0x82000000, 0x821F0000)`. Les deux seules exceptions sont les bornes citées dans un
  commentaire, et non des entrées ;
- `fifadllzf.toml`, `fifadllzf_pointers.toml`, `boot_fixes.cpp` et
  `lua_diagnostics.cpp` : 51 114 adresses, toutes dans `[0x82300000, 0x83B50000)`.

Les adresses comptées sont les débuts de fonctions et les emplacements des pointeurs.
`function_table_base` est exclue.

**Portée** : ces concordances sont une condition **nécessaire, pas suffisante**. Une
disposition différente aurait suffi à rendre invalides les adresses du projet A, et ce
n'est pas le cas. En revanche, une même disposition ne garantit ni un même code, ni la
validité des débuts de fonctions et des pointeurs du projet A [H]. Ni le code machine ni
la configuration d'analyse ne sont établis comme identiques.

## 4. Valeur d'approbation `64` des bibliothèques statiques

### 4.1 Ce que l'outil affiche

- **[V]** L'outil J0 lit, pour chaque entrée de l'en-tête *static libraries*
  (`0x000200FF`), l'octet à l'adresse relative `0x0E` comme type d'approbation, et
  l'octet `0x0F` comme QFE (quatrième composant de la version affichée).
- **[V]** Pour nommer l'approbation, il utilise l'énumération de ReXGlue (0 à 3). Une
  valeur hors de cette énumération est affichée telle quelle, en décimal. `64` est donc
  la valeur brute `0x40` de l'octet `0x0E`.

### 4.2 Comparaison avec les structures de ReXGlue v0.11.0

| Source | Disposition de l'entrée | Valeurs du type d'approbation | Lecture de `0x40` |
|---|---|---|---|
| ReXGlue v0.11.0, `include/rex/kernel/types/xex.h` : `XEXOptStaticLibrary`, `XEXApprovalType` [V] | `name[8]`, `be_u16 version_major`, `be_u16 version_minor`, `be_u16 version_build`, `u8 approval_type`, `u8 version_qfe`, taille `0x10` | `0` unapproved, `1` possible, `2` approved, `3` expired | **Hors énumération** |
| Xenia, `src/xenia/kernel/util/xex2_info.h` : `xex2_opt_static_library` (dont ReXGlue dérive) [V] | Identique | Identique (0 à 3) | Hors énumération |
| idaxex, `formats/xex_optheaders.hpp` et `formats/xex_structs.hpp` : `XexImageLibraryVersion`, `ApprovalType` [V] | Identique : `ApprovalType` sur un octet en `0x0E`, `QFE` en `0x0F` | `0x00` Unapproved, `0x04` Tool, `0x10` Executable, `0x20` PossiblyApproved, `0x40` Approved, `0x60` Expired, `0x80` Debug | **Approved** |

Constats :

- **[V]** Les trois sources s'accordent sur la disposition : un octet d'approbation en
  `0x0E`, un octet de QFE en `0x0F`. La valeur `64` ne déplace donc aucun champ, et la
  version affichée (`majeure.mineure.build.QFE`) reste correctement lue.
- **[V]** ReXGlue v0.11.0 déclare l'en-tête *static libraries*, `XEXOptStaticLibrary` et
  `XEXApprovalType`, mais **ne lit jamais cet en-tête**. Dans `src/` et `include/`, aucune
  occurrence en dehors des déclarations de `include/rex/kernel/types/xex.h`. Les
  `version_qfe` de `project_recompiler.cpp` et de `progress.cpp` sont ceux de la version du
  titre (*execution info*). Cette valeur n'a donc **aucun effet** sur la génération de
  code ni sur le runtime.
- **[H]** Les deux énumérations se réconcilient si l'octet est un ensemble de bits :
  - les bits 5 et 6 portent le niveau d'approbation : `0x20` possible, `0x40` approuvée,
    `0x60` expirée. Ce niveau, décalé de 5 bits, donne exactement les valeurs 1, 2 et 3
    de ReXGlue et de Xenia ;
  - les bits 2, 4 et 7 (`0x04`, `0x10`, `0x80`) sont des indicateurs distincts.

  Selon cette lecture, `0x40` signifie « approuvée », sans autre indicateur.
- **[I]** Aucune spécification officielle n'a été consultée. Le wiki Free60 ne décrit
  pas le contenu des entrées. Cette lecture reste une hypothèse.

### 4.3 Conséquences

- Aucune pour J2 : le champ n'est pas utilisé par ReXGlue.
- Pour l'outil J0 : l'affichage « 64 » est exact (valeur brute), mais pas parlant.
  Proposition, **non réalisée dans cette PR** : afficher la valeur en hexadécimal, avec
  les deux lectures (énumération ReXGlue et octet d'idaxex), en marquant la seconde
  comme hypothèse. Cela demande l'accord de l'orchestrateur.
- Cette analyse n'a lu aucune donnée supplémentaire du jeu. Elle porte sur la seule
  valeur transmise et sur des définitions de format publiques.

Sources :

- [Xenia, `xex2_info.h`](https://raw.githubusercontent.com/xenia-project/xenia/master/src/xenia/kernel/util/xex2_info.h)
- [idaxex, `xex_optheaders.hpp`](https://raw.githubusercontent.com/emoose/idaxex/master/formats/xex_optheaders.hpp)
- [idaxex, `xex_structs.hpp`](https://raw.githubusercontent.com/emoose/idaxex/master/formats/xex_structs.hpp)
- [Free60, XEX](https://free60.org/System-Software/Formats/XEX/)

## 5. Critères de J0 (`docs/ROADMAP.md` §4)

| Critère | Statut | Justification |
|---|---|---|
| C0.1 — Format reconnu, arborescence lue entièrement | **Validé** (2026-11-22) | XGD2 ; 49 fichiers et 8 dossiers ; 0 fichier au-delà de la fin de l'image ; aucune anomalie. L'intégrité du contenu de chaque fichier n'est pas démontrée (§2.1) |
| C0.2 — Empreintes des deux modules comparées au projet A | **Validé** (2026-11-22) | Les deux SHA-256 diffèrent de celles du projet A (§2.2) |
| C0.3 — En-têtes en clair lus | **Validé** (2026-11-22) | Titre `454108E4`, média `6CCD3565`, version `0.0.0.3`, région PAL, chiffrement AES, compression LZX, bibliothèques importées `xam.xex` et `xboxkrnl.exe` (2.0.9328.0, minimale 2.0.8955.0), champs de chargement |
| C0.4 — Rien de propriétaire partagé ni dans `/nix/store` | **Validé** (2026-11-22), avec la limite du §5.1 | Contrôle du rapport et recherches dans `/nix/store` exécutés sur NixOS par l'utilisateur (§5.1) |
| C0.5 — D-008 tranchée | **En attente** | D-008 reste ouverte (§6) ; seule décision bloquante pour J2. L'utilisateur a choisi la voie technique O3 le 2026-11-22. Les conditions de D-008 restent ouvertes : qualification juridique, décision sur la contrainte de mission, accord de démarrage de J2 |

Les validations de C0.1 à C0.4 sont de l'utilisateur et de l'orchestrateur, consignées
le 2026-11-22 dans la
[discussion de la PR #4](https://github.com/mengpo1/fifa2010wc/pull/4#issuecomment-7081900363).
**J0 n'est pas clos** : C0.5 reste en attente. La validation de C0.4 porte sur le
contrôle des données ; elle n'autorise pas le déchiffrement des exécutables.

### 5.1 Validation de C0.4 (2026-11-22)

Vérifications exécutées sur NixOS par l'utilisateur. Les résultats sont repris tels qu'il
les a rapportés (commentaire cité ci-dessus) :

| Vérification (`J0_ISO_IDENTIFICATION.md` §5 et §6) | Résultat |
|---|---|
| `check_proprietary_data.py tree "$WC2010_PRIVATE_DIR/logs"` | `OK: 2 files checked, no proprietary data found`, code de retour 0 |
| `find /nix/store -maxdepth 3 -type f \( -iname '*.xex' -o \( -iname '*.iso' -size +100M \) \) \| wc -l` | `0` |
| `find /nix/store -maxdepth 1 -type f -size +100M \| wc -l` | `1` : `nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude`, 290 728 968 octets |

Limites :

- **[H]** Le nom du seul fichier signalé suggère un paquet de Claude. **[I]** Son
  contenu n'a pas été vérifié. **Il ne faut pas le supprimer.**
- Ces recherches portent sur des noms, des tailles et une profondeur limitée. Elles ne
  prouvent pas l'absence exhaustive de toute donnée propriétaire dans le magasin.
- La validation est acceptée au regard des critères de contrôle de la feuille de route
  (`ROADMAP.md` §4), avec ces limites. L'utilisateur l'a confirmée explicitement.

## 6. D-008 : ce qui change

- **[V]** Le chiffrement des deux modules est **constaté** dans leurs en-têtes en clair,
  et n'est plus une hypothèse : *file format info*, chiffrement normal (AES),
  compression normale (LZX).
- **[V]** Toute voie vers J2 passe donc par l'image en clair des deux modules, que
  ReXGlue obtient en les déchiffrant à la génération de code et à chaque lancement.
- **[V]** Lecture de la source de ReXGlue v0.11.0 (`src/filesystem/xex.cpp`, sans
  exécution), pour l'option O2 :
  - `XEXImage::DecodeWith` accepte un module non chiffré (type 0) : il copie alors
    l'image sans déchiffrement CBC ;
  - `XEXImage::Decode` dérive cependant toujours une clé de session à partir du champ de
    clé de l'en-tête et des clés maîtresses intégrées, avant d'appeler `DecodeWith`.
- **La décision reste ouverte** : la question juridique est inchangée
  (`docs/DECISIONS.md`, D-008).

## 7. Suite

- Prérequis techniques de J2, avec ce qui est réutilisable et ce qui demande une nouvelle
  analyse : `docs/J2_PREREQUISITES.md`.
- Risques mis à jour : `docs/audit/RISKS.md`, R-01 et R-02.
- J2 ne commence pas avant la décision D-008 et l'accord de l'orchestrateur.

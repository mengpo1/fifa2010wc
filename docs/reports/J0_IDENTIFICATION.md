# Rapport du jalon J0 — Identification de l'image du disque

> Mission « J0 — exploitation des résultats de l'ISO », 2026-11-22. Branche
> `claude/j0-results-analysis`, issue de `main` au commit `b429667` (fusion de la PR #3).
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.
>
> Ce rapport ne s'appuie que sur les métadonnées du rapport J0 de l'utilisateur, telles
> que l'orchestrateur les a transmises.
>
> Mises à jour du 2026-11-22 :
> - C0.1 à C0.4 sont validés par l'utilisateur et l'orchestrateur (§5) ;
> - C0.5 est atteint au sens de la gouvernance : D-008 est une décision de projet
>   clôturée, O3 retenue. Le risque juridique résiduel reste ouvert ;
> - J0 est clos, après la vérification du §5.2.
>
> Aucun fichier du jeu n'a été lu, demandé, transmis ou déchiffré pour écrire ce rapport.
> Aucun code n'a été généré. J2 n'est pas commencé.

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
- **aucun déchiffrement n'est engagé**. D-008 retient O3 : ReXGlue déchiffrera les
  modules localement, mais seulement à la phase B du plan de J2, après PB-0. PJ2-3 est
  accordée depuis le 2026-11-23 (D-015 ; `docs/J2_PLAN.md`).

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
| C0.5 — D-008 tranchée | **Atteint** (2026-11-22), au sens de la gouvernance | D-008 est une décision de projet clôturée, O3 retenue (§6). Ce n'est pas une attestation de conformité juridique : le risque juridique résiduel reste ouvert (R-01). L'autorisation de commencer J2 (PJ2-3) est une décision distincte |

Les validations de C0.1 à C0.4 sont de l'utilisateur et de l'orchestrateur, consignées
le 2026-11-22 dans la
[discussion de la PR #4](https://github.com/mengpo1/fifa2010wc/pull/4#issuecomment-7081900363).
C0.5 suit la décision D-008 du porteur du projet
([ticket #8, commentaire 7086214621](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7086214621)).
La validation de C0.4 porte sur le contrôle des données. Ni elle, ni C0.5 n'autorisent à
traiter les exécutables : cela relève de PJ2-3.

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

### 5.2 Vérification avant la clôture de J0 (2026-11-22)

La décision de D-008 demande de ne marquer J0 terminé qu'après la mise à jour des
documents et une revue de cohérence. Voici ce que J0 exige (`ROADMAP.md` §2 et §4), et
ce qui y répond :

| Exigence de J0 | Où | État |
|---|---|---|
| Trancher D-008 | `docs/DECISIONS.md`, D-008 | Fait : décision de projet clôturée, O3 retenue |
| Appliquer la procédure d'identification sans déchiffrement | §1 et §2 | Fait : outil v1, exécuté par l'utilisateur sur sa machine |
| Livrable : un rapport sans contenu propriétaire, avec le verdict « disque Europe du projet A, oui ou non » | Ce rapport, §2 et §3 | Fait : verdict « non » au sens des empreintes. Le contrôle des données du dépôt passe |
| C0.1 à C0.4 | §5 | Validés le 2026-11-22 ; C0.4 avec la limite du §5.1 |
| C0.5 | §5 | Atteint au sens de la gouvernance |

Points encore ouverts. Aucun n'est un critère de J0 :

| Point | Suite |
|---|---|
| Identité du code machine avec celui du projet A [I] | J2 : validation avant toute réutilisation (`docs/J2_PREREQUISITES.md` §3, `docs/J2_PLAN.md` phase B) |
| Qualification juridique des actes | Risque résiduel R-01 (`docs/audit/RISKS.md`). C0.5 demande que D-008 soit tranchée, et elle l'est |
| Affichage de la valeur d'approbation `64` (§4.3) | Proposition en attente d'accord, sans effet sur J2 |
| Fichier `nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude` du magasin (§5.1) | Ni supprimé, ni examiné plus avant |
| Limite de C0.4 : les recherches ne sont pas exhaustives (§5.1) | Contrôles du magasin répétés à la phase B (`docs/J2_PREREQUISITES.md` §6) |
| Existence d'une mise à jour du titre [I] | `docs/audit/ISO_REQUIREMENTS.md` §7 |

**J0 est clos** (2026-11-22) : C0.1 à C0.5 sont atteints, et aucune autre exigence de J0
ne manque. La clôture prend effet avec la fusion de la mise à jour qui l'enregistre,
après la revue de cohérence demandée dans le ticket #8.

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
- Au moment de ce constat, la décision restait ouverte, et la question juridique était
  inchangée.
- **Clôture (2026-11-22)** : D-008 est une décision de projet clôturée, O3 retenue.
  ReXGlue déchiffrera donc lui-même, localement, une fois J2 autorisé. La question
  juridique n'est pas tranchée pour autant : le risque résiduel reste ouvert
  (`docs/DECISIONS.md`, D-008 ; `docs/audit/RISKS.md`, R-01).

## 7. Suite

- Prérequis techniques de J2, avec ce qui est réutilisable et ce qui demande une nouvelle
  analyse : `docs/J2_PREREQUISITES.md`.
- Risques mis à jour : `docs/audit/RISKS.md`, R-01 et R-02.
- Plan de J2 en deux phases, avec critères de sortie et points d'arrêt :
  `docs/J2_PLAN.md`.
- J2 ne commence pas avant l'autorisation explicite PJ2-3. Ni la décision D-008, ni la
  clôture de J0, ni le plan n'en tiennent lieu. *Elle est accordée le 2026-11-23
  (D-015) ; le traitement des fichiers du jeu attend PB-0.*

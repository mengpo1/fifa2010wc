# Prérequis techniques du jalon J2

> Préparé le 2026-11-22, après l'identification du disque de l'utilisateur
> (`docs/reports/J0_IDENTIFICATION.md`). **Ce document ne commence pas J2.** Il dit ce
> dont J2 aura besoin, ce qui peut être repris du projet A et ce qui demande une
> nouvelle analyse.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Point de départ

- **J1** : chaîne de compilation Linux et NixOS validée et fusionnée (PR #2). C1.4 est
  validé sur le GPU de l'utilisateur.
- **J0** : identification faite (PR #3 pour l'outil).
  - Le disque de l'utilisateur est un XGD2 PAL du titre `454108E4`, version `0.0.0.3` :
    49 fichiers, 8 dossiers, aucune anomalie.
  - Les SHA-256 de ses deux modules **diffèrent** de ceux du projet A.
  - Les deux modules sont chiffrés (AES) et compressés (LZX).
  - Leur disposition en mémoire **concorde** avec les trois valeurs publiées par le
    projet A (`J0_IDENTIFICATION.md` §3.2).
- **D-008** reste ouverte. Le code machine des deux disques peut être identique ou
  différent [I]. Ni les empreintes des fichiers, ni la disposition en mémoire ne
  suffisent à le dire (`J0_IDENTIFICATION.md` §3).

## 2. Prérequis bloquants

| N° | Prérequis | État | Responsable |
|---|---|---|---|
| PJ2-1 | D-008 tranchée. Toute génération de code a besoin de l'image en clair des deux modules. Éléments de décision : `docs/D-008_DECISION_NOTE.md` | **Ouverte** | Orchestrateur ou utilisateur, après avis juridique |
| PJ2-2 | J0 clos : C0.5 atteint (`J0_IDENTIFICATION.md` §5) | C0.1 à C0.4 validés le 2026-11-22 ; C0.5 en attente, c'est-à-dire D-008 (PJ2-1) | Orchestrateur ou utilisateur |
| PJ2-3 | Autorisation explicite de commencer J2 | Non donnée | Orchestrateur |

Aucun des travaux ci-dessous ne commence avant PJ2-3.

## 3. Établir si le code du disque est celui du projet A

La configuration d'analyse du projet A (débuts de fonctions, pointeurs de code,
`setjmp`/`longjmp`, correctifs à adresses fixes) ne vaut que pour le code de son disque.
Avant de la réutiliser, il faut établir que le code du disque de l'utilisateur est le
même. Les étapes vont de la moins coûteuse à la plus probante.

### 3.1 Sans déchiffrement : disposition en mémoire (faite le 2026-11-22)

Le projet A publie trois valeurs de disposition dans `pc/config/default.toml` (BSD
3-Clause) [V]. Le rapport J0 de l'utilisateur contient les champs correspondants, lus en
clair [V].

| Valeur | Disque de l'utilisateur | Projet A | Résultat |
|---|---|---|---|
| Chargement de `default.xex` | `0x82000000` | `0x82000000` | Concordante |
| Fin de l'image de `default.xex` | `0x821F0000` (taille 2 031 616 octets, `0x1F0000`) | `0x821F0000` | Concordante |
| Chargement de `fifadllzf.xex` | `0x82300000` | `0x82300000` | Concordante |
| Taille de l'image de `fifadllzf.xex` | 25 493 504 octets (`0x1850000`), fin `0x83B50000` | Non publiée dans ce fichier | Non comparable [I] |

Contrôle complémentaire, sur les seules données publiques du projet A [V] : les 1 980
adresses de la configuration de `default.xex` et les 51 114 de celle de `fifadllzf.xex`
(débuts de fonctions, emplacements des pointeurs, crochets des deux correctifs du jeu)
tombent toutes dans l'image du module correspondant du disque de l'utilisateur
(`J0_IDENTIFICATION.md` §3.2).

**Portée** :

- c'est une condition **nécessaire, pas suffisante**. Une différence aurait suffi à
  écarter la configuration du projet A ; la concordance ne prouve ni un même code, ni la
  validité des adresses ;
- elle **ne vérifie pas** `function_table_base = 0x86100000`. Le placement de la table
  de répartition dépend d'autres contraintes du runtime (§5).

### 3.2 Avec l'image en clair : tests de compatibilité, puis validation des adresses

Seulement si D-008 permet d'obtenir l'image en clair, et dans le dossier privé de
l'utilisateur. Le déchiffrement ne prouve rien à lui seul : il donne accès au code en
clair, qui peut alors être comparé à ce que le projet A a publié de son propre code.

**Étape A — tests de compatibilité initiaux.** Ils détectent une incompatibilité, mais
ne prouvent pas l'identité du code :

1. génération de code de ReXGlue avec la configuration du projet A, sur les modules de
   l'utilisateur ;
2. critère C2.1 : 0 `UnresolvedCall` et 0 erreur de validation ;
3. contrôles ciblés :
   - `setjmp` et `longjmp` du projet A (`0x8283C680`, `0x8283C950`) désignent des
     fonctions de la forme attendue (`find_setjmp.py`) ;
   - les sites des correctifs du jeu (§5) contiennent les séquences d'instructions
     décrites dans leurs commentaires.

Un échec à cette étape écarte la réutilisation telle quelle : nouvelle analyse (§5). Un
succès **ne suffit pas** pour reprendre les milliers de pointeurs et d'adresses du projet
A. Un analyseur peut accepter une adresse fausse, et un pointeur faux peut ne produire
aucune erreur de génération.

**Étape B — validation spécifique avant toute réutilisation des adresses.** Elle est
exigée avant de reprendre les 663 et 17 028 lignes de pointeurs, les débuts de fonctions
et les adresses des correctifs :

1. régénérer, avec les outils du projet A, ses fichiers d'analyse à partir de l'image de
   l'utilisateur :
   - `find_code_pointers.py` pour `*_pointers.toml` ;
   - `autofix_codegen.py` pour les débuts de fonctions ;
   - `find_setjmp.py` pour `setjmp` et `longjmp` ;
2. exiger que les résultats régénérés soient **identiques** aux fichiers publiés par le
   projet A : mêmes adresses, et mêmes emplacements de données notés en commentaire ;
3. vérifier une à une les adresses écrites à la main, qu'aucun outil ne régénère :
   `boot_fixes.cpp` (fonction, registre et emplacement) et `lua_diagnostics.cpp`
   (`luaD_throw` et décalages des structures Lua), d'après le code désassemblé ;
4. au moindre écart, garder la sortie régénérée pour le disque de l'utilisateur, et non
   le fichier du projet A, puis reprendre l'analyse sur les points divergents.

Même identiques, les fichiers régénérés ne prouvent pas l'identité intégrale des images.
Ils établissent que la configuration d'analyse est valable pour ce disque, ce qui suffit
au projet. Une comparaison d'images complète demanderait l'empreinte de l'image en clair
du projet A, qui n'est pas publiée [I].

## 4. Réutilisable sans nouvelle analyse du disque

| Élément | Origine | Pourquoi il ne dépend pas du disque | Statut |
|---|---|---|---|
| Chaîne de compilation, SDK, tests, CI, contrôles de données | Ce dépôt (J1) | Aucune donnée du jeu | [V] |
| Runtime ReXGlue, pilotes Vulkan, audio et entrées SDL3 | ReXGlue v0.11.0 | Indépendants du titre | [V] |
| Structure du manifeste : `default.xex` en point d'entrée, `fifadllzf.xex` chargé par son nom | Projet A, `pc/fifawc10_manifest.toml` | Les deux modules existent sous ces noms sur le disque de l'utilisateur, avec les mêmes adresses de chargement (§3.1) | [V] pour les noms et le chargement ; chemins à adapter au dossier privé |
| Bibliothèques importées : `xam.xex` et `xboxkrnl.exe`, version 2.0.9328.0, minimale 2.0.8955.0 | Rapport J0 | Ce sont les services système que ReXGlue fournit | [V] noms et versions ; la liste des fonctions importées n'est pas connue avant J2 [I] |
| Outils d'analyse en Python : `disc.py`, `xexinfo.py`, `ppcdis.py`, `find_code_pointers.py`, `find_setjmp.py`, `xref.py`, `callers.py`, `autofix_codegen.py` | Projet A, `tools/` | Ce sont des méthodes, pas des résultats ; elles s'appliquent à tout binaire, et servent aussi à la validation (§3.2, étape B) | [V] portables (audit) ; reprise avec notice (D-010). **Exclu** : `xeximage.py`, qui déchiffre (D-008) |
| Correctifs du SDK sans adresse du jeu : 0001 (exports de la caméra USB), 0002 (module trouvé par son nom nu), 0004 (vblank), 0006 (cadence), 0007 (dialogues), 0008 (énumération des sauvegardes) | Projet A, `patches/rexglue-sdk/` | Ils modifient le SDK, pas le code du jeu | [V] sans adresse ; [H] encore utiles au même titre ; transposition vers v0.11.0 à faire (R-04, 338 commits d'écart) |
| Réglages GPU : `execute_unclipped_draw_vs_on_cpu`, `gpu_allow_invalid_fetch_constants` | Projet A | Ils portent sur le rendu du moteur, pas sur des adresses | [H] valables pour le même moteur |
| Savoir : Lua avec `setjmp`/`longjmp` à rediriger, fil de décodage vidéo, exports de la caméra USB | Audit (`LINUX_FEASIBILITY.md` §2.3) | Propriétés du moteur du jeu | [H] mêmes besoins ; adresses à valider (§3.2) |
| Constats de J1 : `-DREXGLUE_LLD` vers le `ld.lld` enveloppé, RUNPATH, durcissement | `docs/reports/J1_VALIDATION.md` §6 | Propriétés de la chaîne de compilation | [V] |

## 5. À valider (§3.2) ou à refaire

| Élément du projet A | Valeur ou volume | Dépend de | Action |
|---|---|---|---|
| Débuts de fonctions ajoutés (`[functions]`, marqueur « autofix ») | Dans `pc/config/default.toml` et `fifadllzf.toml` | Adresses du code | Étape B : régénérer avec `autofix_codegen.py`, comparer, garder la sortie régénérée |
| Pointeurs de code | 663 lignes (`default_pointers.toml`), 17 028 lignes (`fifadllzf_pointers.toml`) | Adresses du code et des données | Étape B : régénérer avec `find_code_pointers.py`, exiger l'identité |
| `setjmp_address`, `longjmp_address` | `0x8283C680`, `0x8283C950` | Adresses du CRT dans `fifadllzf.xex` | Étape A, puis `find_setjmp.py` et vérification manuelle (étape B) |
| `function_table_base` (correctif 0003) | `0x86100000` | La disposition des modules, concordante (§3.1), mais aussi des contraintes du runtime que les en-têtes ne donnent pas : taille de la table de répartition de chaque module, carte mémoire invitée de ReXGlue v0.11.0, autres réservations | **Non vérifiable par les seuls en-têtes.** À établir à J2 avec le runtime de v0.11.0, lors de la transposition du correctif 0003 |
| `pc/fixes/boot_fixes.cpp` | Crochet sur `sub_82CBD7E0`, registre en `0x83A4648C`, emplacement `0x64` | Adresses du code et des données | Étape B : vérification manuelle ; si écart, retrouver la fonction et le registre équivalents et réécrire le crochet |
| `pc/fixes/lua_diagnostics.cpp` | Crochet sur `sub_829655A8` (`luaD_throw`), décalages de structures Lua | Adresse de la fonction ; disposition des structures de Lua | Étape B : vérification manuelle ; les décalages sont propres à la version de Lua [H] |
| Valeurs du manifeste | Chemins `out/game-files`, `sdk_version = "0.10.0"` | Installation du projet A | Chemins vers le dossier privé (variable d'environnement), `sdk_version` de v0.11.0 |

Coût d'une nouvelle analyse, si l'étape A ou B échoue : de quelques jours à quelques
semaines [H] (`ISO_REQUIREMENTS.md` §3, étape 6). Les outils du projet A la rendent
faisable sans réécrire de méthode.

## 6. Préparations sans données du jeu, après autorisation de J2

Ces travaux font partie de J2, mais ne lisent aucune donnée du jeu ; ils peuvent donc
avancer pendant que D-008 est examinée, si l'orchestrateur ouvre J2 :

- transposer les correctifs 0001 à 0004 et 0006 à 0008 vers ReXGlue v0.11.0, avec les
  tests du SDK. Pour 0003, établir les contraintes de placement de la table de
  répartition dans le runtime de v0.11.0 (§5) ;
- écrire un gabarit de manifeste qui prend ses chemins dans `$WC2010_PRIVATE_DIR`, sans
  aucun chemin ni valeur propres au disque dans le dépôt ;
- écrire la couche `platform/linux` : répertoires XDG, journaux, gestionnaire de
  plantage par signaux (`ROADMAP.md`, J2) ;
- prévoir l'extraction de la racine du jeu dans le dossier privé par
  `rexglue vfs dump`, qui ne déchiffre rien. En v0.11.0, `title.game_root` doit être un
  dossier.

## 7. Ordre proposé pour J2 (à valider)

1. D-008 tranchée (PJ2-1), J0 clos (PJ2-2), J2 autorisé (PJ2-3).
2. ~~Comparaison en clair de la disposition (§3.1).~~ Faite : concordante, condition
   nécessaire seulement.
3. Préparations sans données du jeu (§6).
4. Extraction de la racine du jeu dans le dossier privé.
5. Selon D-008 : tests de compatibilité (§3.2, étape A), puis validation des adresses
   (étape B). La configuration du projet A n'est reprise que pour ce qui passe l'étape B ;
   le reste est réanalysé (§5).
6. Édition de liens et critères C2.1 à C2.4 (`ROADMAP.md` §4).

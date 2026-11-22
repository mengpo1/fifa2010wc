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
  - Le disque de l'utilisateur est un XGD2 PAL du titre `454108E4`, version `0.0.0.3`.
  - Les SHA-256 de ses deux modules **diffèrent** de ceux du projet A.
  - Les deux modules sont chiffrés (AES) et compressés (LZX).
- **D-008** reste ouverte. Le code machine des deux disques peut être identique ou
  différent [I] : les empreintes des fichiers ne suffisent pas à le dire
  (`J0_IDENTIFICATION.md` §3).

## 2. Prérequis bloquants

| N° | Prérequis | État | Responsable |
|---|---|---|---|
| PJ2-1 | D-008 tranchée. Toute génération de code a besoin de l'image en clair des deux modules | **Ouverte** | Orchestrateur ou utilisateur, après avis juridique |
| PJ2-2 | J0 clos : C0.1 et C0.4 confirmés, C0.5 atteint (`J0_IDENTIFICATION.md` §5) | Partiel | Utilisateur (comptes et codes de sortie), orchestrateur |
| PJ2-3 | Autorisation explicite de commencer J2 | Non donnée | Orchestrateur |

Aucun des travaux ci-dessous ne commence avant PJ2-3.

## 3. Établir si le code du disque est celui du projet A

La configuration d'analyse du projet A (débuts de fonctions, pointeurs de code,
`setjmp`/`longjmp`, correctifs à adresses fixes) ne vaut que pour le code de son disque.
Avant de la réutiliser, il faut établir que le code du disque de l'utilisateur est le
même. Deux étapes, de la moins coûteuse à la plus probante.

### 3.1 Sans déchiffrement : comparer la disposition en mémoire

Le projet A publie, sous licence BSD 3-Clause, quelques faits sur la disposition de ses
modules (`pc/config/default.toml` de son dépôt) [V] :

| Fait publié par le projet A | Valeur |
|---|---|
| Adresse de chargement de `default.xex` | `0x82000000` |
| Fin de l'image de `default.xex` | `0x821F0000` : la table de répartition commencerait là. Taille d'image déduite : `0x1F0000` [H] |
| Adresse de chargement de `fifadllzf.xex` | `0x82300000` |
| Base de la table de répartition (correctif 0003) | `0x86100000` |

Le rapport local de l'utilisateur contient déjà les champs correspondants de ses
modules, lus en clair : adresse de chargement et taille de l'image chargée, pour chacun.
Ce sont des métadonnées d'en-tête, autorisées par D-007.

- **Différence** : la disposition change, et les adresses du projet A ne s'appliquent pas
  telles quelles. C'est une preuve forte d'un code différent, au moins dans sa
  disposition.
- **Égalité** : condition nécessaire, pas suffisante. Deux compilations différentes
  peuvent avoir la même disposition [H]. Il faut alors l'étape 3.2.
- **Condition** : cette comparaison demande que l'utilisateur transmette ces quatre
  valeurs. La mission J0 interdit de demander des données supplémentaires ; la
  comparaison est donc **à soumettre à l'orchestrateur**, qui décidera de la demander.

### 3.2 Avec l'image en clair : appliquer la configuration et la valider

Seulement si D-008 permet d'obtenir l'image en clair, et dans le dossier privé de
l'utilisateur :

1. Lancer la génération de code de ReXGlue avec la configuration du projet A sur les
   modules de l'utilisateur.
2. Critère C2.1 : 0 `UnresolvedCall` et 0 erreur de validation.
3. Contrôles ciblés :
   - `setjmp` et `longjmp` du projet A (`0x8283C680`, `0x8283C950`) désignent des
     fonctions de la forme attendue (`find_setjmp.py`) ;
   - les sites des correctifs du jeu (§5) contiennent les séquences d'instructions
     décrites dans leurs commentaires.
4. Tout réussit : la configuration est réutilisée, avec notice (D-010). Un seul échec :
   nouvelle analyse (§5).

## 4. Réutilisable sans nouvelle analyse du disque

| Élément | Origine | Pourquoi il ne dépend pas du disque | Statut |
|---|---|---|---|
| Chaîne de compilation, SDK, tests, CI, contrôles de données | Ce dépôt (J1) | Aucune donnée du jeu | [V] |
| Runtime ReXGlue, pilotes Vulkan, audio et entrées SDL3 | ReXGlue v0.11.0 | Indépendants du titre | [V] |
| Structure du manifeste : `default.xex` en point d'entrée, `fifadllzf.xex` chargé par son nom | Projet A, `pc/fifawc10_manifest.toml` | Les deux modules existent sous ces noms sur le disque de l'utilisateur (empreintes J0) | [V] pour les noms ; chemins à adapter au dossier privé |
| Outils d'analyse en Python : `disc.py`, `xexinfo.py`, `ppcdis.py`, `find_code_pointers.py`, `find_setjmp.py`, `xref.py`, `callers.py`, `autofix_codegen.py` | Projet A, `tools/` | Ce sont des méthodes, pas des résultats ; elles s'appliquent à tout binaire | [V] portables (audit) ; reprise avec notice (D-010). **Exclu** : `xeximage.py`, qui déchiffre (D-008) |
| Correctifs du SDK sans adresse du jeu : 0001 (exports de la caméra USB), 0002 (module trouvé par son nom nu), 0004 (vblank), 0006 (cadence), 0007 (dialogues), 0008 (énumération des sauvegardes) | Projet A, `patches/rexglue-sdk/` | Ils modifient le SDK, pas le code du jeu | [V] sans adresse ; [H] encore utiles au même titre ; transposition vers v0.11.0 à faire (R-04, 338 commits d'écart) |
| Réglages GPU : `execute_unclipped_draw_vs_on_cpu`, `gpu_allow_invalid_fetch_constants` | Projet A | Ils portent sur le rendu du moteur, pas sur des adresses | [H] valables pour le même moteur |
| Savoir : Lua avec `setjmp`/`longjmp` à rediriger, fil de décodage vidéo, exports de la caméra USB | Audit (`LINUX_FEASIBILITY.md` §2.3) | Propriétés du moteur du jeu | [H] mêmes besoins ; adresses à retrouver (§5) |
| Constats de J1 : `-DREXGLUE_LLD` vers le `ld.lld` enveloppé, RUNPATH, durcissement | `docs/reports/J1_VALIDATION.md` §6 | Propriétés de la chaîne de compilation | [V] |

## 5. À revalider (§3.2) ou à refaire

| Élément du projet A | Valeur ou volume | Dépend de | Action si le code diffère |
|---|---|---|---|
| Débuts de fonctions ajoutés (`[functions]`, marqueur « autofix ») | Dans `pc/config/default.toml` et `fifadllzf.toml` | Adresses du code | Relancer `autofix_codegen.py` jusqu'à 0 `UnresolvedCall` |
| Pointeurs de code | 663 lignes (`default_pointers.toml`), 17 028 lignes (`fifadllzf_pointers.toml`) | Adresses du code et des données | `find_code_pointers.py` sur l'image de l'utilisateur |
| `setjmp_address`, `longjmp_address` | `0x8283C680`, `0x8283C950` | Adresses du CRT dans `fifadllzf.xex` | `find_setjmp.py`, puis vérification manuelle |
| `function_table_base` (correctif 0003) | `0x86100000` | Adresses de chargement et tailles d'image des deux modules | Recalcul à partir des champs en clair (§3.1), **sans déchiffrement** |
| `pc/fixes/boot_fixes.cpp` | Crochet sur `sub_82CBD7E0`, registre en `0x83A4648C`, emplacement `0x64` | Adresses du code et des données | Retrouver la fonction et le registre équivalents, puis réécrire le crochet |
| `pc/fixes/lua_diagnostics.cpp` | Crochet sur `sub_829655A8` (`luaD_throw`), décalages de structures Lua | Adresse de la fonction ; disposition des structures de Lua | Retrouver `luaD_throw` ; les décalages sont propres à la version de Lua [H] |
| Valeurs du manifeste | Chemins `out/game-files`, `sdk_version = "0.10.0"` | Installation du projet A | Chemins vers le dossier privé (variable d'environnement), `sdk_version` de v0.11.0 |

Coût d'une nouvelle analyse : de quelques jours à quelques semaines [H]
(`ISO_REQUIREMENTS.md` §3, étape 6). Les outils du projet A la rendent faisable sans
réécrire de méthode.

## 6. Préparations sans données du jeu, après autorisation de J2

Ces travaux font partie de J2, mais ne lisent aucune donnée du jeu ; ils peuvent donc
avancer pendant que D-008 est examinée, si l'orchestrateur ouvre J2 :

- transposer les correctifs 0001 à 0004 et 0006 à 0008 vers ReXGlue v0.11.0, avec les
  tests du SDK ;
- écrire un gabarit de manifeste qui prend ses chemins dans `$WC2010_PRIVATE_DIR`, sans
  aucun chemin ni valeur propres au disque dans le dépôt ;
- écrire la couche `platform/linux` : répertoires XDG, journaux, gestionnaire de
  plantage par signaux (`ROADMAP.md`, J2) ;
- prévoir l'extraction de la racine du jeu dans le dossier privé par
  `rexglue vfs dump`, qui ne déchiffre rien. En v0.11.0, `title.game_root` doit être un
  dossier.

## 7. Ordre proposé pour J2 (à valider)

1. D-008 tranchée (PJ2-1), J0 clos (PJ2-2), J2 autorisé (PJ2-3).
2. Comparaison en clair de la disposition (§3.1), sur décision de l'orchestrateur.
3. Préparations sans données du jeu (§6).
4. Extraction de la racine du jeu dans le dossier privé.
5. Selon D-008 : génération de code avec la configuration du projet A, puis validation
   (§3.2). Elle est réutilisée, ou l'analyse est refaite (§5).
6. Édition de liens et critères C2.1 à C2.4 (`ROADMAP.md` §4).

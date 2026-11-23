# J2, étape A3 — Base de la table de répartition des fonctions

> Étape A3 de `docs/J2_PLAN.md` (§3.3), sous l'autorisation PA-0 (D-015). **Phase A :
> aucune donnée du jeu.** Le correctif est essayé sur des images synthétiques
> seulement.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Résultat

- **Le correctif** : `patches/rexglue-sdk/0001-function-table-base.patch`. C'est le
  correctif 0003 du projet A, réécrit pour ReXGlue v0.11.0. Il est appliqué par
  `nix/rexglue-sdk.nix`, et ses tests passent dans la construction du SDK (§5.3).
- **Sans la clé `function_table_base`**, la table reste là où l'amont la place, et le
  code généré calcule la même adresse (§5.2).
- **Besoin pour ce disque** : la table de `default.xex` empiète sur l'image de
  `fifadllzf.xex` si le code de `default.xex` dépasse `0x78000` octets. Cette taille
  reste inconnue [I] (§7).
- **Constat sur v0.11.0** : une allocation à adresse fixe avec réservation et engagement
  ne refuse pas des pages déjà réservées [V]. Elle les reprend, et la table les met à
  zéro. Le correctif alloue donc une table déplacée par une **allocation exclusive** :
  la vérification des pages et leur prise se font sous une seule prise du verrou du tas,
  et rien n'est modifié en cas de conflit (§4.2, P-38).
- **Tailles sur 64 bits** : la taille et la fin de la table sont calculées sur 64 bits et
  comparées au tas avant d'être ramenées à 32 bits (§5.1, P-39).
- **Valeur du projet A, `0x86100000`** : elle ne convient que si le code de
  `fifadllzf.xex` ne dépasse pas `0x12C8000` octets. Cette taille est inconnue [I].
- **Valeur valable pour toute taille de code** : `0x86C10000`, calculée à partir des
  seuls en-têtes en clair (§7). Le choix de la valeur revient à la phase B.

## 2. Méthode

- **Source** : ReXGlue v0.11.0 à la révision `a3e1d82`. Les références `fichier:ligne`
  désignent cette source, avant correctif.
- **Valeurs du disque** : celles des en-têtes en clair relevées à J0
  (`docs/reports/J0_IDENTIFICATION.md`) :
  - `default.xex` chargé à `0x82000000`, image de `0x1F0000` octets, fin `0x821F0000` ;
  - `fifadllzf.xex` chargé à `0x82300000`, image de `0x1850000` octets, fin
    `0x83B50000` ;
  - les deux modules sont compressés (LZX).
- **Aucune adresse de la configuration d'analyse du projet A** n'entre dans le correctif
  ni dans ses tests (CP-7). La valeur `0x86100000` n'est citée que pour être examinée.
- **Tests** : images synthétiques du SDK (`tests/unit/codegen/code_image.h`) et
  mémoire invitée de test. Ils tournent dans le `checkPhase` de `nix/rexglue-sdk.nix`.

## 3. La table de répartition en v0.11.0 [V]

| Élément | Comportement | Référence |
|---|---|---|
| Base de la table | `image_base + image_size`, sans réglage possible | `src/kernel/memory.cpp:778-807` |
| Taille | `(code_size + 0x10000) × 2` : 8 octets par instruction de 4 octets, plus la réserve de *thunks* | `src/kernel/memory.cpp:778-807`, `include/rex/kernel/function_dispatcher.h:95` |
| Allocation | `AllocFixed` dans le tas `v80000000`, réservation et engagement, puis mise à zéro de toute la table | `src/kernel/memory.cpp:789-796` |
| Recherche par le code généré | `REX_LOOKUP_FUNC` calcule `REX_IMAGE_BASE + REX_IMAGE_SIZE + (cible − REX_CODE_BASE) × 2` | `resources/templates/codegen/_indirect_call.inja:15-18` |
| Recherche par le runtime | par la base enregistrée de chaque table | `src/kernel/memory.cpp:836-846` |
| Contrôle des chevauchements | entre les plages `[image, fin de la table)` des modules déjà enregistrés | `src/kernel/function_dispatcher.cpp:162-207` |
| Appelants | le titre (`default.xex`) à son installation, puis chaque module recompilé chargé ensuite | `src/kernel/title_state.cpp:332`, `src/kernel/module_registry.cpp:481-483` |

**Ordre des allocations** [V code ; ordre d'exécution [H]] :
1. l'image de `default.xex` est allouée, puis sa table, à l'installation du titre ;
2. `fifadllzf.xex` est chargé plus tard par le jeu (`XexLoadImage`), car `default.xex`
   n'importe que `xam.xex` et `xboxkrnl.exe` (J0). Le chargeur vérifie d'abord que sa
   plage est libre (`src/kernel/xex_module.cpp:221-229`).

Sans correctif, si la table de `default.xex` empiète sur `0x82300000`, le chargement de
`fifadllzf.xex` échoue donc avec un message explicite : « XEX image range … is in use »
[V code ; [H] que ce soit la première erreur rencontrée].

## 4. Carte mémoire invitée et réservations

### 4.1 Tas concernés [V]

| Plage | Tas | Pages | Usage | Référence |
|---|---|---|---|---|
| `0x00000000-0x3FFFFFFF` | `v00000000` | 4 Kio | Allocations de l'invité sans adresse imposée, tas système | `src/kernel/memory.cpp:275-276` |
| `0x40000000-0x7EFFFFFF` | `v40000000` | 64 Kio | Allocations de l'invité sans adresse imposée | `src/kernel/memory.cpp:277-278` |
| **`0x80000000-0x8FFFFFFF`** | **`v80000000`** | **64 Kio** | **Images XEX et tables de répartition** | `src/kernel/memory.cpp:279-280` |
| `0x90000000-0x9FFFFFFF` | `v90000000` | 4 Kio | Images XEX | `src/kernel/memory.cpp:281-282` |
| `0xA0000000-0xFFFFFFFF` | tas physiques | 64 Kio à 16 Mio | Mémoire physique, GPU | `src/kernel/memory.cpp:284-291` |

Dans `v80000000`, en dehors des images et des tables, le SDK ne réserve qu'une zone de
`0x40000` octets au démarrage, au début du tas : un titre y lit une constante à
`0x8000001C` (`src/kernel/memory.cpp:321-327`) [V]. Le tas système va dans `v00000000`
(`src/kernel/memory.cpp:491-507,660-665`). Une allocation virtuelle de l'invité va dans
`v00000000` ou `v40000000`, sauf si l'invité impose son adresse : elle va alors dans le
tas de cette adresse (`src/kernel/xboxkrnl/xboxkrnl_memory.cpp:192-205`) [V].

**Non connu** [I] : si le jeu impose lui-même une adresse dans `v80000000`. Seule
l'exécution le dira (phase B).

### 4.2 `AllocFixed` ne refuse pas des pages déjà réservées [V]

- Dans `BaseHeap::AllocFixedLocked`, le refus d'une plage déjà réservée ne s'applique
  qu'à une demande de **réservation seule** (`src/kernel/memory.cpp:1158-1165`).
- La table est demandée avec réservation **et** engagement (`src/kernel/memory.cpp:789-793`).
  Sur des pages déjà réservées, l'allocation réussit : les pages changent de
  propriétaire, puis la table est mise à zéro (`:796`).
- Le chargeur des XEX contrôle lui-même que sa plage est libre
  (`src/kernel/xex_module.cpp:221-229`). La table, non.

**Conséquence** : à sa place par défaut, la table suit son image, sur des pages libres
au moment de l'installation. Une table **déplacée** pourrait en revanche effacer une
autre allocation sans aucune erreur. Le correctif l'interdit (§5.1).

**Vérifier puis allouer ne suffit pas** (P-38, revue 6023670172). La première version du
correctif interrogeait la plage (`QueryRegionInfo`), puis appelait `AllocFixed`. Chacun
prend le verrou du tas pour lui seul (`src/kernel/memory.cpp:1646-1652` et `:1156`) [V].
Un autre fil pouvait donc réserver des pages entre les deux appels, et la table les
aurait reprises puis effacées. Le correctif ajoute `BaseHeap::AllocFixedExclusive` :
- il vérifie que **toutes** les pages de la plage sont libres, dans `AllocFixedLocked`,
  sous la même prise du verrou que la mise à jour de la table des pages ;
- en cas de conflit, il échoue **avant** toute modification : aucune page n'est prise,
  aucune n'est effacée ;
- si une étape ultérieure échoue (synchronisation des droits de l'hôte), il rend la
  plage, qui était libre avant l'appel. Les autres échecs possibles, refus de l'hôte et
  budget de mémoire du titre, surviennent avant toute modification [V code] ;
- il refuse un tas physique, dont il ne vérifierait pas le tas parent.

## 5. Le correctif

### 5.1 Contenu

| Partie | Changement |
|---|---|
| Configuration de la génération de code | Clé par binaire `function_table_base`, entier, 0 par défaut. Refusée si elle n'est pas alignée sur 64 Kio, si elle sort de `0x80000000-0x8FFFFFFF` ou si elle dépasse 32 bits. Elle n'est jamais reprise d'une couche partagée (`ClearAddressEntries`) |
| Gabarits | `REX_FUNC_TABLE_BASE` dans l'en-tête généré. `REX_LOOKUP_FUNC` s'en sert. `PPCImage::function_table_base` est renseigné dans l'initialisation générée |
| Runtime | `FunctionDispatcher::InitializeFunctionTable` et `GuestAddressSpace::InitializeFunctionTable` reçoivent la base. Le titre et les modules la transmettent depuis leur `PPCImage` |
| Contrôles du runtime | Pas de chevauchement entre images et tables, dans toutes les combinaisons, y compris une table et sa propre image. Débuts et fins de plages calculés sur 64 bits ; une image, une table ou un code (avec sa réserve de *thunks*) qui ne tient pas en 32 bits est refusé, avant que les champs de 32 bits ne soient remplis |
| Mémoire invitée | Taille et fin de la table sur 64 bits, comparées aux bornes du tas `v80000000` avant la conversion en 32 bits. Une table déplacée est allouée par `AllocFixedExclusive` (§4.2) ; la place par défaut garde l'appel de l'amont |
| Tas (`BaseHeap`) | Nouvelle allocation exclusive `AllocFixedExclusive` (§4.2) |
| Point d'injection pour les tests | `GuestAddressSpace::function_table_alloc_hook_for_testing`, vide en usage normal : appelé juste avant l'allocation d'une table déplacée |
| Journal | Le message de niveau *debug* donne la plage de la table de chaque module |

Fichiers touchés : 18, la liste est produite par le contrôle `sdk-patches`
(`nix/checks.nix`). **Aucun ne concerne le chargement ou le déchiffrement des XEX**
(`src/filesystem/xex.cpp`, `src/kernel/xex_module.cpp`, `thirdparty/excrypt`) : le
contrôle échoue sinon, et il est d'abord essayé sur un correctif synthétique de
`xex.cpp`, qu'il doit refuser.

**Provenance** : correctif 0003 du projet A (BSD 3-Clause), notice dans
`THIRD_PARTY.md`. Repris du projet A : la clé, son passage au runtime et le contrôle des
chevauchements deux à deux. Le passage de la base pour un module chargé ensuite
(`src/kernel/module_registry.cpp`) figurait dans le correctif 0002 du projet A ; il est
séparé ici, comme le demandait A2 (`docs/J2_A2_SDK_PATCHES.md` §3.2). Rien d'autre de
0002 n'est repris. Ajouté ici : plages sur 64 bits, contrôle face à sa propre
image, allocation exclusive, validation de la clé, tests.

### 5.2 Comportement sans la clé [V]

- Base : `image_base + image_size`, comme en amont. Le code généré calcule la même
  adresse, sous un autre nom (`REX_FUNC_TABLE_BASE`).
- Contrôle des chevauchements : comparer deux à deux l'image et la table de chaque
  module revient à comparer leurs unions, contiguës quand la table suit l'image. Le
  résultat est donc celui de l'amont, sauf débordement au-delà de 4 Gio, désormais
  détecté.
- Une taille ou une plage qui ne tient pas en 32 bits est désormais refusée, au lieu de
  revenir à une petite valeur. Pour des tailles valides, rien ne change.
- L'allocation exclusive ne s'applique qu'à une table déplacée.
- Les tests de l'amont passent toujours (§5.3).

### 5.3 Tests

Tous tournent sur des images et une mémoire synthétiques.

| Test | Montre que |
|---|---|
| `InitializeFunctionTable places the table at table_base` | la table est à la base donnée, et une fonction enregistrée y est lue |
| `A default table that runs into the next image is refused` | sans déplacement, le cas de ce disque est refusé : table de `(0x80000 + 0x10000) × 2` octets après une image de `0x1F0000`, image suivante `0x110000` plus loin |
| `A table moved with table_base lets the next image load` | le même cas passe une fois la table déplacée |
| `A table that overlaps another table or its own image is refused` | les deux chevauchements sont refusés |
| `A moved table is refused on pages that are already reserved` | une table déplacée sur une page occupée est refusée, et la page garde son contenu ; la même table passe sur des pages libres |
| `A page reserved by another thread just before a moved table is allocated is kept` | **concurrence, de façon déterministe** (P-38) : au point d'injection, juste avant l'allocation, un autre fil réserve une page de la plage, puis il est attendu (`join`). La table est refusée ; la page garde son propriétaire et son contenu ; aucune page de la plage n'est prise. Avec la première version (vérification, puis allocation), cette page aurait été reprise et effacée |
| `An exclusive fixed allocation takes no page when one page is reserved` | `AllocFixedExclusive` sur quatre pages, dont la dernière est réservée : échec, les trois pages libres le restent, la page réservée garde son propriétaire et son contenu ; sur les seules pages libres, l'allocation réussit |
| `A moved table is released when it is destroyed` | la table déplacée est rendue au tas quand elle est détruite |
| `A table or code range that does not fit is refused` | P-39 : une taille de table au-delà de 4 Gio est refusée par la mémoire invitée et par le répartiteur, sans rien allouer (en 32 bits, elle serait revenue à `0x20000`) ; une fin au-delà du tas et un code au-delà de 4 Gio sont refusés ; le même module, de taille valide, est accepté |
| `Without function_table_base the table follows the image` | sans la clé, l'en-tête généré place la table après l'image, et la recherche passe par `REX_FUNC_TABLE_BASE` |
| `function_table_base moves the table` | la clé est reportée dans l'en-tête et dans l'initialisation générés |
| `A function_table_base that is not 64 KiB aligned is refused` | la génération échoue |
| `A function_table_base outside the 0x80000000 heap is refused` | la génération échoue pour `0x70000000`, `0x90000000` et `0x100000000` |

Résultats : voir §8.

## 6. Contraintes sur `function_table_base`

| N° | Contrainte | Vérifiée par |
|---|---|---|
| T-1 | Alignée sur 64 Kio, la taille des pages de `v80000000` | La génération de code ; `AllocFixed` à l'exécution |
| T-2 | Début dans `0x80000000-0x8FFFFFFF` | La génération de code |
| T-3 | Fin, `base + (code_size + 0x10000) × 2`, au plus `0x90000000` | L'exécution seulement, sur 64 bits, avant toute allocation : la génération ne vérifie pas la fin |
| T-4 | Aucun chevauchement avec une image ou une table de module recompilé, y compris la sienne | Le runtime, à l'enregistrement de chaque module |
| T-5 | Pages libres au moment de l'allocation : zone de démarrage `0x80000000-0x8003FFFF`, images déjà chargées, autres allocations, y compris celles d'un autre fil | Le runtime, pour une table déplacée, par l'allocation exclusive (§4.2) |
| T-6 | Plage encore libre quand un module est chargé **après** la table | Le chargeur des XEX (`src/kernel/xex_module.cpp:221-229`) : erreur explicite au chargement |

Chaque violation de T-1 à T-6 produit une erreur explicite au démarrage du titre ou au
chargement du module [V code ; tests §5.3 pour T-1 à T-5]. Une seule
exception, hors du correctif : une allocation que l'invité ferait **après** la table, à
une adresse qu'il impose (§9).

## 7. Application au disque de l'utilisateur

Soient `c_def` et `c_dll` les tailles de code de `default.xex` et de `fifadllzf.xex`.
Elles se lisent dans l'image décodée, pas dans les en-têtes en clair : elles sont
**inconnues** en phase A [I]. Elles sont au plus égales à la taille de chaque image.

| Cas | Calcul | Conclusion |
|---|---|---|
| Table de `default.xex` par défaut | `0x821F0000 + (c_def + 0x10000) × 2 > 0x82300000` équivaut à `c_def > 0x78000` | Collision si le code dépasse `0x78000` octets [I] |
| Table de `fifadllzf.xex` par défaut | Au plus `(0x1850000 + 0x10000) × 2 = 0x30C0000` octets à partir de `0x83B50000`, donc fin au plus à `0x86C10000` | Elle tient toujours dans le tas [V calcul] |
| Table de `default.xex` à `0x86100000` (projet A) | Elle suit la table de `fifadllzf.xex` si `0x83B50000 + (c_dll + 0x10000) × 2 ≤ 0x86100000`, soit `c_dll ≤ 0x12C8000` | Valable seulement sous cette condition [I] |
| Table de `default.xex` à `0x86C10000` | Au-delà de la fin maximale de la table de `fifadllzf.xex`. Fin au plus à `0x86C10000 + 0x400000 = 0x87010000` | Valable quelles que soient `c_def` et `c_dll`, sous T-5 [V calcul ; [I] allocations du jeu] |

L'arrondi des tables à 64 Kio ne change pas ces bornes : `0x30C0000` et `0x25B0000` en
sont des multiples [V calcul].

**Proposition pour la phase B** [H], à arbitrer :
1. à la première génération de code, relever `c_def` et `c_dll` dans le code généré
   (`REX_CODE_SIZE`), qui reste privé. Ce ne sont que deux tailles, partageables après
   relecture (CP-5) ;
2. fixer `function_table_base` de `default.xex` à `0x86C10000`, ou à une valeur plus
   serrée tirée de `c_dll`. Ne pas reprendre `0x86100000` sans le calcul ci-dessus ;
3. au premier lancement, au niveau *debug*, vérifier les plages de tables du journal.

La valeur entre dans la configuration privée de la phase B, pas dans le gabarit A5, qui
exclut les adresses (`docs/J2_PLAN.md` §3.5).

## 8. Résultats de la construction

Construction : `nix build .#rexglue-sdk`, qui applique le correctif puis lance les tests
du SDK.

Construction locale du 2026-11-23, dans le conteneur de Claude Code, sans données du
jeu.

Résultats sur le correctif corrigé pour P-38 et P-39 (13 tests) :

| Vérification | Résultat |
|---|---|
| Application du correctif | Les 18 fichiers sont corrigés sans décalage ni rejet |
| Compilation du SDK en Release et en Debug, avec `-Werror` | Réussie |
| Tests du SDK en Release (CTest) | **2 236 tests : 2 226 réussis, 10 sautés, 0 échec**. Les 10 sautés le sont aussi sans le correctif : tests d'ordre des verrous, réservés au mode Debug, et deux tests propres à l'hôte |
| Tests du SDK en Debug | **2 247 tests : 2 245 réussis, 2 sautés (propres à l'hôte), 0 échec** |
| Les 13 tests du correctif (§5.3) | Tous réussis, en Release et en Debug |
| Contrôle `sdk-patches` | Réussi : 18 fichiers listés, aucun des XEX ni du déchiffrement ; le correctif synthétique de `xex.cpp` est refusé |
| `nix flake check -L --no-update-lock-file` | « all checks passed! », dont `private-guard-selftest` (50 tests) |

La version précédente, avec 9 tests, avait aussi passé ces vérifications (2 232 tests en
Release, 2 243 en Debug).

Le journal CTest et le rapport JUnit sont installés avec le SDK, sous
`share/rexglue-sdk/test-results/`.

## 9. Limites

- Les tailles de code des deux modules, donc le besoin réel du déplacement, ne sont
  connues qu'en phase B [I].
- Les allocations que le jeu ferait lui-même dans `v80000000` ne sont connues qu'à
  l'exécution [I] :
  - si elles précèdent la table, le contrôle T-5 les protège ;
  - sans adresse imposée, elles vont dans un autre tas (§4.1) ;
  - à une adresse imposée **après** la table, rien ne les contrôle : avec réservation et
    engagement, elles reprendraient des pages de la table (§4.2) [V code]. L'amont se
    comporte de même pour les images. Ce cas n'est pas traité par le correctif.
- Le correctif ne change pas la taille de la réserve de *thunks* (`0x10000`).
- La structure `PPCImage` gagne un champ : tout code généré doit être compilé avec le SDK
  corrigé. C'est déjà le cas, puisque le code est généré et compilé par le SDK de ce
  dépôt.
- La fin de la table n'est pas vérifiée à la génération du code (T-3). Une table qui
  sortirait du tas échoue au démarrage, avec une erreur.
- La reprise après un échec de synchronisation des droits de l'hôte (§4.2) n'est pas
  testée : aucun moyen synthétique ne fait échouer cette étape. Elle est vérifiée par
  lecture du code seulement.
- Le point d'injection pour les tests est un membre public de `GuestAddressSpace`. Il
  reste vide hors des tests ; rien dans le SDK ne le renseigne.

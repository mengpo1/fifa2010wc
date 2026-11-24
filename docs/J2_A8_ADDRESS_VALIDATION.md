# J2, étape A8 — Méthode de validation des adresses : comparaison des pistes

> Étape A8 de `docs/J2_PLAN.md` (§3.8), sous l'autorisation PA-0 (D-015). **Phase A :
> aucune donnée du jeu**, et **aucune piste n'est exécutée**.
> **Arbitrage (2026-11-23, revue 6021690700)** :
> - M1 est la méthode de première analyse, et M3 le repli de recherche ;
> - M2 n'est pas autorisée ;
> - l'étape A8-bis, purement analytique, est autorisée en phase A (§4).
>
> **M1 n'est pas une validation intégrale des adresses** : les valeurs de données restent
> non vérifiées (§3, niveaux de preuve).
> Arbitrage du ticket #14 (D-015) :
> - la priorité va aux diagnostics, aux sorties et aux interfaces existants de ReXGlue ;
> - aucun programme nouveau produisant une image décodée n'est autorisé implicitement.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Ce qu'il faut valider

La configuration du projet A ne vaut que pour le code de son disque. Les empreintes du
disque de l'utilisateur diffèrent ; sa disposition en mémoire concorde, ce qui est une
condition nécessaire, pas suffisante (`docs/J2_PREREQUISITES.md` §3).

| Élément | Volume | Nature | Méthode du projet A |
|---|---|---|---|
| Débuts de fonctions « autofix » | Dans `default.toml` et `fifadllzf.toml` | Code | `autofix_codegen.py` : générer, puis ajouter une graine à chaque erreur « cible hors fonction » |
| Pointeurs de code | 663 et 17 028 lignes | Code atteint par des pointeurs | `find_code_pointers.py` : balayer les sections de données et les paires `lis`/`addi` |
| `setjmp`, `longjmp` | 2 adresses | Code de la bibliothèque C | `find_setjmp.py` : la forme des instructions |
| `boot_fixes.cpp` | Une fonction, un pointeur de registre en `0x83A4648C`, un emplacement `0x64` | Code **et données** | Lecture du désassemblé |
| `lua_diagnostics.cpp` | `luaD_throw`, et les décalages de `lua_State` (`0x70`, `0x08`…) | Code **et disposition de structures** | Lecture du désassemblé |
| `function_table_base` | 1 valeur | Disposition, et non adresse du code | Étape A3 |

[V] Tous ces outils, sauf `disc.py` et `xexinfo.py`, chargent l'image par
`xeximage.load`, qui déchiffre. Ce chargement est exclu (`docs/J2_PREREQUISITES.md` §3.3).

## 2. Ce que fournit ReXGlue, d'après l'inventaire A1

Références : `docs/J2_A1_SDK_INVENTORY.md` §5.

- **Erreurs** : `UnresolvedCall` et `Millicode`, sous la forme `0xCIBLE from 0xSITE`. La
  génération s'arrête avant d'écrire.
- **Listes d'adresses** :
  - `kPPCFuncMappings` donne chaque fonction générée ;
  - `codegen.partition.json` donne une adresse par fonction.
- **Avertissements par entrée `[functions]`** : « not a function entry point »,
  « outranked by », « split by », « not in any code region », « no blocks found ».
- **Désassemblée** : chaque instruction est en commentaire dans le code généré, qui reste
  privé.
- **Limites** :
  - le code généré n'embarque pas les données ;
  - `setjmp` et `longjmp` ne sont contrôlés que pour leur alignement ;
  - une adresse au milieu d'une fonction n'est pas contrôlée explicitement.

## 3. Les pistes

### M1 — Diagnostics et sorties de ReXGlue (méthode de première analyse)

Tout se passe sur la machine de l'utilisateur, dans le dossier privé, sous les contrôles
CP. Les outils de comparaison à écrire lisent seulement des listes d'adresses et la
désassemblée en commentaire du code généré. Ils ne produisent ni image, ni code, ni
donnée du jeu dans le dépôt.

#### Niveaux de preuve

| Niveau | Ce qu'il établit | Ce qu'il n'établit pas |
|---|---|---|
| **N0 — accepté syntaxiquement** | ReXGlue lit l'entrée sans erreur de configuration : clé, alignement, absence de chevauchement | Que l'adresse désigne du code |
| **N1 — adresse de code plausible** | ReXGlue ne signale rien pour l'entrée (§2) : elle est dans une région de code, des blocs y sont trouvés, et elle n'est ni dépassée ni coupée. Ou bien la génération sans la configuration la découvre d'elle-même | **Qu'un pointeur des données du disque désigne réellement cette adresse.** Une entrée acceptée sans avertissement n'est pas une preuve que ce pointeur existe |
| **N2 — référence d'instruction vérifiée** | La désassemblée à l'adresse, ou les instructions qui y font référence, correspondent à la séquence attendue : forme de `setjmp`, séquence décrite par le correctif, immédiats `lis`/`addi`, déplacements `lwz`/`stw` | La valeur ni le contenu des données désignées |
| **N3 — valeur ou contenu de données non vérifié** | Rien : c'est l'état de toute valeur de données, puisque ni ReXGlue ni M1 ne lisent les données | — |

#### Procédés et niveau atteignable

| Élément | Procédé | Niveau atteignable [H] |
|---|---|---|
| Débuts de fonctions « autofix » | (a) Générer **sans** la configuration du projet A, et relever les adresses découvertes. (b) Générer **avec** elle, puis relever les avertissements par entrée et C2.1. (c) Comparer les deux listes aux entrées du projet A | **N1**. Une entrée signalée est écartée, puis réanalysée |
| Pointeurs de code, 663 et 17 028 entrées `[functions]` | Même procédé (A1 §5.3) | **N1 au mieux.** L'existence du pointeur dans les données reste **non vérifiée** (N3) |
| Erreurs restantes | Reprendre la méthode d'`autofix_codegen.py` sans image : une graine par erreur `UnresolvedCall`, et ReXGlue trouve les bornes | **N1** pour chaque graine ajoutée |
| `setjmp`, `longjmp` | Comparer la désassemblée des deux adresses à la forme décrite par `find_setjmp.py` : r3, registres non volatils, LR et CR enregistrés ou rechargés | **N2** |
| Crochet de `boot_fixes.cpp` et `luaD_throw` | Comparer la désassemblée de la fonction accrochée aux séquences décrites dans les commentaires du projet A | **N2** pour le code |
| Pointeur de registre `0x83A4648C`, emplacement `0x64`, décalages de `lua_State` | Retrouver dans la désassemblée les instructions qui chargent ces adresses et ces décalages | **N2** pour la référence ; **N3** pour la valeur et la disposition des données |

#### Ce que M1 ne permet pas de conclure

- **M1 n'est pas une validation intégrale des adresses.** Elle ne valide pas les
  pointeurs issus des données, la valeur du registre `0x83A4648C`, ni la disposition de
  `lua_State`. Ces éléments restent au niveau N3, **non vérifiés**.
- Une adresse fausse peut rester silencieuse, ou corrompre la mémoire sans plantage
  visible. L'exécution à J3 n'est donc pas une validation.
- Aucun résultat de M1 ne permet de dire « identique au projet A », ni de publier une
  validation totale.
- Les résultats dépendent du format des commentaires du code généré.

**Ce qui reste à faire avant la phase B** : l'outil de comparaison de l'étape A8-bis
(§4), avec ses tests sur des listes et une désassemblée **synthétiques**. Le format des
sorties est connu par les gabarits du SDK. Ce travail ne demande aucune donnée du jeu.

### M2 — Image produite par un programme du projet, à partir du SDK (dérogation)

- **Principe** : un programme du projet appelle le décodage de ReXGlue et écrit l'image
  décodée dans le dossier privé. Les outils du projet A, adaptés pour lire cette image
  plutôt que `xeximage.load`, s'appliquent alors tels quels.
- **Couverture** : complète, y compris les données.
- **Ce qu'elle demande** :
  - **une dérogation explicite** à la contrainte reformulée de D-008, puisque le projet
    produirait lui-même une image décodée ;
  - une image en clair sur le disque, en plus de `/dev/shm` ;
  - une révision de R-01 et de R-07.
- **Non autorisée** (arbitrage de la revue 6021690700). Toute méthode qui produit une
  image décodée reste exclue sans décision distincte.

### M3 — Nouvelle analyse avec ReXGlue seul

- **Principe** : générer sans la configuration du projet A, puis traiter les erreurs une
  à une, avec la méthode « autofix » sans image de M1.
- **Correctifs du jeu** : on retrouve les fonctions de `boot_fixes.cpp` et de
  `lua_diagnostics.cpp` dans la désassemblée.
- **Coût** : de quelques jours à quelques semaines [H] (`docs/J2_PREREQUISITES.md` §5).
- **Couverture, restreinte** : elle repose sur ReXGlue seul, qui ne fournit pas les
  données. Elle atteint au mieux N1 pour les débuts de fonctions, et N2 pour le code des
  correctifs. Elle a **les mêmes limites que M1** pour les pointeurs issus des données et
  les adresses de structures, qui restent N3.
- **Usage** : c'est la voie de repli de recherche de M1. Si elle ne peut pas lever les
  inconnues d'un élément nécessaire, c'est un **point d'arrêt** (§4).

### Écartée — `xeximage.py`

Il déchiffre avec une clé écrite en dur (D-008, D-010).

## 4. Arbitrage et suite

**Arbitrage de l'orchestrateur** (revue 6021690700 de la PR #18, 2026-11-23) :
- **M1** est retenue comme méthode de première analyse ;
- **M3** est le repli de recherche ;
- **M2 n'est pas autorisée** ;
- **l'étape A8-bis est autorisée en phase A**, à condition d'être purement analytique.
  Elle compare des listes et des annotations, ses tests tournent en CI sans ISO ni XEX, et
  le projet n'émet ni décodage ni image déchiffrée. **Elle ne franchit pas PB-0 à elle
  seule.**

**Critères, par élément de la configuration du projet A** :

| Élément | Niveau exigé pour le reprendre | Sinon |
|---|---|---|
| Débuts de fonctions, graines « autofix » | N1, et C2.1 satisfait | Sortie propre au disque de l'utilisateur, puis M3 |
| Pointeurs de code | N1, noté « pointeur non vérifié dans les données (N3) » | Entrée écartée ; M3 pour la fonction concernée |
| `setjmp`, `longjmp`, code des crochets | N2 | Arrêt PB-2, puis M3 |
| Valeurs de données : registre `0x83A4648C`, emplacement `0x64`, décalages de `lua_State` | N2 pour la référence. La valeur reste **N3, non vérifiée**, et est notée comme telle | Arrêt (ci-dessous) |

**Cas d'arrêt à l'étape B3** :
- un élément nécessaire au démarrage reste au niveau N0 ;
- une référence attendue (N2) est introuvable, ou diffère de la séquence décrite ;
- M3 ne lève pas l'inconnue d'un élément nécessaire.

Dans ces cas, on suspend et on consigne. Une **analyse complémentaire** est soumise à une
décision distincte du porteur du projet et de l'orchestrateur ; ce n'est jamais M2 sans
dérogation explicite. Les valeurs de données N3 nécessaires au correctif de démarrage
relèvent de cette décision, avant J3.

**Exigences pour l'étape A8-bis** :
- l'outil compare des listes d'adresses, des avertissements et des annotations de
  désassemblée ;
- il ne lit ni image, ni XEX, ni données du jeu ;
- ses tests sont **synthétiques** et couvrent les faux positifs :
  - adresse présente dans la configuration mais non découverte ;
  - décalage de données invalide ;
  - collision de fonctions ;
  - absence de diagnostic ;
  - erreur de format de la sortie ;
- il ne produit que des **rapports agrégés** : nombres et niveaux par élément. La
  désassemblée et le code généré restent locaux, dans le dossier privé ;
- il ne versionne au plus que des adresses et des métadonnées, après PB-3. Jamais de
  désassemblée ni de code généré (D-007).

*A8-bis (2026-11-23) : `tools/address_compare.py`, décrit dans
`docs/J2_A8BIS_ADDRESS_COMPARE.md`. Les faux positifs ci-dessus ont chacun leur test.
Limite : N2 n'est pas calculé à partir du code généré, dont les commentaires
d'instruction ne portent pas d'adresse ; il vient d'un relevé d'examen manuel.*

# J2, étape A8 — Méthode de validation des adresses : comparaison des pistes

> Étape A8 de `docs/J2_PLAN.md` (§3.8), sous l'autorisation PA-0 (D-015). **Phase A :
> aucune donnée du jeu**, et **aucune piste n'est exécutée**. Cette note prépare la
> décision de méthode. **La décision revient au porteur du projet et à l'orchestrateur**,
> avant PB-0.
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

### M1 — Diagnostics et sorties de ReXGlue (prioritaire)

Tout se passe sur la machine de l'utilisateur, dans le dossier privé, sous les contrôles
CP. Les outils de comparaison à écrire lisent seulement des listes d'adresses et la
désassemblée en commentaire du code généré. Ils ne produisent ni image, ni code, ni
donnée du jeu dans le dépôt.

| Élément | Procédé | Couverture |
|---|---|---|
| Débuts de fonctions | (a) Générer **sans** la configuration du projet A, et relever les adresses découvertes. (b) Générer **avec** elle, puis relever les avertissements par entrée et C2.1. (c) Comparer les deux listes aux entrées du projet A | **Bonne** [H]. Une entrée sans avertissement, découverte ou admise, avec C2.1 satisfait, est cohérente avec le code. Une entrée signalée est écartée, puis réanalysée |
| Pointeurs de code (entrées `[functions]`) | Même procédé : ce sont des entrées `[functions]` (A1 §5.3) | **Partielle** [H]. ReXGlue vérifie qu'une entrée est du code et un début de fonction plausible. Il ne vérifie pas qu'un pointeur des données la désigne |
| Erreurs restantes | Reprendre la méthode d'`autofix_codegen.py` sans image : une graine par erreur `UnresolvedCall`, et ReXGlue trouve les bornes | **Bonne** [H]. Le projet A ne lit l'image que pour estimer la taille d'une fonction (recherche de `blr`/`bctr`) |
| `setjmp`, `longjmp` | Comparer la désassemblée des deux adresses à la forme décrite par `find_setjmp.py` : r3, registres non volatils, LR et CR enregistrés ou rechargés | **Bonne** [H] |
| Crochet de `boot_fixes.cpp` et `luaD_throw` | Comparer la désassemblée de la fonction accrochée aux séquences décrites dans les commentaires du projet A | **Bonne pour le code** [H] |
| Pointeur de registre `0x83A4648C`, emplacement `0x64`, décalages de `lua_State` | Indirectement : retrouver dans la désassemblée les instructions qui chargent ces adresses et ces décalages (immédiats de `lis`/`addi`, déplacements de `lwz`/`stw`) | **Indirecte seulement** [H]. Le contenu des données n'est jamais lu |

**Ce qui reste à faire avant la phase B** : un outil de comparaison local, avec ses tests
sur des listes et une désassemblée **synthétiques**. Le format des sorties est connu par
les gabarits du SDK. C'est un travail de phase A, qui ne demande aucune donnée du jeu.

**Risques et limites** :
- validation indirecte des adresses de données ;
- dépendance au format des commentaires du code généré ;
- la cohérence n'est pas une preuve d'identité des images.

Ces limites suffisent au projet, au sens de `docs/J2_PREREQUISITES.md` §3.2 :
- une donnée mal placée se révèle à l'exécution, à J3, par un plantage ou un journal ;
- l'enveloppe de contrôle CP s'applique alors.

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
- **Non retenue par défaut.** Elle ne sert que si M1 et M3 échouent sur un point
  bloquant.

### M3 — Nouvelle analyse avec ReXGlue seul

- **Principe** : générer sans la configuration du projet A, puis traiter les erreurs une
  à une, avec la méthode « autofix » sans image de M1.
- **Correctifs du jeu** : on retrouve les fonctions de `boot_fixes.cpp` et de
  `lua_diagnostics.cpp` dans la désassemblée.
- **Coût** : de quelques jours à quelques semaines [H] (`docs/J2_PREREQUISITES.md` §5).
- **Usage** : c'est la voie de repli de M1 pour tout ce que la comparaison n'établit pas.

### Écartée — `xeximage.py`

Il déchiffre avec une clé écrite en dur (D-008, D-010).

## 4. Proposition

1. **Méthode retenue proposée : M1**, avec **M3 en repli** pour chaque élément que M1
   n'établit pas. M2 n'est envisagée qu'en cas d'échec bloquant, et par une décision de
   dérogation distincte.
2. **Avant PB-0**, écrire en phase A :
   - l'outil de comparaison de M1 ;
   - ses tests sur des données synthétiques ;
   - une procédure pour les étapes B2 et B3 de `docs/J2_PLAN.md`.

   Proposition : ce sera l'étape A8-bis, en PR séparée.
3. **Critère de validation** de chaque élément de la configuration du projet A :
   - débuts de fonctions et pointeurs : présents dans les découvertes de la génération
     sans la configuration, ou admis par la génération avec la configuration sans
     aucun avertissement, et C2.1 satisfait ;
   - adresses de code accrochées et `setjmp`/`longjmp` : la désassemblée correspond aux
     séquences attendues ;
   - adresses de données : les références dans la désassemblée concordent. L'élément est
     alors noté « validé indirectement » ;
   - tout écart : on garde la sortie propre au disque de l'utilisateur, et l'on
     réanalyse (M3).
4. **Ce qui est versionné** : au plus des adresses et des métadonnées, après PB-3. Jamais
   de désassemblée ni de code généré (D-007).

**Décision demandée** au porteur du projet et à l'orchestrateur :
- retenir M1, avec M3 en repli, et M2 exclue sauf dérogation ;
- autoriser l'étape A8-bis, qui écrirait l'outil de comparaison.

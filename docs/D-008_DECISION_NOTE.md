# Note de décision D-008 — Traitement des XEX chiffrés : O1, O2 ou O3

> Préparée le 2026-11-22 pour le ticket [#8](https://github.com/mengpo1/fifa2010wc/issues/8).
> **Ce n'est ni une décision, ni un avis juridique.** D-008 reste **ouverte et bloquante**
> pour C0.5 et J2. Cette note réunit les éléments d'une décision explicite de
> l'utilisateur.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.
>
> Méthode :
> - aucun fichier du jeu n'a été lu, demandé ni transmis ;
> - aucun déchiffrement, aucune génération de code, aucune exécution de ReXGlue sur des
>   données du jeu ;
> - les faits techniques viennent de la **lecture du code public** de ReXGlue v0.11.0,
>   à la révision épinglée par `flake.lock` (`a3e1d82`). Aucune valeur de clé n'est
>   reproduite ici ;
> - les textes juridiques **n'ont pas pu être relus** dans cette session : Légifrance a
>   refusé l'accès automatique et EUR-Lex n'a renvoyé que des pages vides. Les
>   références juridiques viennent du ticket #8 et de l'audit. Leur contenu exact reste à
>   vérifier par un juriste.

## 1. La question

Les deux modules du disque de l'utilisateur, `default.xex` et `fifadllzf.xex`, sont
chiffrés en AES et compressés en LZX [V] (`docs/reports/J0_IDENTIFICATION.md`).

- La génération de code de J2 a besoin de l'image en clair de ces deux modules.
- L'exécution du portage aussi, à chaque lancement [V] (§3.1).

Il faut donc choisir explicitement par quel chemin cette image en clair est obtenue, et à
quelles conditions, ou décider d'attendre :

| Option | Principe |
|---|---|
| **O1** | Attente d'un avis juridique. Aucun déchiffrement. C'est le chemin conservatoire actuel |
| **O2** | L'utilisateur fournit lui-même des XEX dont l'en-tête indique « non chiffré ». **Intention** : une voie où le projet n'utilise ni n'embarque de clé. **Ce n'est pas l'état actuel** : le SDK compilé par le flake contient déjà les clés et le code de déchiffrement (§3.4), et `Decode` dérive toujours une clé de session (§3.3). Un correctif du SDK reste nécessaire ; il n'est pas réalisé |
| **O3** | ReXGlue est utilisé tel quel. Il déchiffre lui-même, sur la machine de l'utilisateur, pour sa copie |

## 2. Ce que cette note ne tient pas pour acquis

Aucun des éléments suivants n'est traité comme une autorisation juridique suffisante :

- la **possession** du disque ou de l'ISO ;
- l'**usage personnel** ;
- le **caractère public des clés**. **[H]** Leur diffusion ne change probablement pas, à
  elle seule, la qualification d'une mesure technique (`ISO_REQUIREMENTS.md` §5) ;
- le fait que le déchiffrement se fasse **dans une dépendance** ou **sur la machine de
  l'utilisateur**. Cela n'en détermine pas la légalité (ticket #8).

## 3. Faits techniques, par lecture du code public

### 3.1 Un seul chemin de décodage [V]

Tous les chargements d'un module aboutissent à `XEXImage::Decode`
(`src/filesystem/xex.cpp`) :

| Moment | Chemin dans ReXGlue v0.11.0 |
|---|---|
| Lancement du portage : `game:\default.xex`, **à chaque lancement** | `TitleState::LoadXEXImage` → `ModuleObject::LoadFromFile` → `LoadFromMemory` → `XEXModule::Load` → `XEXImage::Decode` (`src/kernel/title_state.cpp`, `src/kernel/user_module.cpp`, `src/kernel/xex_module.cpp`) |
| Chargement de `fifadllzf.xex` par le jeu | `XexLoadImage` → `ModuleRegistry::LoadUserModule` → `ModuleObject::LoadFromFile` → même chemin (`src/kernel/xboxkrnl/xboxkrnl_xex.cpp`, `src/kernel/module_registry.cpp`) |
| Génération de code (`rexglue codegen`) | `ToolApp::Open` → `TitleRuntime::Load` → même chemin (`src/codegen/tool_runtime.cpp`, `src/codegen/codegen_context.cpp`). `ReadImageRange` lit en plus l'en-tête seul, sans décoder (`src/codegen/project_recompiler.cpp`) |
| Correctif de titre | Si un fichier `<module>p` (par exemple `default.xexp`) se trouve à côté d'un module, il est chargé et appliqué automatiquement (`src/kernel/user_module.cpp`) |

### 3.2 Ce que fait `XEXImage::Decode` [V]

1. Quatre clés maîtresses (« retail », « devkit », et leurs équivalents XEX1) sont
   définies en clair dans `src/filesystem/xex.cpp` (`kMasterKeys`).
2. Pour chacune, `Decode` :
   - dérive une clé de session : `DecryptKey` déchiffre, avec la clé maîtresse, la clé de
     fichier de l'en-tête (`aes_key`) ;
   - appelle `DecodeWith` :
     - type de chiffrement 1 : les données sont déchiffrées en AES-CBC avec la clé de
       session ;
     - type 0 : elles sont copiées sans déchiffrement ;
     - puis la décompression s'applique (aucune, basique ou LZX), avec la vérification
       des empreintes des blocs LZX ;
   - accepte le résultat s'il commence par l'en-tête d'un exécutable PE.
3. En cas d'échec avec toutes les clés, le chargement échoue (« tried both encryption
   keys »).

Autres constats :

- **[V]** Au chargement, ReXGlue ne vérifie **ni la signature RSA, ni les empreintes
  d'en-tête et de pages** du module. Le SHA-1 de la signature sert seulement à
  vérifier qu'un correctif `.xexp` s'applique au bon module.
- **[V]** Les exports cryptographiques du noyau émulé (`XeCrypt*`,
  `src/kernel/xboxkrnl/xboxkrnl_crypt.cpp`) sont des primitives que le jeu peut appeler
  pour ses propres besoins. Ils sont distincts du déchiffrement des XEX.
- **[V]** Sur 67 fonctions `XeKeys*`, 61 sont des bouchons. Six sont implémentées :
  `XeKeysHmacSha`, `XeKeysHmacShaUsingKey`, `XeKeysAesCbcUsingKey`, `XeKeysObscureKey`,
  `XeKeysConsolePrivateKeySign` et `XeKeysConsoleSignatureVerification`.
  - **[H]** Elles servent au jeu lui-même, par exemple pour signer ses sauvegardes.
  - **[I]** Le matériel de clé qu'elles utilisent éventuellement n'a pas été examiné.
    C'est une question distincte de D-008, à rattacher à l'acte 4 (§5).
- **[H]** D'après les chemins lus, l'image en clair n'existe qu'en mémoire. Aucune
  écriture de l'image sur disque n'a été trouvée dans `src/codegen`, mais cette lecture
  n'est pas exhaustive. En revanche, le **C++ généré**, traduction du code du jeu,
  persiste dans le dossier privé (`generated/`, D-007), sous O2 comme sous O3.

### 3.3 Faisabilité technique d'O2

| Point | Constat |
|---|---|
| Un module dont l'en-tête indique « non chiffré » est-il accepté ? | **[V]** Oui par lecture : `DecodeWith` traite le type 0 avec les trois compressions. **Non vérifié par exécution** |
| Un en-tête réécrit par un outil tiers serait-il rejeté ? | **[H]** Non pour sa signature ou ses empreintes, qui ne sont pas vérifiées (§3.2). Il doit rester cohérent : compression, empreintes des blocs LZX, image PE |
| O2 est-il « sans clé » avec ReXGlue tel quel ? | **[V] Non.** `Decode` dérive toujours une clé de session avec la première clé maîtresse, même pour un module non chiffré |
| Peut-on rendre O2 sans clé côté projet ? | **[H]** Oui, par un correctif de la série du projet (D-011). Il sauterait la boucle des clés quand le type de chiffrement vaut 0 ; c'est quelques lignes dans `Decode`. **Non écrit, non testé** |
| Peut-on retirer les clés du SDK ? | **[H]** Oui, par un correctif plus large qui supprimerait `kMasterKeys` et la branche chiffrée. `MasterKey` et `DecryptKey` ne servent que dans `xex.cpp`. Le SDK ne saurait alors plus charger un XEX chiffré. ExCrypt resterait nécessaire pour les primitives `XeCrypt*` |
| Où vivraient les XEX non chiffrés ? | **[V]** Dans le dossier privé, en permanence, car le runtime les recharge à chaque lancement (§3.1). Ce sont des fichiers dérivés du jeu, couverts par D-007 |
| D'où viendraient-ils ? | **[I]** Aucune source de modules non chiffrés n'est connue. **[H]** En pratique, seul un outil tiers de déchiffrement appliqué par l'utilisateur à sa copie les produirait. O2 ne supprime donc pas l'acte de déchiffrement : il le déplace hors du projet |
| Comment vérifier O2 sans données du jeu ? | Proposition, **non réalisée** : un module XEX2 synthétique non chiffré, contenant une petite image PE, chargé par ReXGlue dans un test. C'est la même méthode que les tests de J0. À faire seulement après la décision |

### 3.4 État du projet, quelle que soit l'option [V]

- Le dépôt ne contient ni clé ni code de déchiffrement écrit par le projet
  (engagement de D-008).
- Le projet n'a exécuté aucun déchiffrement. J0 lit seulement les en-têtes en clair.
- **Le SDK compilé par le flake depuis J1 contient le code de déchiffrement des XEX et
  ses clés maîtresses.** `xex.cpp` est compilé dans `librexfilesystem.so`
  (`src/filesystem/CMakeLists.txt`). C'est déjà vrai sous O1, sur la machine de
  l'utilisateur et sur les machines de la CI.
- Le projet ne publie aucun binaire : la CI ne publie que des journaux et des rapports
  (`.github/workflows/ci.yml`), et aucun cache binaire n'est alimenté.
- **[I]** La qualification d'une recette (le flake) qui télécharge et compile une
  dépendance contenant ces clés est à poser au juriste (§5, acte 4).

## 4. Les trois options comparées

### 4.1 Angle juridique

| | O1 | O2 | O3 |
|---|---|---|---|
| Acte de déchiffrement | Aucun | Oui, par l'utilisateur, avec un outil tiers, hors du projet, une fois | Oui, par la dépendance, sur la machine de l'utilisateur, à la génération de code et à **chaque lancement** |
| Qui l'accomplit | — | L'utilisateur | L'utilisateur, au moyen de la chaîne du projet |
| Copie déchiffrée persistante | Non | **Oui** : les XEX non chiffrés, dans le dossier privé | Non pour l'image (en mémoire, [H]) ; le C++ généré persiste |
| Recompilation, c'est-à-dire traduction du code (acte 2) | Non | Oui | Oui |
| Contrainte de mission « ne pas engager de contournement » | Respectée | **[H]** respectée à la lettre par le projet, mais l'acte a lieu chez l'utilisateur | **Contraire à la lettre**, sauf requalification explicite par l'orchestrateur (ticket #8) |
| Ce qui reste à qualifier | Acte 4 | Actes 1 à 4 (§5) | Actes 1 à 4 (§5) |

**[I]** Aucune option n'est qualifiée juridiquement par cette note. Le déplacement de
l'acte de déchiffrement (vers l'utilisateur avec O2, vers la dépendance avec O3) ne
tranche rien à lui seul.

### 4.2 Angle technique

| | O1 | O2 | O3 |
|---|---|---|---|
| Génération de code (J2) | Impossible | Possible d'après le code [V], non vérifiée par exécution | Possible : chemin standard de ReXGlue, pratiqué par les projets A et B [V audit] |
| Clés utilisées par la chaîne du projet | Aucune n'est utilisée, mais elles sont présentes dans le SDK (§3.4) | **Oui, sauf correctif** : dérivation de la clé de session (§3.3) | Oui |
| Travail technique à prévoir | Aucun | Correctif « sans clé » [H], test synthétique, procédure d'entrée | Aucun propre à D-008 |
| Fiabilité | — | Dépend de l'outil tiers et de la cohérence de l'en-tête réécrit [H] | Celle de ReXGlue |

### 4.3 Angle opérationnel

| | O1 | O2 | O3 |
|---|---|---|---|
| Avancement | J2 bloqué pour la génération de code. Les préparations sans données du jeu (`J2_PREREQUISITES.md` §6) restent possibles si l'orchestrateur ouvre J2 | J2 possible après la décision et le correctif éventuel | J2 possible après la décision et la requalification |
| Charge pour l'utilisateur | Obtenir un avis juridique (délai et coût [I]) | Se procurer et utiliser lui-même un outil tiers. Le projet ne peut ni le fournir ni, peut-être, le documenter [I]. Conserver des XEX déchiffrés | Aucune étape propre |
| Reproductibilité | — | Plus faible : dépend d'un outil et d'une manipulation extérieurs | Celle du flake |
| Hygiène des données (D-007) | Inchangée | Un fichier dérivé de plus à protéger : les XEX déchiffrés | Inchangée ; le C++ généré reste à protéger, comme sous O2 |

## 5. Actes à faire qualifier séparément

Comme le demande le ticket #8, chaque acte se qualifie à part. Ce sont des questions
pour un juriste du pays où les opérations ont lieu, pas des réponses :

| N° | Acte | Options concernées | Question à poser |
|---|---|---|---|
| 1 | **Déchiffrement local** des modules : en mémoire à chaque chargement (O3), ou une fois par un outil tiers (O2) | O2, O3 | Le chiffrement des XEX est-il une mesure technique au sens applicable : logiciel (directive 2009/24/CE) ou œuvre complexe (directive 2001/29/CE, CJUE C-355/12) ? Le déchiffrement par l'utilisateur légitime d'une copie qu'il possède est-il permis, et sous quelles conditions ? Le régime diffère-t-il selon que l'outil est fourni par un tiers (CPI R.335-3 à examiner) ? |
| 2 | **Recompilation statique** : traduction du code du jeu en C++, puis compilation en exécutable natif | O2, O3 | La traduction et l'adaptation sont des actes réservés à l'auteur d'un logiciel (CPI L.122-6 [H]). L'exception de décompilation pour l'interopérabilité (L.122-6-1 IV, art. 6 de la directive 2009/24) couvre-t-elle un port complet d'un programme existant ? Le ticket #8 relève des conditions strictes : créer un logiciel indépendant, information non accessible autrement, actes limités au nécessaire [H] |
| 3 | **Distribution** éventuelle d'un port : binaire, code généré, correctifs propres au jeu | Toutes | Exclue aujourd'hui (D-007). À qualifier seulement si elle est un jour envisagée |
| 4 | **Clés et outil de déchiffrement** : le dépôt n'en contient pas, mais le flake télécharge et compile une dépendance qui en contient (§3.4) | Toutes, dès J1 | Fournir une recette de compilation d'une dépendance qui contient des moyens de neutralisation pose-t-il problème (art. 7(1)(c) de la directive 2009/24, CPI L.122-6-2 et L.335-3-1 à examiner) ? |

Éléments à documenter avec la décision, sans les tenir pour des autorisations (§2) :

- **[I]** le pays où les opérations ont lieu ;
- **[I]** le périmètre : usage personnel seul, ou partage, ou distribution ;
- **[I]** le fondement de l'acquisition et de la licence du jeu.

## 6. Repères juridiques, non relus dans cette session

Ces références viennent de la recherche préliminaire du ticket #8 et de l'audit
(`ISO_REQUIREMENTS.md` §5). Elles ne sont reprises ici que comme pistes :

- **CPI L.122-6-1**, décompilation pour l'interopérabilité :
  [Légifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000044365559) ;
- **CPI L.331-5**, mesures techniques des œuvres autres que les logiciels. Selon le
  ticket, un protocole ou un algorithme n'est pas en lui-même une mesure technique :
  [Légifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000044259273) ;
- **CPI L.335-3-1** et **R.335-3**, atteintes aux mesures techniques et moyens de les
  neutraliser :
  [L.335-3-1](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006279236),
  [R.335-3](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006280050) ;
- **Directive 2009/24/CE**, art. 4 à 7 :
  [EUR-Lex](https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32009L0024) ;
- **Directive 2001/29/CE**, art. 6, et son articulation avec la directive 2009/24 :
  [EUR-Lex](https://eur-lex.europa.eu/eli/dir/2001/29/oj?locale=fr) ;
- **CJUE, 23 janvier 2014, C-355/12, *Nintendo c/ PC Box*** : jeux vidéo comme œuvres
  complexes, protection des mesures techniques sous réserve de proportionnalité :
  [EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62012CJ0355).

**[I]** Quel régime de mesures techniques s'applique : celui des logiciels ou celui des
œuvres ? Cela dépend de la qualification du jeu et de sa protection. Cette question
conditionne toutes les autres.

## 7. Synthèse

- **O1** ne demande aucun acte de contournement. Il bloque la génération de code, mais
  pas les travaux sans données du jeu. La seule question juridique qui subsiste est
  l'acte 4, déjà posée depuis J1.
- **O2** n'est **pas une voie sans clé** avec ReXGlue tel quel (§3.3). Il ne supprime
  pas l'acte de déchiffrement : l'utilisateur l'accomplit lui-même, avec un outil tiers,
  et en garde le résultat sur disque. Il demanderait un correctif et un test synthétique.
  Sa faisabilité n'est établie que par lecture du code.
- **O3** est techniquement le plus simple et le mieux éprouvé. Il est contraire à la
  lettre de la contrainte de mission sans requalification explicite. Ses actes 1 et 2
  sont à qualifier comme ceux d'O2.
- Quelle que soit l'option, la **recompilation elle-même** (acte 2) est un acte à
  qualifier, distinct du déchiffrement.

**Ce que cette note conclut** : aucun élément technique ne justifie, à lui seul, de
quitter O1 avant qu'un avis juridique ait qualifié les actes 1 à 4. Si l'incertitude
demeure, le ticket #8 prévoit de **conserver O1**. Cette note ne prend pas la décision.

## 8. Ce que la décision devra consigner

À reporter dans D-008 (`docs/DECISIONS.md`) au moment de la décision, et seulement à ce
moment :

1. **L'option choisie** : O1, O2 ou O3. Pour O2 : avec ou sans le correctif « sans clé »
   (§3.3). Pour O3 : la requalification explicite de la contrainte « ne pas engager de
   contournement », par l'orchestrateur.
2. **Le pays** des opérations, le **périmètre** (personnel, partage, distribution) et le
   **fondement** de l'acquisition et de la licence. Ils sont documentés, mais ne tiennent
   pas lieu d'autorisation.
3. **L'avis juridique** : obtenu ou non, sa date, les actes qu'il qualifie (§5, actes 1
   à 4). Il n'est pas nécessaire d'en publier le contenu ni l'auteur.
4. **Les conditions et réserves** retenues, et les **limites de diffusion** : par défaut,
   rien du jeu ni du code généré n'est diffusé (D-007).
5. **Le point de contrôle avant J2** :
   - relecture de la décision par l'orchestrateur ;
   - pour O2, le test synthétique (§3.3) ;
   - puis les prérequis PJ2-1 à PJ2-3 (`J2_PREREQUISITES.md` §2).

# Journal des décisions

> Révisé le 2026-11-21 (mission 001, « Linux prioritaire »).
> Statuts : **Acceptée** (imposée par l'orchestrateur ou par une contrainte de mission),
> **Proposée** (recommandation de l'audit, à valider), **Ouverte** (à trancher, bloquante
> si indiqué), **Décision de projet clôturée** (tranchée par le porteur du projet ; les
> réserves qui subsistent sont indiquées), **Remplacée**.
> Les faits cités renvoient à `docs/audit/` (étiquettes [V], [H], [I]).

| ID | Sujet | Statut |
|---|---|---|
| D-001 | Linux x86_64 prioritaire, macOS ARM64 différé | Acceptée |
| D-002 | ReXGlue comme recompilateur et runtime | Proposée |
| D-003 | Vulkan comme backend graphique | Proposée |
| D-004 | SDL3 pour la fenêtre, l'audio et les entrées | Proposée |
| D-005 | C++23, CMake, Ninja, Clang ≥ 20 | Proposée |
| D-006 | Isolation des systèmes et règles de portabilité | Proposée |
| D-007 | Ressources propriétaires hors dépôt et hors magasin Nix | Acceptée |
| D-008 | Déchiffrement des XEX et protections techniques | **Décision de projet clôturée — O3 retenue** (2026-11-22) ; risque juridique résiduel ouvert (R-01) ; J2 autorisé le 2026-11-23 (D-015) |
| D-009 | Intégration NixOS (flake, SDK pur, jeu impur) | Proposée |
| D-010 | Politique de réutilisation des projets existants | Proposée |
| D-011 | Épinglage du SDK et série de correctifs | Acceptée (v0.11.0) |
| D-012 | Hébergement du projet | Acceptée |
| D-013 | Pas de lanceur graphique avant J5 | Proposée |
| D-014 | Xenia seulement comme oracle de développement | Proposée |
| D-015 | Lancement de J2 : autorisations PA-0 et PJ2-3, arbitrages de la phase A | **Acceptée** (2026-11-23) ; phase B soumise à PB-0, franchi le 2026-11-24 (D-017) |
| D-016 | Sortie de la phase A de J2 (PA-1) et règle des échecs intermittents des tests Debug | **Acceptée** (2026-11-24) ; PB-0 non franchi à cette date, franchi ensuite (D-017) |
| D-017 | Entrée en phase B de J2 : PB-0 franchi, B1 seulement | **Acceptée** (2026-11-24) ; PB-1 non franchi |
| D-018 | Arbitrages de B1 : plantages de l'extraction (option B) et rapport J0 local obligatoire | **Acceptée** (2026-11-25) ; ni fusion, ni extraction réelle, ni PB-1 |
| D-019 | Arbitrage de B1 : le bac à sable ne montre du magasin Nix que la fermeture de la commande empaquetée | **Acceptée** (2026-11-25) ; ni fusion, ni extraction réelle, ni PB-1 |

---

## D-001 — Linux x86_64 prioritaire, macOS ARM64 différé

- **Statut** : Acceptée (mission 001, modification de priorité).
- **Décision** : Linux x86_64 sous NixOS 26.05 est la seule cible des jalons J1 à J5.
  macOS ARM64 n'est abordé qu'au jalon J6, après une version Linux jouable et stabilisée.
- **Remplace** : la priorité macOS de la planification initiale.
- **Compatibilité future** : préservée par D-006. ReXGlue compile déjà pour `mac-arm64`
  en amont [V] (`EXISTING_PROJECTS.md` §C).

## D-002 — ReXGlue comme recompilateur et runtime

- **Statut** : Proposée.
- **Décision** : bâtir le portage sur ReXGlue (BSD 3-Clause), et non sur XenonRecomp avec
  un runtime maison.
- **Motifs** :
  - [V] Les deux ports existants du jeu reposent sur ReXGlue, et l'un est publié comme
    jouable sous Windows ;
  - [V] ReXGlue fournit le runtime complet (noyau, XAM, système de fichiers, GPU Xenos,
    APU XMA), et il compile sous Linux et Nix ;
  - [V] XenonRecomp (MIT) ne fournit aucun runtime et n'est plus actif depuis environ
    15 mois.
- **Conséquence** : la dépendance à une API instable est assumée (R-04, D-011).

## D-003 — Vulkan comme backend graphique

- **Statut** : Proposée.
- **Décision** : pilote `vulkan` de ReXGlue sous Linux, puis le même via MoltenVK sous
  macOS (J6). D3D12 sort du périmètre.
- **Motifs** : [V] le backend existe, il est choisi par défaut hors Windows, et il prend
  en charge les deux réglages GPU propres à FIFA. Aucun backend n'est à écrire, il est à
  valider (`LINUX_FEASIBILITY.md` §3).
- **Abstraction graphique** : celle du SDK (`IGraphicsDriver`, modules de pilotes).
  Le projet n'ajoute pas de couche au-dessus de Vulkan.

## D-004 — SDL3 pour la fenêtre, l'audio et les entrées

- **Statut** : Proposée.
- **Décision** : pilotes `ui-sdl3`, `apu-sdl3` et `hid-sdl3` du SDK, qui sont ses
  valeurs par défaut hors Windows [V].
- **Abstractions audio et entrées** : `IAudioSystem` et `IInputSystem` du SDK. Le
  projet n'en écrit pas d'autres.

## D-005 — C++23, CMake, Ninja, Clang ≥ 20

- **Statut** : Proposée.
- **Décision** : code du projet en C++23 (imposé par le SDK [V]) ; CMake ≥ 3.25 (testé
  avec 4.1.6 [V]) ; Ninja ; Clang ≥ 20 (imposé par ReXGlue v0.11.0 [V]) ; lld.
- **Outils annexes** : Python 3 accepté pour les outils d'analyse hors exécution (comme
  ceux du projet A).

## D-006 — Isolation des systèmes et règles de portabilité

- **Statut** : Proposée.
- **Décision** : architecture en couches `app/`, `hooks/`, `platform/{common,linux,macos}`
  au-dessus du SDK (`LINUX_FEASIBILITY.md` §6.2), avec ces règles :
  1. aucun en-tête système hors de `platform/<os>/` ;
  2. aucun appel direct à Vulkan, SDL ou POSIX dans `app/` et `hooks/` ;
  3. aucune hypothèse x86_64, taille de page ou modèle de code dans le code du projet ;
  4. aucune dépendance Windows dans le cœur portable ; pas de cible Windows prévue ;
  5. `platform/macos/` contient des bouchons qui compilent, mais n'est pas implémenté
     avant J6.

## D-007 — Ressources propriétaires hors dépôt et hors magasin Nix

- **Statut** : Acceptée (contrainte de mission), précisée par l'audit.
- **Décision** : ne jamais versionner, mettre en cache, envoyer en CI ni copier dans
  `/nix/store` l'ISO, les XEX, les images déchiffrées, le C++ généré, les caches de
  shaders, les captures, les sons, les sauvegardes et les DLC. Dossier privé local
  configurable (`ISO_REQUIREMENTS.md` §6). Contrôle automatique dès J1 (`ROADMAP.md`
  §4.5).
- **Autorisé** : empreintes, métadonnées d'en-tête, adresses et configuration d'analyse.

## D-008 — Déchiffrement des XEX et protections techniques

- **Statut** : **Décision de projet clôturée — O3 retenue** (2026-11-22). C'est une
  décision du porteur du projet, consignée dans le
  [ticket #8, commentaire 7086214621](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7086214621).
  **Le risque juridique résiduel reste ouvert** (R-01) : la décision tranche la voie
  technique, pas la question de droit.

  | Clos, au plan de la gouvernance du projet | Reste ouvert |
  |---|---|
  | La voie technique : **O3**, c'est-à-dire ReXGlue v0.11.0 amont tel quel. O1 et O2 sont écartées | La **qualification juridique** de trois actes : le déchiffrement des XEX, l'adaptation ou recompilation du jeu, et l'usage d'un SDK qui contient des clés. Aucun avis juridique n'a été obtenu et aucun droit n'est établi |
  | Le préalable interne « obtenir un avis juridique formel avant de retenir O3 ». Le porteur du projet l'a levé | L'**autorisation de commencer J2** (PJ2-3). Elle fera l'objet d'une décision distincte |
  | La reformulation de la contrainte de mission sur les protections techniques (ci-dessous) | Toute **distribution**. Elle est exclue du périmètre, et en envisager une demanderait une nouvelle décision |

- **Faits** :
  - [V] ReXGlue déchiffre les XEX avec des clés intégrées, à la génération de code et à
    chaque lancement ;
  - [V] l'outil `xeximage.py` du projet A contient la clé en clair ;
  - [V] (J0, 2026-11-22) les deux modules du disque de l'utilisateur, `default.xex` et
    `fifadllzf.xex`, sont chiffrés (AES) et compressés (LZX), d'après leur en-tête
    *file format info* lu en clair, sans déchiffrement
    (`docs/reports/J0_IDENTIFICATION.md`). Toute génération de code passera donc par
    l'image en clair des deux modules ;
  - [V] (lecture de la source de ReXGlue v0.11.0, `src/filesystem/xex.cpp`, sans
    exécution) un module non chiffré est accepté par `XEXImage::DecodeWith`, sans
    déchiffrement CBC. Mais `XEXImage::Decode` dérive toujours une clé de session à
    partir des clés intégrées avant de décoder. Avec l'option O2, ReXGlue tel quel
    garde donc une opération cryptographique sur l'en-tête, même si les données ne sont
    pas chiffrées ;
  - [I] la qualification juridique ;
  - pays des opérations : France, selon la déclaration de l'utilisateur du 2026-11-22,
    non vérifiée de façon indépendante.
- **Options examinées avant la décision** (`ISO_REQUIREMENTS.md` §5) :
  - O1 : attendre un avis juridique ;
  - O2 : l'utilisateur fournit des XEX non chiffrés, **avec l'intention** que le projet
    n'utilise ni n'embarque de clé. Ce n'est pas l'état actuel : il faudrait un
    correctif du SDK, qui n'a pas été réalisé (`docs/D-008_DECISION_NOTE.md` §3.3 et
    §3.4) ;
  - O3 : utiliser ReXGlue tel quel. **C'est l'option retenue.**
- **Historique de l'instruction**. Ces étapes sont conservées pour la traçabilité ; la
  décision ci-dessous les remplace.
  - *Recommandation de l'audit (2026-11-21), historique* : O1 jusqu'à décision. Elle
    n'est plus d'actualité depuis la décision du 2026-11-22.
  - *Constat de J0 (PR #4)* : le chiffrement est constaté, et la décision restait alors
    ouverte. Pour O2, des XEX non chiffrés ne pouvaient venir que d'une opération de
    l'utilisateur sur sa copie, hors du projet.
  - *Analyse préalable (PR #9, ticket #8)* : `docs/D-008_DECISION_NOTE.md` compare O1, O2
    et O3 sous les angles juridique, technique et opérationnel. Ce n'est ni une décision
    ni un avis juridique. La note établit, par lecture du code public de ReXGlue :
    - qu'il n'existe qu'un chemin de décodage, utilisé à la génération de code et à
      chaque lancement ;
    - qu'O2 n'est pas une voie sans clé avec ReXGlue tel quel ;
    - que le SDK compilé depuis J1 contient déjà le code de déchiffrement et ses clés.
  - *Choix et déclarations de l'utilisateur (PR #10)*, consignés dans le ticket #8. Ce
    sont des déclarations : aucun justificatif n'a été examiné, et aucun n'est demandé.

    | Point | Déclaration de l'utilisateur | Ticket #8 |
    |---|---|---|
    | Voie technique **O3**, c'est-à-dire ReXGlue tel quel, plutôt qu'O2 | « Je valide O3 » | [7084704229](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084704229) |
    | Pays des opérations **France**, **usage personnel** uniquement, **aucune distribution** : ni jeu recompilé, ni code généré, ni ressource propriétaire | « Oui en France pour mon usage personnel et sans distribution » | [7084729825](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084729825) |
    | Jeu **acheté en magasin sur DVD original**, ISO **extraite par l'utilisateur** lui-même | « Oui je l'ai acheté en magasin en DVD puis rippé moi-même » | [7084744556](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084744556) |
    | **Accord personnel** de l'utilisateur pour la voie O3 | « Je l'autorise » | [7084775427](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084775427) |

    Ces déclarations ne sont ni une conclusion de légalité, ni un avis juridique, ni
    une autorisation des titulaires de droits, ni une preuve d'achat. La possession d'un
    exemplaire original, l'usage personnel et l'absence de distribution ne suffisent
    pas, à eux seuls, à rendre les opérations licites.

    État consigné alors : O3 retenue, mise en œuvre suspendue à deux conditions, la
    qualification juridique de trois points et une décision sur la contrainte de
    mission. **Cet état est remplacé par la décision ci-dessous.**
- **Décision du porteur du projet (2026-11-22)**,
  [ticket #8, commentaire 7086214621](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7086214621).
  - **Déclaration citée** : « Nous resterons dans un flou juridique ici. Je possède le
    jeu et je ne le redistribuerai pas. Peut-on valider O3 ? » L'orchestrateur l'a
    consignée comme une décision de projet.
  - **Voie** : O3 est la voie technique définitive. ReXGlue v0.11.0 amont (`a3e1d82`,
    D-011) déchiffre lui-même les modules, à la génération de code et à chaque
    lancement, sur la machine de l'utilisateur et pour sa copie. Le correctif « sans
    clé » d'O2 et son test synthétique (`docs/D-008_DECISION_NOTE.md` §3.3) ne sont pas
    prévus.
  - **Préalable levé** : l'obligation interne d'obtenir un avis juridique formel avant
    de retenir O3 est levée **par décision du porteur du projet**. Elle n'est pas levée
    parce qu'une autorisation légale aurait été établie.
  - **Incertitude juridique résiduelle, reconnue explicitement**. Elle porte sur :
    1. le déchiffrement des XEX par ReXGlue, à la génération de code et à chaque
       lancement ;
    2. l'adaptation, c'est-à-dire la recompilation, du code du jeu ;
    3. le SDK compilé par le flake, qui contient les clés et le code de déchiffrement.

    La décision n'est **ni un avis juridique, ni une autorisation des titulaires de
    droits, ni une démonstration de licéité**. Que le porteur accepte personnellement le
    risque ne modifie pas le droit applicable. Aucun document du projet ne doit dire que
    le déchiffrement est « légalement validé » ni « légalement autorisé ».
  - **Contrainte de mission reformulée.** La contrainte initiale était : « ne pas engager
    de contournement des protections techniques ». Elle devient :

    > Le projet n'écrit, ne versionne ni ne diffuse aucune clé, ni aucun code ou outil
    > de déchiffrement qui lui soit propre. Le seul déchiffrement est celui du SDK public
    > amont ReXGlue v0.11.0 (voie O3). Il est exécuté localement, sur la machine de
    > l'utilisateur et pour sa copie, sous réserve des règles de droit applicables.

    Cette reformulation désigne une voie technique. Elle ne confère aucun droit de
    contourner une protection. Elle exclut notamment `xeximage.py` du projet A,
    XenonRecomp et tout outil de déchiffrement écrit pour le projet.
  - **SDK déclaré** [V] : le SDK compilé par le flake contient les clés maîtresses et le
    code de déchiffrement. Ils viennent de `src/filesystem/xex.cpp` et de
    `thirdparty/excrypt`, compilés dans `librexfilesystem.so`
    (`docs/D-008_DECISION_NOTE.md` §3.4). L'exécutable du portage, lié à ce SDK, en
    dépendra à chaque lancement. Le projet ne présente jamais ce SDK comme dépourvu de
    déchiffrement. Aucune valeur de clé n'est reproduite dans le dépôt. Aucun cache
    binaire public du SDK n'est prévu : la CI n'en alimente aucun.
  - **D-007 impérative**. Restent dans le stockage privé local de l'utilisateur :
    - l'ISO et les XEX ;
    - les images décodées et le code généré ;
    - les caches, les journaux et toute autre sortie issue du jeu.

    Rien de cela ne va dans Git, dans les journaux publics, en CI ni dans le magasin Nix.
  - **Périmètre déclaré** : France, usage strictement personnel, aucune distribution, DVD
    original acheté en magasin et ISO extraite par l'utilisateur. Ce sont des
    déclarations, non des faits certifiés.
- **Conséquences sur les autres statuts** :
  - **C0.5** est atteint au sens de la gouvernance, puisque la voie est décidée. Ce n'est
    pas une attestation de conformité juridique. Pour la clôture de J0, voir
    `docs/reports/J0_IDENTIFICATION.md` §5 ;
  - **PJ2-1** est levé au même titre (`docs/J2_PREREQUISITES.md` §2) ;
  - **L'autorisation PJ2-3 n'était pas donnée** : cette décision ne lançait pas J2.
    Aucun XEX n'est traité, aucun code n'est généré, rien n'est déchiffré. *Suite : PJ2-3
    est accordée le 2026-11-23 (D-015) ; le traitement des fichiers du jeu attend
    PB-0.*
  - **R-01** reste un risque élevé (`docs/audit/RISKS.md`).
- **Éléments de droit** : les sources officielles sont listées aux §9.2 et §10 de
  `docs/D-008_DECISION_NOTE.md`. Elles ne remplacent pas une consultation juridique.
- **Engagement** : le dépôt ne contiendra jamais de clé, ni de code de déchiffrement
  écrit par le projet. La contrainte reformulée reprend cet engagement.

## D-009 — Intégration NixOS

- **Statut** : Proposée.
- **Décision** :
  - `flake.nix` épinglé sur nixos-26.05, avec `flake.lock` ;
  - dérivation *pure* du SDK depuis les sources : `llvmPackages_20.stdenv`, sous-modules
    épinglés, bibliothèques X11 explicites, `hardeningDisable = [ "fortify" "fortify3" ]`
    (ou correctif en amont), rpath corrigé ;
  - `devShell` *impur* pour la génération de code et la compilation du jeu, depuis le
    dossier privé ;
  - enveloppe d'exécution qui fournit les bibliothèques chargées par `dlopen` et les ICD
    Vulkan.
- **Motifs** : constats faits en compilant le SDK sous Nix (`LINUX_FEASIBILITY.md` §1.1
  et §5) ; protection des données (D-007).
- **Rejeté** : utiliser le SDK précompilé avec `nix-ld` ou `steam-run` (dépendances
  FHS et libstdc++ de GCC 13), sauf pour une comparaison ponctuelle.

## D-010 — Politique de réutilisation des projets existants

- **Statut** : Proposée.
- **Projet A** (CalinGraphics, BSD 3-Clause) : réutilisation autorisée **avec notice**
  pour la configuration d'analyse (si elle est revalidée sur le code du disque de
  l'utilisateur, `docs/J2_PREREQUISITES.md` §3 ; les empreintes diffèrent depuis J0),
  les correctifs du SDK
  (à transposer), les correctifs du jeu, les réglages GPU et les outils Python.
  **Exclus** : le lanceur WPF et les scripts PowerShell, qui ne sont pas portables, ainsi
  que `xeximage.py` (déchiffrement, D-008). Les outils d'analyse qui chargent l'image par
  `xeximage.load` ne sont réutilisables qu'avec une autre source de l'image, à décider
  (`docs/J2_PREREQUISITES.md` §3.3).
- **Projet B** (RamiChaaben8, MIT) : réutilisation ciblée avec notice, après
  clarification de la titularité (la notice porte le nom d'un autre auteur [V]) :
  connaissances de débogage, correctifs XAM, outil DLC (à J5). **Exclus** :
  `Settings.exe`, `sounds/*.wav` et tout binaire.
- **Principe** : ne forker aucun des deux projets ; importer des éléments précis, avec
  leur provenance indiquée dans un fichier `THIRD_PARTY.md`.

## D-011 — Épinglage du SDK et série de correctifs

- **Statut** : Acceptée par l'orchestrateur (mission 002) : **ReXGlue v0.11.0**, épinglé
  sur `a3e1d82678ca20d68d4837a8e9ee4652ff073745`, le commit désigné par l'étiquette
  `v0.11.0` [V]. Le commit de fusion « Release v0.11.0 » de `main`
  (`ebac1cf0d04bab0042a5dd6148b34ab3953e9c0d`), lu pendant l'audit, a exactement le même
  arbre source (`bd12f1aa8e972f0f4c608a7d23a6971acfaf6c35`) [V].
- **Options examinées** :
  - v0.11.0 : compilation sous Nix vérifiée [V], API actuelle ; correctifs du projet A à
    transposer (0003 et 0002 au minimum ; 0001 et 0006 semblent déjà en amont [V]).
    *Établi à l'étape A2 (`docs/J2_A2_SDK_PATCHES.md`) : 0001, 0004 et 0007 sont déjà en
    amont, et 0006 l'est en partie. 0003 est candidat pour J2, à confirmer en A3.
    0002 sera d'abord essayé par configuration en phase B. 0008 est reporté à J4 ;*
  - `bd833a2` avec les correctifs du projet A : base Windows connue, mais compilation
    Linux non vérifiée et API ancienne.
- **Règle commune** : commit exact épinglé ; correctifs numérotés dans
  `patches/rexglue-sdk/` ; montée de version seulement à un jalon validé.
- **Série (2026-11-23, soumise à la revue)** : `0001-function-table-base.patch`, le 0003
  du projet A réécrit pour v0.11.0 (étape A3, `docs/J2_A3_FUNCTION_TABLE.md`). Sa
  provenance est dans son en-tête et dans `THIRD_PARTY.md` (D-010). Le contrôle
  `sdk-patches` de `nix flake check` liste les fichiers touchés et refuse tout fichier
  des XEX ou du déchiffrement (O3, D-015).
- **Option de construction (2026-11-24, soumise à la revue)** :
  `-DCMAKE_INSTALL_LIBDIR=lib` dans `nix/rexglue-sdk.nix`. Ce n'est pas un correctif du
  SDK. Elle rend justes les emplacements des modules fournisseurs du paquet, faux avec
  le dossier absolu que passe nixpkgs (étape A7, `docs/J2_A7_SYNTHETIC_CHAIN.md` §4).

## D-012 — Hébergement du projet

- **Statut** : Acceptée (choix de l'utilisateur).
- **Décision** : le projet a son dépôt dédié, `mengpo1/fifa2010wc`, qui ne contient que
  ce projet. Son `.gitignore` et sa CI peuvent être réglés pour D-007 sans gêner un
  autre projet.

## D-013 — Pas de lanceur graphique avant J5

- **Statut** : Proposée.
- **Décision** : configuration par fichier TOML et par la ligne de commande jusqu'à J4 ;
  un lanceur portable éventuel au jalon J5.

## D-014 — Xenia seulement comme oracle de développement

- **Statut** : Proposée.
- **Décision** : Xenia peut servir, sur la machine du développeur, à produire des
  comportements et des captures de référence. Il n'est jamais lancé par le portage, ni
  distribué avec lui. Cela respecte l'exigence « sans émulateur lors de son utilisation ».

## D-015 — Lancement de J2 : autorisations PA-0 et PJ2-3, arbitrages de la phase A

- **Statut** : **Acceptée** (2026-11-23). Sources :
  - [ticket #14](https://github.com/mengpo1/fifa2010wc/issues/14) et son
    [commentaire 7099561807](https://github.com/mengpo1/fifa2010wc/issues/14#issuecomment-7099561807) ;
  - instruction directe du porteur du projet à Claude Code.
- **Déclaration citée** : « oui je l'autorise et AVEC les fichiers du jeu ».
- **Autorisations**. Une autorisation enregistrée n'est pas un prérequis technique
  satisfait.

  | Point | État | Portée |
  |---|---|---|
  | **PA-0** | **Accordée** | Phase A (A1 à A8), sans ISO, XEX, ressource du jeu, code généré ni donnée propriétaire |
  | **PJ2-3** | **Accordée sur le principe** | J2, phase B comprise : traitement local de l'exemplaire privé de l'utilisateur, **sur sa machine uniquement** |
  | **PB-0** | **Non franchi** | Conditions techniques d'entrée en phase B, sans nouveau consentement : PA-1, CP-1 à CP-7 exécutés et consignés, méthode de validation des adresses décidée après A8 (`docs/J2_PLAN.md` §2) |

- **Arbitrages de l'orchestrateur sur `docs/J2_PLAN.md` §6** (ticket #14) :
  1. **Image en clair et validation des adresses** :
     - on ne choisit ni n'exécute de nouveau moyen de produire une image ;
     - la priorité va à une méthode fondée sur les diagnostics, les sorties et les
       interfaces existants de ReXGlue, évaluée par lecture du code en A1 et A8 ;
     - si elle ne suffit pas, A8 compare les autres méthodes, leurs risques et les
       dérogations qu'elles demanderaient ;
     - **aucun programme nouveau produisant une image décodée n'est autorisé
       implicitement**. La méthode est décidée après A8, avant PB-0.
  2. **« O3 tel quel »** désigne le mécanisme de décodage et de déchiffrement des XEX
     de l'amont, inchangé.
     - Les correctifs fonctionnels sans lien avec le déchiffrement sont permis, avec des
       tests. C'est le cas de 0002 et 0003 s'ils sont nécessaires.
     - Toute modification de `src/filesystem/xex.cpp`, de `thirdparty/excrypt`, des clés
       ou du comportement de déchiffrement est exclue.
     - Aucun correctif ancien n'est présumé compatible.
  3. **PA-0 est distinct de PJ2-3.**
  4. **Le ticket #11 (J1-bis) est remplacé par la phase A.** La couche Linux générique
     relève de A1, puis de A6. Rien n'est réimplémenté de ce que fournit ReXGlue sans
     inventaire ni besoin démontré.
- **Ce qui ne change pas** :
  - D-007 est impérative : tout contenu ou artefact privé reste sous
    `$WC2010_PRIVATE_DIR`, et rien ne va dans GitHub, en CI, dans le cloud ni dans
    `/nix/store` ;
  - R-01 reste une incertitude juridique non résolue. Ce consentement n'est ni une
    autorisation des titulaires de droits, ni un avis juridique ;
  - la fusion de chaque PR, le choix de la méthode A8 et les points d'arrêt PA-1, puis
    PB-1 à PB-4, restent des actes de revue distincts.

## D-016 — Sortie de la phase A de J2 (PA-1) et règle des échecs intermittents des tests Debug

- **Statut** : **Acceptée** (2026-11-24). Sources :
  - le rapport de phase A, `docs/reports/J2_PHASE_A.md`, fusionné par la
    [PR #27](https://github.com/mengpo1/fifa2010wc/pull/27) ;
  - les revues de l'orchestrateur
    [6039494135](https://github.com/mengpo1/fifa2010wc/pull/27#pullrequestreview-6039494135)
    et [6043202272](https://github.com/mengpo1/fifa2010wc/pull/27#pullrequestreview-6043202272)
    de cette PR ;
  - la décision du porteur du projet, donnée à Claude Code le 2026-11-24 : « PA-1
    franchi, règle confirmée ».
- **Décision 1 : PA-1 est franchi.**
  - Les critères de `docs/J2_PLAN.md` §3.9 sont remplis (rapport, §1).
  - A1 à A8, et A8-bis, sont fusionnées dans `main`, chacune après une CI verte sur sa
    tête exacte.
  - La CI de `main` porte la réserve du rapport, §4.1.
- **Décision 2 : la règle des échecs intermittents des tests Debug de ReXGlue** est
  confirmée. C'est l'option 2 du rapport (§4.1), proposée par l'orchestrateur ; son suivi
  se fait dans le [ticket #28](https://github.com/mengpo1/fifa2010wc/issues/28).
  - Tous les tests Debug et leur parallélisme sont gardés. **Aucun test n'est
    désactivé, ignoré ni relancé automatiquement.**
  - Un échec isolé de la suite Debug peut être relancé **une fois au plus**, à la main,
    sur le même commit. Les journaux et l'identifiant des deux tentatives sont gardés.
  - **Un second échec bloque**, et doit être examiné.
  - Pour chaque incident, on consigne :
    - le SHA ;
    - le contexte de la machine ;
    - le nom du test ;
    - le signal ou le délai dépassé ;
    - les traces.
  - On réévalue la règle si la fréquence augmente, ou si un test devient reproductible.
  - Les options écartées pour l'instant :
    - signaler les cas à ReXGlue : seulement avec un accord explicite et distinct du
      porteur, à partir d'informations publiques, sans aucun journal du jeu ;
    - réduire le parallélisme, sans mesure préalable ;
    - écrire un correctif du SDK, tant qu'aucun test ne reproduit la cause.
  - La cause, liée à la durée de vie d'un thread, reste une **hypothèse**.
- **Ce qui ne change pas** :
  - **PB-0 n'est pas franchi.** PA-1 n'est pas PB-0.
  - La phase B attend encore les contrôles CP-1 à CP-7, exécutés et consignés **sur la
    machine du porteur du projet**, dont la vérification des *core dumps* transmis par
    tube (rapport, §4.3). Elle attend ensuite la décision PB-0, distincte.
  - **Aucune opération sur l'ISO ni sur les XEX n'a lieu avant PB-0.** Rien du jeu ne va
    dans GitHub, en CI, dans le cloud ni dans `/nix/store` (D-007).
  - Les limites consignées dans le rapport (§4.2 à §4.6) restent à respecter en phase B.

## D-017 — Entrée en phase B de J2 : PB-0 franchi, B1 seulement

- **Statut** : **Acceptée** (2026-11-24). Sources :
  - la décision consignée par l'orchestrateur dans le
    [ticket #14, commentaire 7143518212](https://github.com/mengpo1/fifa2010wc/issues/14#issuecomment-7143518212) ;
  - le bilan des contrôles CP-1 à CP-7 présenté au porteur du projet, dans le
    [commentaire 7143470897](https://github.com/mengpo1/fifa2010wc/issues/14#issuecomment-7143470897)
    du même ticket ;
  - la réponse du porteur, dans la conversation d'orchestration, à la question
    « autorises-tu formellement le passage à la phase B et le traitement local des
    fichiers du jeu sur ton NixOS ? » : **« oui »**.
- **Décision : PB-0 est franchi**, sous les conditions déjà documentées.
- **Prérequis présentés au porteur**, tels que le ticket #14 les consigne :
  - PJ2-3 accordée (D-015) ; PA-1 franchi (D-016) ; méthode des adresses : M1 d'abord, M3
    en repli, sans présumer un code identique à celui du projet A ;
  - **CP-1** : `private_guard check-dir` et `private-project init` passent sur la machine
    du porteur ; l'ISO est en lecture seule ;
  - **CP-2** : aucun dossier privé en entrée Nix, d'après la revue des fichiers Nix ; CI
    publique verte, sans données du jeu. Le `nix flake check` local a répondu
    `all checks passed!`, mais avec `running 0 flake checks` ;
  - **CP-3** : avant l'opération, la seule grande correspondance du magasin est le fichier
    `nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude`, déjà relevé et non ouvert. Aucun `*.xex`,
    aucune grande `*.iso`. Contrôle non exhaustif ;
  - **CP-4** : essai à blanc de `preflight` et `postflight` réussi, avec la surveillance du
    dossier personnel, de `/tmp`, de 31 montages Btrfs persistants, du dépôt et du SDK ;
    6 dossiers `PrivateTmp` de systemd exclus et nommés (#30) ; aucun constat.
    - Un `SIGSEGV` synthétique sous `ulimit -c 0` a donné `COREFILE none`. Ce n'est pas
      une preuve pour tous les plantages.
    - `kernel.core_pattern` reste un tube vers systemd-coredump ;
  - **CP-5** : `logs/share` vide, aucun fichier à partager. Analyse et relecture
    obligatoires avant tout partage ;
  - **CP-6** : `main` à `fda9971`, propre ; crochet `.githooks` actif ; 57 fichiers du dépôt
    analysés sans donnée propriétaire ; aucun fichier indexé ;
  - **CP-7** : manifeste public sans adresse ; comparaison obligatoire avant toute
    réutilisation des adresses du projet A.
- **Portée exacte** :
  - **B1 seulement**, sur la machine NixOS du porteur, avec son propre exemplaire, et
    exclusivement dans `$WC2010_PRIVATE_DIR` : ni dépôt, ni cloud, ni CI, ni magasin Nix ;
  - B1 est l'extraction par `rexglue vfs dump`, sans décodage des XEX
    (`docs/J2_A1_SDK_INVENTORY.md` §3.3). Sa procédure versionnée et sa revue
    indépendante sont préparées **sans aucune donnée du jeu**
    ([ticket #32](https://github.com/mengpo1/fifa2010wc/issues/32),
    `docs/J2_B1_EXTRACTION.md`) ;
  - avant et après chaque opération privée :
    - CP-3 et CP-4 ;
    - la surveillance explicite des montages d'impermanence ;
    - des journaux confinés au dossier privé ;
    - refus du root, `umask 077`, `ulimit -c 0` ;
    - l'ISO en lecture seule ;
  - aucune sortie ni aucun contenu propriétaire dans les PR ou en CI.
- **Ce qui n'est pas décidé** :
  - **PB-1 n'est pas franchi.** Après B1, on compare 49 fichiers, 8 dossiers, les SHA-256
    des deux XEX et celui de l'ISO avec J0, et l'on s'arrête en cas d'écart.
    L'orchestrateur décide sur les résultats locaux ;
  - **B2 ne commence pas avant la décision PB-1** ;
  - aucune décision PB-2, PB-3 ou PB-4 n'est anticipée ;
  - aucune PR n'est fusionnée sans un consentement distinct du porteur ;
  - le risque juridique résiduel **R-01 reste ouvert** ;
  - pas de distribution, ni de modification du déchiffrement de ReXGlue.
- **Limite** : le passage de PB-0 autorise le travail local dans ce cadre. Il ne prétend
  pas garantir l'absence de fuite hors du périmètre couvert par les contrôles
  (`docs/J2_PHASE_B_CONTROLS.md` §3, « Limite »).

## D-018 — Arbitrages de B1 : plantages de l'extraction et rapport J0 local

- **Statut** : **Acceptée** (2026-11-25). Source : la décision du porteur du projet,
  consignée dans la PR #33,
  [commentaire 7161970968](https://github.com/mengpo1/fifa2010wc/pull/33#issuecomment-7161970968).
  Elle répond aux questions posées après la revue
  [7158108520](https://github.com/mengpo1/fifa2010wc/pull/33#issuecomment-7158108520) (B1-R03 et
  B1-R06).
- **Décision 1 : option B pour les plantages de l'extraction** (`docs/J2_B1_EXTRACTION.md`
  §6) :
  - `RLIMIT_CORE` exactement à `1` pour le seul processus d'extraction, dans le bac à
    sable ;
  - sous réserve d'une **validation synthétique** sur le noyau et le mode `core_pattern`
    effectivement utilisés ;
  - `private_guard` adapté de façon ciblée, sans affaiblir les autres contrôles. Dans
    l'implémentation, aucun de ses contrôles n'a dû changer : l'outil garde une limite
    souple de `0`, que `private_guard` contrôle, et seul le processus confiné reçoit `1` ;
  - **seul le mode tube est accepté** ; le mode socket, ou tout mode non validé, est refusé ;
  - **`run` reste bloqué** tant que la preuve locale n'est pas acquise ;
  - aucun `sudo`, aucune modification globale de NixOS ;
  - les cas négatifs et le protocole local, sans données propriétaires, sont documentés et
    testés.
- **Décision 2 : pas de B1 sans rapport J0 local.** Le rapport valide et concordant est
  obligatoire ; son absence, une erreur ou une discordance bloquent l'extraction
  (`docs/J2_B1_EXTRACTION.md` §7).
- **Ce qui ne change pas** :
  - ces arbitrages ne valent **ni autorisation de fusion, ni autorisation d'extraction
    réelle** ;
  - **PB-1 n'est pas franchi**, et B2 reste interdit ;
  - D-017 reste en vigueur : B1 seulement, sur la machine du porteur.

## D-019 — Arbitrage de B1 : accès du bac à sable au magasin Nix

- **Statut** : **Acceptée** (2026-11-25). Source : la décision du porteur du projet,
  consignée dans la PR #33,
  [commentaire 7172181035](https://github.com/mengpo1/fifa2010wc/pull/33#issuecomment-7172181035).
  Elle répond à la question posée après la revue de la version 3
  ([7164470853](https://github.com/mengpo1/fifa2010wc/pull/33#issuecomment-7164470853), R02 ;
  `docs/J2_B1_EXTRACTION.md` §3.4).
- **Décision : option B.** Le processus confiné n'accède qu'aux seules dépendances
  nécessaires, en lecture seule, et non à tout `/nix/store` :
  - la **fermeture transitive des dépendances Nix** de la commande empaquetée et du SDK
    nécessaires à l'extraction et aux sondes, **calculée lors de la construction**, sans
    liste de bibliothèques maintenue à la main ;
  - **provenance et validité des chemins vérifiées** ; le démarrage est refusé si la liste
    est absente, invalide ou incomplète ;
  - **aucun montage global du magasin en guise de repli** ;
  - aucune donnée propriétaire dans les dérivations ou les artefacts Nix.
- **Mise en œuvre** (`docs/J2_B1_EXTRACTION.md` §3.4) :
  - `closureInfo` de nixpkgs, sur Python, le SDK et le fichier de l'outil, passée par la
    commande empaquetée (`--store-closure`) ;
  - chaque chemin de la fermeture est lié en lecture seule, et rien d'autre du magasin ;
  - la preuve de l'option B (D-018) est liée à cette fermeture.
- **Critères demandés** : vraie extraction synthétique et sonde dans le confinement
  restreint ; test négatif d'accès à une entrée synthétique du magasin extérieure à la
  fermeture ; test de dépendance manquante et de refus avant extraction ; maintien des
  contrôles existants.
- **Ce qui ne change pas** :
  - D-018 reste en vigueur, dont le rapport J0 local obligatoire ;
  - cet arbitrage ne vaut **ni autorisation de fusion, ni autorisation d'extraction
    réelle** ;
  - **PB-1 n'est pas franchi**, et B2 reste interdit ;
  - aucun `sudo`, aucune modification globale de NixOS ;
  - une nouvelle revue indépendante est demandée avant toute approbation.

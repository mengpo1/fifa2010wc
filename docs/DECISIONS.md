# Journal des décisions

> Révisé le 2026-11-21 (mission 001, « Linux prioritaire »).
> Statuts : **Acceptée** (imposée par l'orchestrateur ou par une contrainte de mission),
> **Proposée** (recommandation de l'audit, à valider), **Ouverte** (à trancher, bloquante
> si indiqué), **Remplacée**.
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
| D-008 | Déchiffrement des XEX et protections techniques | **Ouverte, bloquante pour J2** ; O3 retenue comme voie technique par l'utilisateur — mise en œuvre suspendue à la qualification des conditions juridiques et au feu vert opérationnel distinct |
| D-009 | Intégration NixOS (flake, SDK pur, jeu impur) | Proposée |
| D-010 | Politique de réutilisation des projets existants | Proposée |
| D-011 | Épinglage du SDK et série de correctifs | Acceptée (v0.11.0) |
| D-012 | Hébergement du projet | Acceptée |
| D-013 | Pas de lanceur graphique avant J5 | Proposée |
| D-014 | Xenia seulement comme oracle de développement | Proposée |

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

- **Statut** : **Ouverte, bloquante pour J2.** O3 retenue comme voie technique par l'utilisateur — mise en œuvre suspendue à la qualification des conditions juridiques et au feu vert opérationnel distinct
  (2026-11-22). La décision n'est pas close : voir « Choix et déclarations de
  l'utilisateur ».
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
- **Options** (`ISO_REQUIREMENTS.md` §5) :
  - O1, attente d'un avis ;
  - O2, XEX non chiffrés fournis par l'utilisateur, **avec l'intention** que le projet
    n'utilise ni n'embarque de clé. Ce n'est pas l'état actuel : il faudrait un correctif
    du SDK, non réalisé (`docs/D-008_DECISION_NOTE.md` §3.3 et §3.4) ;
  - O3, ReXGlue utilisé tel quel.
- **Recommandation de l'audit** : O1 jusqu'à décision. J0 et J1 n'en dépendent pas.
- **Mise à jour du 2026-11-22** : le chiffrement est constaté, la décision **reste
  ouverte**. Les options sont inchangées. Pour O2, des XEX non chiffrés ne peuvent venir
  que d'une opération de l'utilisateur sur sa copie, hors du projet, et la question
  juridique demeure.
- **Analyse préalable** (2026-11-22, ticket #8) : `docs/D-008_DECISION_NOTE.md` compare
  O1, O2 et O3 sous les angles juridique, technique et opérationnel. Ce n'est ni une
  décision ni un avis juridique : **D-008 reste ouverte**. La note établit, par lecture
  du code public de ReXGlue :
  - qu'il n'existe qu'un chemin de décodage, utilisé à la génération de code et à chaque
    lancement ;
  - qu'O2 n'est pas une voie sans clé avec ReXGlue tel quel ;
  - que le SDK compilé depuis J1 contient déjà le code de déchiffrement et ses clés.

  Elle liste aussi les actes à faire qualifier, et ce que la décision devra consigner.
- **Choix et déclarations de l'utilisateur (2026-11-22)**, consignés dans le ticket #8.
  Ce sont des déclarations : aucun justificatif n'a été examiné, et aucun n'est demandé.

  | Point | Déclaration de l'utilisateur | Ticket #8 |
  |---|---|---|
  | Voie technique **O3**, c'est-à-dire ReXGlue tel quel, plutôt qu'O2 | « Je valide O3 » | [7084704229](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084704229) |
  | Pays des opérations **France**, **usage personnel** uniquement, **aucune distribution** : ni jeu recompilé, ni code généré, ni ressource propriétaire | « Oui en France pour mon usage personnel et sans distribution » | [7084729825](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084729825) |
  | Jeu **acheté en magasin sur DVD original**, ISO **extraite par l'utilisateur** lui-même | « Oui je l'ai acheté en magasin en DVD puis rippé moi-même » | [7084744556](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084744556) |
  | **Accord personnel** de l'utilisateur pour la voie O3 | « Je l'autorise » | [7084775427](https://github.com/mengpo1/fifa2010wc/issues/8#issuecomment-7084775427) |

  - **Ce que ces déclarations ne sont pas** :
    - ni une conclusion de légalité, ni un avis juridique ;
    - ni une autorisation des titulaires de droits ;
    - ni une preuve d'achat.

    La possession d'un exemplaire original, l'usage personnel et l'absence de
    distribution ne suffisent pas, à eux seuls, à rendre les opérations licites.
    « Je l'autorise » vaut accord personnel pour O3. Il ne lève pas les prérequis et
    n'autorise pas le démarrage de J2 (PJ2-3).
  - **Points à qualifier avant toute exécution** :
    1. le déchiffrement des XEX par ReXGlue, à la génération de code et à chaque
       lancement ;
    2. la traduction, c'est-à-dire la recompilation, du code existant ;
    3. la dépendance ReXGlue compilée par le flake, qui contient les clés et le code de
       déchiffrement.

    La distribution n'est pas traitée comme une activité projetée : le périmètre déclaré
    et D-007 l'excluent.
  - **Autres conditions** :
    - une décision explicite, après clarification juridique, sur la façon dont la
      contrainte initiale « ne pas engager de contournement des protections
      techniques » s'applique à cette voie ;
    - l'accord distinct de démarrage de J2 (PJ2-3) ;
    - le maintien de D-007 : ni ISO, ni XEX, ni code généré, ni clé, ni autre ressource
      propriétaire dans le dépôt, les journaux partagés ou le magasin Nix.
  - **Statuts** :
    - O3 est retenue comme voie technique ;
    - D-008 et C0.5 ne sont **pas clôturées** ;
    - J0 n'est pas clos ;
    - PJ2-1 et PJ2-3 ne sont pas atteints, et J2 n'est pas autorisé ;
    - aucun déchiffrement, aucune génération de code.
  - **Éléments de droit** : les sources officielles relevées dans le ticket #8 sont
    listées dans l'addendum de la note (`docs/D-008_DECISION_NOTE.md` §9). Elles ne
    remplacent pas une consultation juridique.
  - **Conséquence technique** : le correctif « sans clé » et le test synthétique
    (`docs/D-008_DECISION_NOTE.md` §3.3) ne concernent que la voie O2. Ils ne sont pas
    prévus.
- **Engagement immédiat** : le dépôt ne contiendra jamais de clé ni de code de
  déchiffrement écrit par le projet.

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
  que `xeximage.py` (déchiffrement, D-008).
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
    transposer (0003 et 0002 au minimum ; 0001 et 0006 semblent déjà en amont [V]) ;
  - `bd833a2` avec les correctifs du projet A : base Windows connue, mais compilation
    Linux non vérifiée et API ancienne.
- **Règle commune** : commit exact épinglé ; correctifs numérotés dans
  `patches/rexglue-sdk/` ; montée de version seulement à un jalon validé.

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

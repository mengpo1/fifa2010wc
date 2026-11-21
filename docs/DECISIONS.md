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
| D-008 | Déchiffrement des XEX et protections techniques | **Ouverte, bloquante pour J2** |
| D-009 | Intégration NixOS (flake, SDK pur, jeu impur) | Proposée |
| D-010 | Politique de réutilisation des projets existants | Proposée |
| D-011 | Épinglage du SDK et série de correctifs | Ouverte (recommandation : v0.11.0) |
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

- **Statut** : **Ouverte, bloquante pour J2.** À trancher par l'orchestrateur ou
  l'utilisateur, après avis juridique.
- **Faits** :
  - [V] ReXGlue déchiffre les XEX avec des clés intégrées, à la génération de code et à
    chaque lancement ;
  - [V] l'outil `xeximage.py` du projet A contient la clé en clair ;
  - [H] les XEX du jeu sont chiffrés ;
  - [I] la qualification juridique et le pays de l'utilisateur.
- **Options** (`ISO_REQUIREMENTS.md` §5) : O1, attente d'un avis ; O2, XEX non chiffrés
  fournis par l'utilisateur, sans clé ni déchiffrement dans le projet ; O3, ReXGlue
  utilisé tel quel.
- **Recommandation de l'audit** : O1 jusqu'à décision. J0 et J1 n'en dépendent pas.
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
  pour la configuration d'analyse (si les empreintes concordent), les correctifs du SDK
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

- **Statut** : Ouverte. Recommandation : **ReXGlue v0.11.0** (`ebac1cf`).
- **Options** :
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

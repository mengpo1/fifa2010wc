# Audit — Registre des risques

> Mission 001, révision « Linux prioritaire » — audit du 2026-11-21.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.
> Probabilité (P) et impact (Im) : F = faible, M = moyen, É = élevé.
> macOS ARM64 n'est plus une priorité. Ses risques sont regroupés en fin de document
> (section F), pour garder la compatibilité future en vue sans peser sur le chemin Linux.

## Vue d'ensemble

| ID | Risque | P | Im | Bloquant pour |
|---|---|---|---|---|
| R-01 | Déchiffrement des XEX et protections techniques | É | É | J2 et suivants |
| R-02 | Disque différent de celui du projet A : configuration d'analyse à revalider, ou à refaire (mis à jour après J0) | É | É | J2 |
| R-03 | Rendu du jeu défectueux sur le backend Vulkan | M | É | J3, J4 |
| R-04 | Instabilité de l'API ReXGlue, coût de transposition des correctifs | É | M | J2 |
| R-05 | Maturité du runtime ReXGlue sous Linux pour ce jeu | M | É | J3, J4 |
| R-06 | Longue traîne de défauts propres au jeu (code recompilé) | É | É | J4, J5 |
| R-07 | Fuite de ressources propriétaires | M | É | Tous |
| R-08 | Spécificités NixOS (FHS, dlopen, durcissement, CMake 4) | É | M | J1 |
| R-09 | Audio : XMA, flux, cadence | M | M | J4 |
| R-10 | Sauvegardes, profil, services XAM | M | M | J4, J5 |
| R-11 | Performances sous Linux | M | M | J4 |
| R-12 | Conformité des licences tierces | M | M | Distribution |
| R-13 | Dépendance à des projets portés par une seule personne | M | M | Long terme |
| R-14 | Hébergement du projet (clos) | — | — | — |
| R-15 | Dérive des versions de la chaîne de compilation | M | F | J1 |
| F-01 à F-04 | Risques macOS ARM64 (futur) | — | — | J6 |

---

## A. Juridique et données

### R-01 — Déchiffrement des XEX et protections techniques

- **[V]** ReXGlue déchiffre les XEX avec des clés intégrées, à la génération de code et à
  chaque lancement. Les projets A et B reposent sur ce mécanisme ; l'outil
  `xeximage.py` du projet A contient la clé en clair.
- **[V]** (J0, 2026-11-22) Les deux modules du disque de l'utilisateur sont chiffrés en
  AES et compressés en LZX, d'après leur en-tête en clair (*file format info*). Ce
  n'est plus une hypothèse : toute génération de code passera par l'image en clair des
  deux modules (`docs/reports/J0_IDENTIFICATION.md` §6).
- **[V]** (lecture de la source de ReXGlue v0.11.0, sans exécution) Un module non chiffré
  est accepté par `XEXImage::DecodeWith`. `XEXImage::Decode` dérive toutefois une clé de
  session à partir des clés intégrées avant tout décodage, même pour un module non
  chiffré.
- **[I]** Qualification juridique dans le pays de l'utilisateur. Pays : France, selon la
  déclaration de l'utilisateur du 2026-11-22.
- **Mitigation** : décision D-008 avant toute génération de code. Les jalons J0 et J1
  n'en dépendent pas. Le projet ne contient jamais de clé. Détails :
  `ISO_REQUIREMENTS.md` §5.
- **État (2026-11-22)** : l'utilisateur a choisi la voie technique O3 : ReXGlue tel
  quel, qui déchiffre à la génération de code et à chaque lancement. Ce choix **ne réduit
  pas le risque**. La qualification juridique des actes et la décision sur la contrainte
  de mission restent à obtenir avant toute exécution (`docs/DECISIONS.md`, D-008).

### R-02 — Disque différent de celui du projet A (mis à jour après J0, 2026-11-22)

- **[V]** Le projet A n'accepte que le disque Europe (En, Es, Nl), identifié par deux
  SHA-256. Ses 17 691 lignes de configuration d'analyse sont propres à ces binaires.
- **[V]** (J0) Le disque de l'utilisateur est un XGD2 PAL du titre `454108E4`, en
  version `0.0.0.3`, avec l'identifiant de média `6CCD3565`. Les SHA-256 de ses deux
  modules **diffèrent** de ceux du projet A (`docs/reports/J0_IDENTIFICATION.md`).
- **[I]** Identité ou différence du **code machine**. La différence d'empreintes ne
  permet pas de conclure. Le SHA-256 couvre tout le fichier : l'en-tête (identifiant de
  média, version, régions, clé de fichier chiffrée, signature) et des données chiffrées
  avec une clé propre au fichier. Un même code peut donc donner des fichiers différents
  (`J0_IDENTIFICATION.md` §3).
- **[V]** (J0) La disposition en mémoire concorde avec les trois valeurs publiées par le
  projet A dans `pc/config/default.toml` : `default.xex` chargé à `0x82000000`, fin de
  son image à `0x821F0000`, `fifadllzf.xex` chargé à `0x82300000`.
  - Toutes les adresses de la configuration d'analyse du projet A tombent dans les
    images des modules de l'utilisateur.
  - Condition **nécessaire, non suffisante** : ni le code ni la configuration ne sont
    établis comme identiques (`docs/reports/J0_IDENTIFICATION.md` §3.2).
  - La taille de l'image de `fifadllzf.xex` du projet A n'est pas publiée [I].
- **[I]** Région, version et identifiant de média du disque du projet A (non publiés).
- **Probabilité** : élevée qu'une revalidation soit nécessaire, puisque c'est certain.
  Probabilité d'une analyse complète à refaire : inconnue tant que le code n'est pas
  comparé.
- **Conséquence** :
  - la configuration d'analyse du projet A ne peut pas être supposée valable ;
  - il faut la revalider (débuts de fonctions, pointeurs de code, `setjmp`/`longjmp`,
    correctifs à adresses fixes `boot_fixes.cpp` et `lua_diagnostics.cpp`,
    `function_table_base`) ;
  - si la revalidation échoue, l'analyse est à refaire avec les outils du projet A, qui
    restent réutilisables.
- **Mitigation** (`docs/J2_PREREQUISITES.md` §3) :
  - comparaison de la disposition en mémoire, sans déchiffrement : **faite**,
    concordante ;
  - puis, seulement si D-008 le permet :
    - tests de compatibilité initiaux : C2.1 et contrôles ciblés. Ce n'est pas une
      preuve d'identité ;
    - validation spécifique avant toute réutilisation des adresses : régénérer avec les
      outils du projet A ses fichiers d'analyse et exiger qu'ils soient identiques ;
      vérifier une à une les adresses écrites à la main ;
  - ne jamais conclure sur le code à partir des seules empreintes des fichiers.

### R-07 — Fuite de ressources propriétaires

- Vecteurs : commit accidentel (XEX, code généré, captures), magasin Nix lisible par
  tous et transmissible à un cache, journaux de bogue contenant de la mémoire du jeu,
  artefacts de CI.
- **[V]** Le projet A bloque explicitement ces motifs dans son `.gitignore`, et son code
  généré reste local.
- **Mitigation** : D-007. `.gitignore` strict, dossier privé hors dépôt, aucune entrée
  de jeu dans une dérivation Nix pure, CI sans jeu, relecture des journaux avant partage.

### R-12 — Conformité des licences tierces

- **[V]** ReXGlue et Xenia : BSD 3-Clause. SDL3 : zlib [H]. extract-xiso : type BSD avec
  clause de publicité. Projet A : BSD 3-Clause. Projet B : MIT, notice au nom d'un autre
  auteur.
- **[I]** Configuration exacte de la copie de FFmpeg vendue avec ReXGlue (dépôt
  `wmarti/FFmpeg`, branche `xenia-ffmpeg-canary-full`). La licence LGPL ou GPL dépend des
  composants activés ; cela compte seulement en cas de distribution de binaires.
- **[V]** Le projet B versionne `Settings.exe` et un fichier `.wav` de provenance inconnue.
- **Mitigation** : D-010. Aucune reprise de binaire ni de ressource ; notices conservées ;
  inventaire des licences avant toute distribution.

## B. Technique — recompilation et runtime

### R-04 — Instabilité de l'API ReXGlue

- **[V]** README : « early development », API instable. Il y a 338 commits entre
  `bd833a2` (base du projet A) et v0.11.0, avec une réorganisation de l'arborescence
  (`src/graphics` → `src/gpu/xenos`, pilotes en modules dynamiques) et l'abandon de
  `generated/rexglue.cmake`.
- **[V]** v0.11.0 exige Clang ≥ 20 ; `bd833a2` se contentait de Clang ≥ 18.
- **Mitigation** : épingler un commit exact et garder les correctifs sous forme de série
  (comme le projet A) ; ne monter de version qu'à un jalon stable ; voir D-011.

### R-05 — Maturité du runtime ReXGlue sous Linux pour ce jeu

- **[V]** Linux amd64 est une cible de CI officielle. Les couches de base ont des
  variantes POSIX : mémoire, exceptions par signaux, fibres, threads, horloge.
- **[V]** Le SDK v0.11.0 compile sous Linux x86_64 (`LINUX_FEASIBILITY.md` §1.1).
- **[I]** Aucun des deux ports de FIFA n'a été exécuté sous Linux.
- **[H]** Les comportements sensibles à la cadence (vblank, threads invités, attentes
  actives), qui ont exigé le correctif 0004 sous Windows, peuvent différer sous Linux,
  dans un sens ou dans l'autre.
- **Mitigation** : J3 vise uniquement l'écran-titre, avec journaux détaillés ; on
  compare à Windows, et à Xenia comme oracle si nécessaire.

### R-06 — Longue traîne de défauts propres au jeu

- **[V]** Le projet A a dû ajouter des débuts de fonctions manqués, environ 17 700 lignes
  de pointeurs de code, `setjmp`/`longjmp` pour Lua et un contournement au démarrage.
- **[V]** Le projet B documente 32 sessions de débogage, dont des défauts introduits par
  ses propres déclarations de fin de fonction.
- **[H]** Des fonctions atteintes seulement par pointeur peuvent manquer à l'analyse et
  planter tard (modes de jeu rarement parcourus).
- **Mitigation** : critères de validation par parcours (`ROADMAP.md` §4), journalisation
  des appels non résolus, réutilisation des outils de rétro-ingénierie du projet A.

### R-09 — Audio

- **[V]** Le jeu passe par les exports XAudio de la console. Le runtime sert ces clients
  de rendu et décode le XMA avec sa copie de FFmpeg. La sortie hôte passe par SDL3, sur
  toutes les plateformes.
- **[I]** Qualité du décodage XMA pour les commentaires et l'ambiance de ce jeu ; absence
  de sous-alimentation (« underrun ») sous PipeWire ou PulseAudio.
- **Mitigation** : compteurs `IAudioSystem::GetStats` (sous-alimentations, latence)
  intégrés aux critères de J4.

### R-10 — Sauvegardes, profil, services XAM

- **[V]** Le projet A corrige l'énumération des sauvegardes (correctif 0008). Le projet B
  a trouvé un défaut de troncature des arguments 64 bits dans ReXGlue v0.10.
- **[H]** v0.11.0 a corrigé la troncature (le code de passage des arguments a été réécrit).
- **[V]** Xbox Live n'est pas pris en charge (problème connu du projet A).
- **Mitigation** : test « sauvegarder, quitter, relancer, recharger » dans les critères ;
  modes en ligne hors périmètre.

## C. Technique — plateforme Linux

### R-03 — Rendu sur le backend Vulkan

- **[V]** Le backend Vulkan existe (environ 23 000 lignes, contre 19 000 pour D3D12), et
  il est choisi par défaut hors Windows (`gpu.driver = any`).
- **[V]** Les deux contournements GPU propres à FIFA du projet A
  (`allow_invalid_fetch_constants`, `execute_unclipped_draw_vs_on_cpu`) existent aussi
  dans le chemin Vulkan.
- **[V]** Fonctionnalités Vulkan obligatoires : `independentBlend`,
  `fragmentStoresAndAtomics` et `vertexPipelineStoresAndAtomics`. Les geometry shaders
  sont facultatifs (chemin de repli).
- **[I]** Aucun des deux ports n'a documenté d'essai de FIFA sur Vulkan.
- **[H]** Des écarts propres au jeu sont possibles dans l'émulation de l'EDRAM et des
  « resolves », et entre les chemins de cibles de rendu (`fsi` ou cibles hôtes).
  Le projet B a dû régler des « readbacks » et des effets de post-traitement sous D3D12.
- **Mitigation** : à J3, comparer avec des captures de référence locales ; tester sur
  deux pilotes (Mesa RADV ou ANV, et NVIDIA propriétaire) ; essayer les deux chemins de
  cibles de rendu.

### R-08 — Spécificités NixOS

- **[V]** Vérifié pendant l'audit (`LINUX_FEASIBILITY.md` §5) :
  - SDL3 refuse de se configurer sans libXtst, que Nix n'apporte pas par transitivité ;
  - le durcissement `fortify` du compilateur enveloppé par Nix, combiné au `-Werror` de
    ReXGlue, fait échouer la compilation ;
  - le SDK précompilé dépend de GLIBC 2.38 et de la libstdc++ de GCC 13, et SDL3 y charge
    par `dlopen` une quinzaine de bibliothèques système.
- **[H]** Les autres options de durcissement (`zerocallusedregs`,
  `stackclashprotection`) peuvent coûter des performances sur le code recompilé.
- **Mitigation** : D-009. Compilation du SDK depuis les sources dans une dérivation
  Nix ; enveloppe qui fournit les bibliothèques chargées par `dlopen` ; durcissement
  réglé explicitement.

### R-11 — Performances

- **[V]** Le projet A annonce 60 i/s en match sous Windows et note que le jeu sollicite
  davantage le GPU que le processeur.
- **[V]** Linux x86_64 compile en modèle de code `large` (`-mcmodel=large`) pour les gros
  exécutables recompilés.
- **[I]** Coût réel du modèle `large` et du chemin Vulkan pour ce jeu.
- **Mitigation** : critère de J4 fixé à 30 i/s stables (cadence d'origine) ; 60 i/s
  est un objectif de J5.

### R-15 — Dérive de la chaîne de compilation

- **[V]** nixos-26.05 fournit clang 20.1.8 (exigé par ReXGlue v0.11.0), CMake 4.1.6 et
  GCC 15.3 par défaut.
- **[V]** La CI de ReXGlue compile avec clang 20 et la libstdc++ de GCC 13 sous
  Ubuntu 24.04.
- **[H]** Une libstdc++ plus récente (15.3) peut révéler des écarts. Les SDK
  précompilés y sont sensibles ; une compilation complète depuis les sources ne l'est pas.
- **Mitigation** : épingler nixpkgs (commit du canal) dans `flake.lock`.

## D. Organisation

### R-13 — Projets portés par une seule personne

- **[V]** Les projets A et B ont chacun un mainteneur principal. ReXGlue a un fondateur
  et des mainteneurs Linux et macOS nommés. XenonRecomp est inactif depuis environ
  15 mois.
- **Mitigation** : ne pas dépendre d'eux à l'exécution ; épingler les commits ; garder
  une copie de travail de ReXGlue avec nos correctifs.

### R-14 — Hébergement du projet (clos)

- **Clos** par D-012 : le projet dispose d'un dépôt dédié, `mengpo1/fifa2010wc`. Son
  `.gitignore` et sa CI peuvent être réglés pour D-007 sans gêner un autre projet.

---

## F. Risques macOS ARM64 (plateforme future, non prioritaire)

| ID | Risque | Faits et hypothèses |
|---|---|---|
| F-01 | Pages de 16 Kio | **[V]** Pris en charge par ReXGlue (`REX_PHYS_HOST_OFFSET`, documentation `runtime/memory.md`). **[I]** Effet sur les performances. |
| F-02 | Vulkan via MoltenVK | **[V]** Le code gère `VK_KHR_portability_subset`, et les geometry shaders sont facultatifs. **[H]** `vertexPipelineStoresAndAtomics`, obligatoire, doit être disponible sous MoltenVK sur Apple Silicon. **[I]** Écarts de rendu. |
| F-03 | Instructions vectorielles VMX128 sur ARM | **[V]** ReXGlue et XenonRecomp utilisent SIMDe pour ARM64. **[I]** Coût en performances. |
| F-04 | Signature et notarisation des applications | **[I]** Exigences de distribution locale, hors périmètre tant que Linux n'est pas jouable. |

**Règle de conception qui découle de F-01 à F-04** : aucun code du projet ne doit
supposer x86_64, Linux, des pages de 4 Kio ou un appel direct à Vulkan (voir D-006).

# Rapport de la phase A de J2 — point de revue PA-1

> J2, phase A (`docs/J2_PLAN.md` §3), sous l'autorisation PA-0 (D-015), 2026-11-23 et
> 2026-11-24. **Aucun fichier du jeu n'a été lu, produit ni requis** : toutes les étapes ont
> tourné en CI et dans le bac à sable de Nix, sur des données synthétiques ou sur la source
> publique de ReXGlue v0.11.0.
>
> PA-1 est un point de revue (`J2_PLAN` §2 et §3.9). Ce n'est pas un nouveau consentement :
> PJ2-3 est déjà accordée (D-015). **PB-0 n'est pas franchi** ; ce rapport dit ce qui reste
> à remplir (§5).
>
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Critères de sortie (`J2_PLAN` §3.9)

| Critère | État | Preuve |
|---|---|---|
| A1 à A6 et A8 fusionnées, chacune avec la CI verte | **Rempli** [V]. A8-bis (#24), ajoutée par l'arbitrage de A8, l'est aussi | §2 : chaque PR a fusionné après une CI verte sur sa tête exacte |
| A7 faite, ou son impossibilité documentée | **Faite** [V], fusion en attente (#26) | `docs/J2_A7_SYNTHETIC_CHAIN.md` ; contrôle `a7-synthetic-chain` |
| `nix flake check -L --no-update-lock-file` et `check_proprietary_data.py repo` passent sur `main` | **Réserve** (§4.1) : la CI de `main` a échoué deux fois sur un test Debug de ReXGlue, instable sous charge, et jamais sur un contrôle du projet | §4.1 |
| Aucun fichier du jeu lu ni requis | **Rempli** [V] | CI sans le jeu ; §3 |
| La série de correctifs ne touche ni le décodage des XEX, ni `excrypt`, ni les clés | **Rempli** [V] | Contrôle `sdk-patches` ; la série compte un correctif, `0001-function-table-base.patch` (A3) |
| Source de l'image décidée | **Rempli** [V] : M1 d'abord, M3 en repli, M2 non autorisée | Arbitrage de l'orchestrateur (revue 6021690700 de #18), acquis à la fusion de #18 avec l'accord du porteur du projet |
| Rapport de phase A rédigé | Ce document | — |

## 2. Étapes et livrables

| Étape | PR | Fusion | Apport | Contrôle Nix |
|---|---|---|---|---|
| A1 — Inventaire de ReXGlue v0.11.0 | #15 | 2026-11-23 | Sorties, journaux, chemins, validation d'adresses, variables d'environnement du SDK (`docs/J2_A1_SDK_INVENTORY.md`) | — |
| A2 — Besoin des correctifs du projet A | #17 | 2026-11-23 | 0001, 0004 et 0007 déjà en amont, 0006 en partie ; 0002 à essayer par configuration en phase B ; 0008 reporté à J4 (`docs/J2_A2_SDK_PATCHES.md`) | — |
| A3 — Base de la table de répartition | #19 | 2026-11-23 | Correctif `0001-function-table-base.patch` et 13 tests du SDK ; P-38 et P-39 corrigés (`docs/J2_A3_FUNCTION_TABLE.md`) | `sdk-patches`, tests du SDK |
| A4 — Contrôles du dossier privé | #16 | 2026-11-23 | `private_guard` (CP-1, CP-4) et procédure (`docs/J2_PHASE_B_CONTROLS.md`) | `private-guard-selftest` |
| A5 — Gabarit de configuration | #20 | 2026-11-23 | Gabarit du manifeste sans adresse, outil `private_project` ; P-40 à P-42 corrigés (`docs/J2_A5_CONFIG_TEMPLATE.md`) | `private-project-selftest` |
| A6 — Lacunes Linux | #23 | 2026-11-24 | Aucun changement du runtime ; confinement rejoué de bout en bout (`docs/J2_A6_LINUX_GAPS.md`) | `linux-confinement` |
| A7 — Chaîne sans données du jeu | #26 | en attente | ELF lié au SDK à partir de code généré ; deux défauts de construction corrigés (A7-1, A7-2) ; 1 615 cas Catch2 réussis (`docs/J2_A7_SYNTHETIC_CHAIN.md`) | `a7-synthetic-chain`, `cmake-skeleton` |
| A8 — Méthode de validation des adresses | #18 | 2026-11-23 | Pistes M1, M2, M3 comparées ; arbitrage : M1, M3 en repli, M2 non autorisée (`docs/J2_A8_ADDRESS_VALIDATION.md`) | — |
| A8-bis — Comparateur d'adresses | #24 | 2026-11-24 | `address_compare`, méthode M1 analytique ; P-43 à P-46 corrigés (`docs/J2_A8BIS_ADDRESS_COMPARE.md`) | `address-compare-selftest` |

CI de `main` après chaque fusion : verte pour #15, #16, #18, #19, #20 et #23. Après #17 et
#24, elle a échoué sur un test Debug de ReXGlue (§4.1).

## 3. Ce que la phase A n'a pas touché [V]

- **Aucun ISO, aucun XEX, aucune image, aucun code généré du jeu** n'a été lu ni écrit.
  Les entrées des contrôles sont synthétiques :
  - une image XDVDFS de deux fichiers texte (A6) ;
  - des adresses `0x8C01xxxx` (A8-bis) ;
  - les programmes de test PowerPC de la source de ReXGlue (A7) ;
  - les fixtures de test du SDK, inspectées en J1 (P-10).
- **Le déchiffrement reste celui de l'amont** (O3, D-015) : le contrôle `sdk-patches`
  refuse tout fichier des XEX ou de `excrypt` dans la série. La seule autre adaptation du
  paquet est une option de construction, `-DCMAKE_INSTALL_LIBDIR=lib` (A7-1, D-011).
- **Aucune adresse du projet A n'est versionnée comme configuration** (CP-7) : le gabarit
  A5 n'en a aucune.
- **Aucun binaire précompilé de provenance inconnue n'a été exécuté** : A7 n'utilise pas
  les binutils fournis par ReXGlue.

## 4. Réserves et limites à garder pour PB-0

### 4.1 Tests Debug de ReXGlue instables sous charge

- **Constat** [V] : la CI de `main` a échoué deux fois après une fusion, chaque fois sur un
  seul test du SDK construit en Debug (`rexglue-sdk-debug-tests`), jamais sur un contrôle
  du projet. Dans les deux cas, la même dérivation avait réussi sur la PR et en local.
  - Après #17 (run 45188167661) : « an unfocused window mutes only when asked »
    (`apu`), *Failed*.
  - Après #24 (run 45371847463) : « A profile flag wins over the all profiles flag »
    (`xam`, `content_package_test.cpp:166`), *SIGSEGV* après la dernière assertion, donc
    pendant la fermeture du dispositif de test.
  - En J1 déjà (P-17) : un test de synchronisation du noyau dépassait son délai sous
    charge, et un autre plantait.
- **Analyse en cours** [I] : reproduction locale sous charge, avec une trace d'appels. La
  piste étudiée est la sortie d'un thread invité qui touche encore le runtime alors que le
  test le détruit. Le résultat sera consigné ici.
- **Ce qui n'est pas fait** : aucun test n'est désactivé, ignoré ni relancé
  automatiquement pour obtenir une CI verte. Un job n'est relancé qu'une fois, à la main.

### 4.2 Limites des outils du dossier privé

- **Les chemins d'entrée sont contrôlés, puis ouverts par leur nom** (A8-bis,
  `address_compare`). Entre les deux, un processus concurrent qui modifie les liens du
  dossier privé peut faire lire un autre fichier : la fenêtre de concurrence demeure.
  Revue de l'orchestrateur 7127537347.
- **Le renommage d'un vrai dossier déjà ouvert n'est pas couvert** (A5 P-42, A8-bis
  P-46) :
  - les écritures sont ancrées par descripteur (`O_DIRECTORY | O_NOFOLLOW`) et refusent un
    lien ;
  - mais un descripteur ne fixe pas l'emplacement du dossier dans l'arborescence. Un
    processus du même utilisateur qui déplace ce dossier hors du dossier privé, pendant
    l'exécution, n'est pas arrêté.
- **Mesure qui en découle, pour PB-0** : l'accès au dossier privé reste limité à
  l'utilisateur (`0700`, CP-1). Aucun autre processus de cet utilisateur ne le modifie
  pendant une étape. Ces outils protègent contre une erreur de configuration, pas contre
  un processus malveillant du même utilisateur.

### 4.3 Confinement du système (A6)

- **L'objet de mémoire de l'invité reste dans `/dev/shm`** (A6 §5.1). Un espace de noms
  de montage privé n'est pas écrit ; c'est à décider si le besoin apparaît.
- **Les *core dumps* transmis par tube échappent à `ulimit -c 0`** (A6 §5.2, `core(5)`).
  - La vérification synthétique de `J2_PHASE_B_CONTROLS` §5 est un **prérequis de CP-4,
    à faire une fois sur la machine de l'utilisateur avant PB-0**, sans aucune donnée du
    jeu : relever `kernel.core_pattern` et `fs.suid_dumpable`, faire planter un shell,
    puis vérifier avec `coredumpctl` que rien n'est stocké.
  - À défaut, le porteur du projet décide d'un réglage de `coredump.conf`.
- **`linux-confinement` ne prouve pas un confinement universel** des écritures, ni le
  comportement de la génération de code sur un XEX.

### 4.4 Validation des adresses

- M1 n'établit que les niveaux N0 à N2. **Les valeurs de données restent N3, non
  vérifiées** (A8 §4).
- N2 vient d'un relevé d'examen manuel, dont `address_compare` contrôle la cohérence. Il
  ne le calcule pas à partir du code généré (A8-bis §3 et §6).

### 4.5 Chaîne de compilation (A7)

- A7 n'exerce ni `rexglue codegen` sur un XEX, ni `rexglue_project`, ni le chargement des
  modules à l'exécution. VMX128 (29 programmes de test), la taille du jeu et le Debug de
  l'hôte ne sont pas couverts.
- L'exécutable du jeu se configure depuis `nix develop`, avec un preset : toute autre
  valeur de `REXGLUE_LLD` arrête la configuration (A7-2).

### 4.6 Portée des essais

**Les tests synthétiques ne sont pas une garantie générale.** Ils montrent que les cas
prévus sont traités, pas qu'aucune autre mutation de l'arborescence, aucun autre format
de journal ni aucun autre comportement du jeu ne pose problème. Revues de l'orchestrateur
7127536477 et 7127537347.

## 5. État de PB-0

PB-0 (`J2_PLAN` §2) demande quatre conditions :

| Condition | État |
|---|---|
| Autorisation PJ2-3 expresse | Accordée le 2026-11-23 (D-015) |
| PA-1 franchi | **Ce rapport**, soumis à la revue de l'orchestrateur, puis du porteur du projet |
| Contrôles CP-1 à CP-7 exécutés et consignés (`J2_PREREQUISITES.md` §6) | **À faire sur la machine de l'utilisateur**, avec la vérification des *core dumps* (§4.3). Aucun ne lit le jeu, sauf le contrôle que `iso/` est en lecture seule |
| Méthode de validation des adresses décidée | Décidée : M1, M3 en repli, M2 non autorisée (§1) |

**Ce qui reste avant la phase B**, dans l'ordre :

1. la revue de ce rapport, et la fusion de A7 (#26) avec l'accord du porteur du projet ;
2. la décision sur la réserve du §4.1 ;
3. sur la machine de l'utilisateur, la procédure de `J2_PHASE_B_CONTROLS.md` §1 :
   préparation du dossier privé, `private_guard check-dir`, crochet de pré-commit
   (CP-1, CP-6), puis la vérification des *core dumps* (§4.3) et la recherche CP-3 dans
   le magasin ;
4. la consignation des résultats, sans contenu propriétaire (CP-5) ;
5. la décision PB-0 du porteur du projet.

**Aucune opération sur l'ISO ni sur les XEX n'a lieu avant cette décision.**

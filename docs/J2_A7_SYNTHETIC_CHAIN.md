# J2, étape A7 — Essai de la chaîne sans données du jeu

> Étape A7 de `docs/J2_PLAN.md` (§3.7), sous l'autorisation PA-0 (D-015).
> **Phase A : aucune donnée du jeu.** L'entrée est faite des programmes de test PowerPC de
> la source de ReXGlue v0.11.0 ; aucun XEX, aucune ISO, aucun fichier du jeu n'est lu.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Conclusion

- **Le critère de sortie de §3.7 est atteint** [V] : un ELF lié au SDK installé, à partir
  de code que l'outil `rexglue` installé a généré, sans aucune donnée du jeu. Le contrôle
  Nix `a7-synthetic-chain` le refait à chaque `nix flake check` (§3).
- **A7 a trouvé un défaut du paquet du SDK, corrigé ici** [V, §4]. Dans le paquet Nix, les
  emplacements des modules fournisseurs étaient faux
  (`${PACKAGE_PREFIX_DIR}//nix/store/…/lib/librexfilesystem.so`). Un hôte configuré par
  `rexglue_configure_target`, ce que fera l'exécutable du jeu, ne pouvait pas être lié.
  Le défaut aurait arrêté B5.
- **P-05 est reproduit, puis vérifié corrigé, dans un projet consommateur** [V, §3] :
  - avec `-DREXGLUE_LLD` vers le `ld.lld` enveloppé, toutes les dépendances du programme
    se résolvent dans le magasin ou parmi les bibliothèques copiées à côté de lui ;
  - avec le `lld` brut, le programme se construit, mais le contrôle des dépendances le
    refuse ;
  - sans `-DREXGLUE_LLD`, la configuration s'arrête sur le message du SDK. L'oubli ne
    passe donc pas inaperçu dans cet environnement.
- **P-07 tient pour l'hôte** [V] : les bibliothèques copiées à côté du programme sont
  identiques octet pour octet à celles du paquet. Le pilote Vulkan garde donc
  `vulkan-loader` dans son RUNPATH.
- **Le code généré s'exécute** [I] : résultat des 1 615 cas Catch2 à consigner après le passage du contrôle avec le SDK corrigé.
- **Limites** (§5) :
  - A7 n'exerce ni `rexglue codegen` sur un XEX, ni `rexglue_project`, ni le chargement
    des modules à l'exécution ;
  - les 29 programmes de test qui demandent VMX128 ne sont pas couverts ;
  - un essai sur des données synthétiques n'est pas une garantie générale.

## 2. Moyen

- **Entrée** : `tests/ppc/asm/*.s` de la source épinglée de ReXGlue v0.11.0 (`a3e1d82`,
  BSD-3-Clause), 190 programmes de test d'instructions PowerPC. Chacun porte ses valeurs
  d'entrée et ses valeurs attendues en commentaires (`#_ REGISTER_IN`,
  `#_ REGISTER_OUT`…). Ce ne sont pas des données du jeu ; l'adresse de chargement
  `0x82010000` est celle des tests d'amont (`cmake/ppc_test_pipeline.cmake`).
- **Assembleur** : les GNU binutils 2.46 de nixpkgs, compilés depuis les sources
  (`pkgsCross.ppc-embedded.buildPackages.binutils-unwrapped`).
  - Ils ne connaissent pas l'option `-mvmx128` ni les instructions VMX128 de la Xbox 360.
    161 programmes s'assemblent avec les options d'amont, moins `-mvmx128` ; 29 sont
    refusés.
  - La liste des refusés est versionnée (`tests/a7-chain/vmx128-tests.txt`). Le contrôle
    échoue si l'assembleur en refuse d'autres, ou en accepte un.
  - ReXGlue fournit des binutils déjà compilés, avec VMX128, dans `tools/binutils`
    (exécutables Linux et Windows). **A7 ne les exécute pas** : ce sont des binaires sans
    recette de construction dans la source, de provenance non vérifiée.
- **Génération** : `rexglue recompile-tests` du paquet du SDK
  (`src/rexglue/command/test_recompiler.cpp`). Il analyse chaque programme, émet le C++
  des fonctions et écrit des cas Catch2, qui comparent registres et mémoire aux valeurs
  attendues. La commande tourne avec `REX_LOG_FILE=false` et un `HOME` du bac à sable.
- **Hôte** : `tests/a7-chain/CMakeLists.txt`, un projet CMake hors de l'arbre du SDK.
  - Il trouve le paquet par `find_package(rexglue)`, comme le projet du jeu.
  - Il configure sa cible par `rexglue_configure_target`, la fonction qu'appelle
    `rexglue_setup_target` pour l'hôte du jeu (`lib/cmake/rexglue/rexglue_project.cmake`) :
    mêmes options de compilation et d'édition de liens, même éditeur de liens
    (`REXGLUE_LLD`), RUNPATH `$ORIGIN`, copie des bibliothèques du SDK et des modules
    fournisseurs à côté du programme.
  - Il lie `rex::kernel` et Catch2 3.14.0 de nixpkgs. L'arbre du SDK construit les mêmes
    tests avec son propre Catch2 (`tests/ppc/CMakeLists.txt`, désactivé par défaut :
    `REXGLUE_BUILD_PPC_TESTS=OFF`).

## 3. Contrôle `a7-synthetic-chain`

`nix/checks.nix`, dans le bac à sable de Nix, sous l'utilisateur de construction :

| Étape | Ce qui est vérifié |
|---|---|
| 1. Assemblage | 161 programmes sur 190 ; les 29 refusés sont exactement la liste VMX128 |
| 2. `rexglue recompile-tests` | Code de sortie 0 ; au moins un cas Catch2 par programme (1 615 cas) |
| 3. Paquet du SDK | Aucun `${PACKAGE_PREFIX_DIR}//` dans les fichiers CMake du paquet ; chaque emplacement de module de `rexglueModules-Release.cmake` existe (§4) |
| 3. Hôte | Configuration et construction en Release avec `-DREXGLUE_LLD=<ld.lld enveloppé>` ; `build.ninja` porte `--ld-path=` vers ce fichier |
| 4. Dépendances | `$ORIGIN` dans le RUNPATH ; `ld.so --list` réussit, sans « not found », et chaque bibliothèque se résout dans `/nix/store` ou dans le dossier du programme ; interpréteur dans le magasin |
| 4. Copies | Chaque bibliothèque copiée à côté du programme est identique à celle du paquet ; `librexgpu-xenos-vulkan.so` a `vulkan-loader` dans son RUNPATH (P-07) |
| 5. Exécution | Les cas Catch2 passent ; rapport JUnit conservé |
| 6a. Témoin | Sans `-DREXGLUE_LLD`, la configuration échoue avec « ReXGlue links with lld » |
| 6b. Témoin | Avec le `lld` brut, le programme se construit et le contrôle des dépendances le refuse (P-05) |

- Les témoins (6a, 6b) n'utilisent qu'un programme, `instr_add`, pour rester courts.
- **La sortie ne garde que des journaux et des rapports** : aucune source générée, aucun
  objet, aucun programme. `chain.txt` résume chaque étape.
- Le contrôle est aussi recueilli comme preuve par la CI (`.github/workflows/ci.yml`).

## 4. Constat A7-1 : emplacements des modules dans le paquet du SDK [V]

- **Symptôme** au premier passage du contrôle :

  ```
  ninja: error: '/nix/store/…-rexglue-sdk-0.11.0/nix/store/…-rexglue-sdk-0.11.0/lib/librexfilesystem.so',
  needed by 'a7_ppc_tests', missing and no known rule to make it
  ```

- **Cause** :
  - le crochet CMake de nixpkgs passe des dossiers d'installation absolus, dont
    `-DCMAKE_INSTALL_LIBDIR=$out/lib` (`pkgs/by-name/cm/cmake/setup-hook.sh:78`) ;
  - ReXGlue les joint à son préfixe : `"\${PACKAGE_PREFIX_DIR}/${_module_dir}/…"`
    (`cmake/rexglue_install.cmake:78`), et `${PACKAGE_PREFIX_DIR}/@CMAKE_INSTALL_LIBDIR@`
    dans `cmake/rexglueConfig.cmake.in:52,60` (macOS seulement) ;
  - les dix modules fournisseurs de `rexglueModules-Release.cmake` pointaient donc vers un
    chemin inexistant. Les autres cibles importées (`rexglueTargets-release.cmake`) sont
    écrites par `install(EXPORT)`, qui gère les dossiers absolus : elles étaient justes.
- **Pourquoi rien ne l'avait vu** : les tests du SDK tournent dans son arbre de
  construction, et le contrôle `cmake-skeleton` ne fait que `find_package`, qui ne lit
  pas l'emplacement des modules. Seul un hôte qui copie les modules le demande.
- **Correctif** (`nix/rexglue-sdk.nix`) : `-DCMAKE_INSTALL_LIBDIR=lib`, placé après les
  options du crochet, qu'il remplace. Le paquet n'a qu'une sortie : le dossier relatif
  installe au même endroit. **Aucun fichier du SDK n'est modifié** ; la série de
  correctifs reste celle de A3.
- **Régression** : l'étape 3 du contrôle refuse un `${PACKAGE_PREFIX_DIR}//` et vérifie
  que chaque emplacement de module existe ; le paquet d'avant le correctif échoue aux
  deux.

## 5. Limites

- **Pas de XEX** : `rexglue codegen` sur un manifeste, `rexglue_project` et
  `rexglue_setup_target` ne sont pas exercés. `recompile-tests` charge les programmes par
  un module factice (`StubModule`), sans chargeur XEX, sans `.pdata`, sans importations ;
  l'analyse et la validation d'un XEX ne passent qu'en phase B.
- **Pas d'exécution des modules** : les modules fournisseurs sont copiés et contrôlés,
  mais le programme ne les charge pas, et rien ne tourne sur Vulkan.
- **Pas de VMX128** : 29 des 190 programmes d'amont, dont toutes les instructions
  vectorielles `…128`, `lvlx`, `lvrx`, `stvlx` et `stvrx`, ne sont pas couverts.
- **Taille** : quelques Mio de code généré, loin de la taille du jeu. Les limites de
  l'édition de liens liées au modèle de code `large` (`rexglue_target.cmake`) ne sont pas
  approchées.
- **Release seulement** ; la configuration Debug n'est pas construite.
- Un essai sur des données synthétiques ne garantit pas le comportement sur le jeu.

## 6. Effets sur la suite

- **B5** (`J2_PLAN` §4.5) : le projet du jeu se configure avec
  `-DREXGLUE_LLD=$REXGLUE_LLD` (`nix develop`) et lie à travers `rexglue_setup_target`,
  qui appelle `rexglue_configure_target`. A7 montre que ce chemin fonctionne avec le
  paquet corrigé, et que l'oubli de `-DREXGLUE_LLD` arrête la configuration.
- Les constats P-05 et P-07 de `reports/J1_VALIDATION.md` §6 sont vérifiés pour un hôte,
  et non plus seulement pour le SDK.

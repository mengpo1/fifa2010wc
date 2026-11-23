# Rapport de validation — Jalon J1 : infrastructure native Linux/NixOS

> Mission 002, 2026-11-21. Branche `claude/j1-linux-nix-infra`, issue de `main` au commit
> `9869c30` (fusion de la PR #1). Aucune ressource du jeu n'a été utilisée, lue, produite
> ou déchiffrée. Le travail s'arrête après J1 : J2 n'est pas commencé.
>
> Règle de ce rapport : chaque résultat renvoie à une commande exécutée et à son journal.
> Ce qui n'a pas pu être exécuté figure à part, au §7.
>
> Complément du 2026-11-22 : résultats obtenus par l'utilisateur sur son hôte NixOS
> (§7.1), et fusion de la PR #2 sur `main` (§8).

## 1. Synthèse

| Critère (`docs/ROADMAP.md` §4) | Statut | Preuve |
|---|---|---|
| C1.1 — Le SDK se compile depuis un dépôt propre par une seule commande Nix | **Validé** (environnement Nix sur Ubuntu) | §4.3 : `nix build .#rexglue-sdk`, code de sortie 0 |
| C1.2 — Les tests unitaires du SDK passent | **Validé** en bac à sable Nix : Release 2 213 réussis, 0 échec, 10 sautés ; Debug 2 232 réussis, 0 échec, 2 sautés (raisons au §4.4) ; sur l'hôte NixOS de l'utilisateur : Debug 2 234 tests, 0 échec, 2 sautés (§7.1) | §4.4 : rapport JUnit installé avec le SDK ; §7.1 |
| C1.3 — `rexglue` s'exécute sans `nix-ld` ni `steam-run` | **Validé** dans le bac à sable Nix, sans aucun dossier de bibliothèques FHS, avec un contrôle ELF strict (§4.10) ; sur l'hôte NixOS de l'utilisateur, `rexglue --help` affiche son aide ; le code de sortie n'est pas visible dans la sortie transmise (§7.1) | §4.5 : contrôles `rexglue-cli-runs` et `elf-deps-check-selftest` ; §7.1 |
| C1.4 — Le pilote Vulkan trouve le GPU | **Validé sur l'hôte NixOS de l'utilisateur** : la sonde trouve une AMD Radeon 860M (RADV KRACKAN1, Mesa 26.1.8) avec les trois fonctions requises par ReXGlue (§7.1). Le journal d'initialisation du pilote Vulkan Xenos lui-même ne peut venir qu'avec le jeu, à J3 | §4.7 ; §7.1 |
| C1.5 — Aucune donnée du jeu requise ni présente | **Validé**, avec un contrôle avant commit qui lit l'index (§4.10) | §4.6 : contrôles du dépôt, de la clôture Nix et du hook |

Commande de synthèse, rejouée sur l'arbre final de la branche : `nix flake check -L` →
« all checks passed! », code de sortie 0. Les 7 contrôles sont `rexglue-sdk`,
`rexglue-sdk-debug-tests`, `rexglue-cli-runs`, `elf-deps-check-selftest`,
`cmake-skeleton`, `proprietary-data-source` et `proprietary-data-closure` ; les paquets et l'environnement
`devShells.default` sont évalués. La même suite a réussi en CI GitHub (§4.9). Les résultats des tests sont installés avec chaque SDK
(`share/rexglue-sdk/test-results/`), et les rapports de contrôle sont dans les sorties
des dérivations de contrôle.

## 2. Environnement d'exécution

| Élément | Valeur |
|---|---|
| Système hôte | Ubuntu 24.04.5 LTS dans un conteneur (noyau Linux 6.18.44-fc, x86_64). **Ce n'est pas NixOS** |
| Processeur, mémoire | 4 processeurs virtuels Intel Xeon à 2,30 GHz, 15 Gio |
| Nix | 2.34.6 ; `sandbox = true`, `sandbox-fallback = true` (voir P-09) |
| GPU | Aucun : ni `/dev/dri`, ni pilote Vulkan, ni `/run/opengl-driver` |
| Virtualisation | Pas de `/dev/kvm` : aucun test de machine virtuelle NixOS possible |

## 3. Versions utilisées

Le détail et les justifications figurent dans `docs/DEPENDENCIES.md`. Points essentiels :

| Composant | Version, épinglage |
|---|---|
| nixpkgs | NixOS 26.05, publication `26.05.14894.ab5c18fdedfc`, révision `ab5c18fdedfc8f9bbc9d773f10a540790e2787a7`, narHash `sha256-xVwloUjz7paCDnvN5dkrasmAGV+O6uyRUPFHxv2w3VA=` |
| ReXGlue | v0.11.0, révision `a3e1d82678ca20d68d4837a8e9ee4652ff073745` avec sous-modules, narHash `sha256-uSyEi0ou+ixZCd7pjOrvfkVy8mSly1ys5Tev6xjdCQ0=` |
| Compilateur | clang 20.1.8 (`llvmPackages_20.stdenv`), libstdc++ de GCC 15.3.0, glibc 2.42 |
| Éditeur de liens | `ld.lld` 20.1.8, **enveloppé** par Nix (`llvmPackages_20.bintools`, voir P-05) |
| Construction | CMake 4.1.6, Ninja 1.13.2 |
| Vulkan | vulkan-headers, vulkan-loader et vulkan-tools 1.4.341.0 ; VMA 3.3.0 |
| CI | `actions/checkout` v7.0.1, `cachix/install-nix-action` v32.0.0, `actions/upload-artifact` v7.0.2 (SHA de commit), Nix 2.34.6 |

## 4. Travaux, commandes et résultats

### 4.1 Documentation de la PR #1

| Étape | Commande, action | Résultat |
|---|---|---|
| Contrôle des renvois | Script Python : chaque identifiant D-, R-, F- et C- cité doit être défini, chaque référence de section doit exister | 14 décisions, 19 risques, 23 critères, tous définis ; une référence imprécise (« §3.5 ») corrigée |
| Contrôle de fond | Relecture croisée | Une incohérence corrigée : la transposition des correctifs du SDK figurait en J1 dans SUMMARY, mais en J2 dans ROADMAP. Elle est remise en J2 |
| Décision D-011 | Mise à jour des documents | D-011 « Acceptée », épinglée sur `a3e1d82` (voir P-01) |
| Fusion | Autorisation explicite de l'utilisateur, puis fusion classique | PR #1 fusionnée : `9869c30` |

### 4.2 Épinglage

```bash
git ls-remote https://github.com/rexglue/rexglue-sdk 'refs/tags/v0.11.0*'
```

Résultat : `a3e1d82678ca20d68d4837a8e9ee4652ff073745 refs/tags/v0.11.0`. Voir P-01.

```bash
nix flake lock
```

Résultat : les deux entrées sont verrouillées (révision et narHash ci-dessus).

### 4.3 Compilation du SDK depuis les sources (C1.1)

```bash
nix build .#rexglue-sdk -L
```

La dérivation (`nix/rexglue-sdk.nix`) compile ReXGlue et ses sous-modules dans le bac à
sable Nix, sans réseau, avec `REXGLUE_BUILD_TESTS=ON`, puis exécute les tests
(`checkPhase`).

| Essai | Durée | Résultat | Cause, correction |
|---|---|---|---|
| 1 | 25 s | Échec à la configuration | P-02 : contrôle des sous-modules par `.git` |
| 2 | 39 s | Échec à la configuration | P-03 (SDL3 lit le marqueur `.git`) et P-04 (`xdmcp` manquant) |
| 3 | 5 min 49 s | Compilation réussie (1 472 étapes), échec des tests | P-05 : `libX11-xcb.so.1` introuvable par les tests |
| 4 | 5 min 51 s | Compilation réussie, échec des tests | P-05 : `libstdc++.so.6` introuvable (cause réelle : `ld.lld` non enveloppé) |
| 5 | 6 min 56 s | **Tests : 2 223, 0 échec**, échec en phase de correction | P-06 : `libsteam_api.so` réclamée par SDL3 |
| 6 | 6 min 51 s | **Succès** (code 0) | — |
| 7 | 12 min 11 s, Release et Debug en parallèle, dans `nix flake check` | **Succès** : Release 2 223 tests, Debug 2 234 tests, 0 échec | P-07 : `appendRunpaths` pour le pilote Vulkan, défaut révélé par le contrôle C1.3 sur l'essai 6 |

Produit final (essai 7) : `/nix/store/av4svay3hp9k1f4vh210nwa7cx3gbdsd-rexglue-sdk-0.11.0`,
qui contient l'outil `bin/rexglue`, les bibliothèques et modules du SDK, et les
résultats des tests. L'essai 6 (`k79py9vw…`, 49 Mio, 20 bibliothèques partagées) avait
les mêmes tests ; il manquait seulement le RUNPATH du pilote Vulkan (P-07).

### 4.4 Tests du SDK (C1.2)

Commande exécutée dans la `checkPhase` de la dérivation :

```bash
ctest --output-on-failure --no-tests=error -j "$NIX_BUILD_CORES" --output-junit ctest-junit.xml
```

Résultats des SDK finaux (essai 7), lus dans le rapport JUnit et le journal CTest
installés avec chacun (`share/rexglue-sdk/test-results/ctest-junit.xml` et `ctest.log`) :

| Mesure | SDK Release (`rexglue-sdk`) | SDK Debug (`rexglue-sdk-debug-tests`) |
|---|---|---|
| Tests | 2 223 (`tests="2223"`) | 2 234 (`tests="2234"`) |
| Réussis | 2 213 | 2 232 |
| Échecs | 0 (`failures="0"`) | 0 (`failures="0"`) |
| Sautés | 10 (`skipped="10"`) | 2 (`skipped="2"`) |
| Durée CTest | 55,38 s | 93,14 s |

La build Debug compte 11 tests de plus : ils ne sont enregistrés qu'en Debug. Les essais
5 et 6 avaient donné le même résultat pour la Release (2 223 tests, 0 échec, 10 sautés).

Les 10 tests sautés et leur raison, lue dans le source des tests :

| Tests | Raison (message `SKIP` du test) | Conséquence |
|---|---|---|
| 8 tests d'ordre des verrous (#78, #187, #741, #976, #1124, #1258, #1753, #1965) | « lock order is checked in debug builds only » : la dérivation compile en Release | Exécutés par le contrôle `rexglue-sdk-debug-tests` (SDK en Debug) : **les 8 réussissent** ; aucun n'est sauté en Debug |
| #236 « HostStat names the entry as the folder holds it » | « the host distinguishes names by case » | Sans objet sous Linux (système de fichiers sensible à la casse) |
| #1637 « A write to a watched host page unprotects it by the access of every guest page » | « the host page is not larger than a guest page » | Sans objet sur x86_64 (pages de 4 Kio) ; pertinent pour macOS ARM64 (J6) |

### 4.5 Exécution de l'outil sans `nix-ld` ni `steam-run` (C1.3)

Contrôle `rexglue-cli-runs` (`nix/checks.nix`), exécuté dans le bac à sable Nix :

1. il échoue si `/lib`, `/lib64`, `/usr/lib` ou `/usr/lib64` existent, ce qui prouve
   l'absence de dossier FHS et l'activité réelle du bac à sable (P-09) ;
2. il vérifie que l'interpréteur ELF de `rexglue` est dans `/nix/store` ;
3. il résout, avec `ld.so --list`, toutes les dépendances de chaque fichier ELF du SDK
   (`tools/check_elf_deps.sh`), et échoue si `ld.so --list` sort avec un code non nul,
   si une dépendance est introuvable ou si elle est hors de `/nix/store` (version stricte
   depuis la revue, §4.10) ;
4. il vérifie la présence de `vulkan-loader` dans le RUNPATH de `libSDL3.so.0` et de
   `librexgpu-xenos-vulkan.so`, qui chargent `libvulkan.so.1` par `dlopen` ;
5. il exécute `rexglue --help` et exige le code de sortie 0.

Premier passage : échec à l'étape 4 pour `librexgpu-xenos-vulkan.so` (P-07). Après
correction, **toutes les étapes réussissent**. Extrait du rapport du contrôle
(`report.txt` dans la sortie de `rexglue-cli-runs`) :

```
== Sandbox root (no FHS library folders expected)
bin build dev etc nix proc tmp
no /lib, /lib64, /usr/lib or /usr/lib64
== Interpreter: /nix/store/pagq7gjgxqbi09g0091x2cxwq2kwxyx8-glibc-2.42-103/lib/ld-linux-x86-64.so.2
== Dynamic dependencies of every ELF file of the SDK
21 ELF files, every dependency resolved inside /nix/store
libSDL3.so.0: vulkan-loader on RUNPATH
librexgpu-xenos-vulkan.so: vulkan-loader on RUNPATH
== /nix/store/av4svay3hp9k1f4vh210nwa7cx3gbdsd-rexglue-sdk-0.11.0/bin/rexglue --help
exit status 0
ReXGlue v0.11.0.0-dev.unknown Recompilation Toolkit
```

Hors bac à sable, dans `nix develop` sur l'hôte : `rexglue --version` affiche
`0.11.0.0-dev.unknown`, avec le binaire du SDK pris dans `/nix/store`.

### 4.6 Données propriétaires (C1.5)

| Contrôle | Commande | Résultat |
|---|---|---|
| Tests du script de contrôle | `python3 -I tools/test_check_proprietary_data.py` | 16 tests, tous réussis, dont 4 sur le mode `staged` ajoutés après la revue (§4.10) |
| Fichiers suivis | `python3 -I tools/check_proprietary_data.py repo` | « OK: 28 files checked, no proprietary data found » (arbre final) |
| Fichiers indexés | `python3 -I tools/check_proprietary_data.py staged` | « OK: 21 files checked, no proprietary data found » (les 21 fichiers ajoutés par J1). Depuis la revue, ce mode lit le contenu de l'index (§4.10) |
| Source du flake (bac à sable) | contrôle `proprietary-data-source` | « OK: 29 files checked, no proprietary data found » sur l'arbre final ; les 16 tests du script passent aussi dans le bac à sable (« Ran 16 tests », avec `git` fourni au contrôle) |
| Clôture Nix (SDK, sonde) et source de ReXGlue | contrôle `proprietary-data-closure` | 276 chemins du magasin analysés : « OK: 46121 files checked, no proprietary data found » |
| Hook pre-commit, de bout en bout | Dépôt jetable : un commit propre, puis un fichier à signature XEX sous un nom anodin, puis une `.iso` forcée (`git add -f`) | Commit propre accepté ; les deux autres refusés (code 1) ; un seul commit dans l'historique |
| Workflow CI | `actionlint` 1.7.12 (nixpkgs épinglé) | Aucun signalement |

Règles appliquées par `tools/check_proprietary_data.py` : extensions interdites (ISO, XEX,
archives et médias du jeu, paquets de contenu), dossiers privés ou générés, taille
maximale de 1 Mio, signatures de contenu (XEX, STFS, disque XDVDFS aux décalages des
partitions XGD), jetons hexadécimaux de 128 bits (taille d'une clé AES), marqueurs du
code généré par `rexglue codegen`. Deux fixtures de test de ReXGlue sont autorisées par
chemin **et** empreinte (P-10).

### 4.7 Sonde Vulkan (C1.4)

```bash
nix run .#vulkan-probe
```

| Exécution | Résultat |
|---|---|
| Dans cet environnement | « vkCreateInstance: Found no drivers! », code 4 : aucun périphérique |
| Validation de l'outil avec lavapipe (Mesa 26.1.8, implémentation logicielle), `VK_DRIVER_FILES=…/lvp_icd.x86_64.json` | « llvmpipe (LLVM 21.1.8, 256 bits) », type `PHYSICAL_DEVICE_TYPE_CPU`, API 1.4.354 ; les trois fonctionnalités exigées par ReXGlue sont présentes ; classé « logiciel, pas un GPU », code 3 |

La sonde fonctionne, mais **C1.4 reste non vérifié** : un rastériseur logiciel n'est
pas un GPU compatible.

### 4.8 Squelette CMake (élément 9)

Contrôle `cmake-skeleton` : `cmake --preset linux-amd64-release` dans le bac à sable,
contre le paquet du SDK : **réussi** (« Configuring done », « Build files have been
written »). Le journal indique `Found ReXGlue SDK 0.11.0.0-dev.unknown`, la couche
`platform/linux` et « Host executable: not built before J2 ». La même configuration
réussit dans `nix develop` sur l'arbre de travail. Un avertissement sur
`CMAKE_EXPORT_COMPILE_COMMANDS`, variable inutilisée faute de cible, a été supprimé en
retirant cette variable du préréglage.

Contenu : `CMakeLists.txt` (C++23, Clang ≥ 20, choix de la couche plateforme, refus
explicite de macOS avant J6, `find_package(rexglue 0.11 CONFIG REQUIRED)`) et
`CMakePresets.json` (`linux-amd64-debug`, `-release`, `-relwithdebinfo`). Aucun
exécutable n'est construit avant J2.

### 4.9 CI Linux (élément 12)

`.github/workflows/ci.yml` : contrôle des données sur les fichiers suivis, installation de
Nix 2.34.6, `nix flake metadata --no-update-lock-file`, `nix flake check -L`, collecte
des preuves (rapports des tests, des contrôles et de la sonde) publiées en artefact.
Le workflow passe `actionlint` 1.7.12.

Première exécution sur GitHub, sur la PR #2, commit `f9d8d46` : job `linux-x86_64`
(exécution 44956145051), du 2026-11-21 22:19:31 au 22:37:17 UTC, soit 17 min 46 s,
conclusion **success**. Extraits du journal du job :

| Élément | Ligne du journal |
|---|---|
| Tests du SDK Release | « rexglue-sdk> 100% tests passed, 0 tests failed out of 2223 », « Total Test time (real) = 66.22 sec » |
| Clôture Nix | « proprietary-data-closure> OK: 46121 files checked, no proprietary data found » |
| Synthèse | « all checks passed! » |
| Sonde Vulkan (informative) | « vkCreateInstance: Found no drivers! », « probe exit status: 4 » : les machines hébergées par GitHub n'ont pas de GPU |
| Preuves | Artefact `j1-evidence` publié (302 853 octets) |

Le point d'accès utilisé pour lire le journal ne renvoie que ses 5 000 dernières lignes ;
les lignes des tests Debug et de la première étape sont plus anciennes. Leur réussite
reste établie : « all checks passed! » exige celle du contrôle
`rexglue-sdk-debug-tests`, et la conclusion **success** du job celle de chaque étape.

### 4.10 Corrections après la revue de l'orchestrateur (PR #2)

La revue, « conforme sous réserves, fusion non autorisée à ce stade », relève deux
défauts. Chacun a été reproduit avant correction, puis couvert par un test de
non-régression.

**Défaut 1 : le mode `staged` lisait l'arbre de travail (P-15).**

Reproduction avant correction, dans un dépôt jetable :

```bash
printf 'XEX2\0\0\0\0' > asset.dat && git add asset.dat && printf 'clean text\n' > asset.dat
python3 -I tools/check_proprietary_data.py staged
```

L'index contenait la signature `XEX2`, l'arbre de travail du texte propre. Résultat :
« OK: 1 files checked », code 0 : le contenu indexé, celui qui aurait été commité,
passait.

Correction : `check_staged()` lit la liste des fichiers ajoutés, copiés, modifiés ou
renommés dans l'index, prend l'objet de chacun avec `git ls-files --stage`, l'extrait
avec `git cat-file blob` dans un dossier temporaire, à son chemin dans le dépôt, puis
applique les mêmes règles qu'aux autres fichiers. Les liens symboliques et les
sous-modules n'ont pas de contenu propre et sont ignorés.

Preuve de non-régression (`tools/test_check_proprietary_data.py`, classe
`StagedModeTest`, dépôt Git temporaire isolé de toute configuration globale) :

| Test | Vérifie |
|---|---|
| `test_staged_data_is_caught_when_the_working_tree_is_clean` | Contenu XEX indexé, arbre de travail propre : refusé (le cas du défaut) |
| `test_unstaged_working_tree_change_is_not_what_is_committed` | Index propre, donnée seulement dans l'arbre de travail : accepté, car ce n'est pas le contenu du commit |
| `test_staged_name_rules_still_apply` | Une `.iso` forcée dans l'index reste refusée |
| `test_deleted_files_are_not_checked` | Une suppression indexée n'est pas analysée |

Résultat après correction : « Ran 16 tests … OK », en local et dans le bac à sable
(`proprietary-data-source`, `git` fourni au contrôle). Le même scénario est désormais
refusé : « asset.dat: XEX executable signature b'XEX2' at offset 0 », code 1.

**Défaut 2 : le contrôle ELF masquait l'échec de `ld.so --list` (P-16).**

Reproduction avant correction : un fichier ELF tronqué à 64 octets (en-tête d'une
bibliothèque du SDK), placé dans le magasin avec `nix store add-file`. `ld.so --list`
sort avec le code 127 (« cannot read file data »), mais l'ancienne logique l'accepte :
la ligne d'erreur commence par `/nix/store/`, donc elle ne contient ni « not found »
ni chemin hors du magasin. Hors du magasin, le même fichier était refusé, mais par
hasard, par le filtre « chemin hors du magasin » : c'est pourquoi la preuve utilise des
fichiers du magasin.

Correction : `tools/check_elf_deps.sh` fait échouer un fichier dès que `ld.so --list`
sort avec un code non nul, et affiche ce code et le message du chargeur. Il échoue aussi
si une dépendance est introuvable ou hors de `/nix/store`, ou si aucun fichier ELF n'est
fourni. Les 21 fichiers ELF du SDK rendent tous 0 avec `ld.so --list` (vérifié un par
un) : aucun traitement d'exception n'est nécessaire. `rexglue-cli-runs` utilise ce
script.

Preuve de non-régression : contrôle `elf-deps-check-selftest`, sur des fichiers placés
dans le magasin (dérivations `elf-sample-truncated.so` et `elf-sample-missing-needed.so`,
taillées ou dérivées d'une bibliothèque du SDK, sans aucune donnée du jeu) :

| Cas | Résultat |
|---|---|
| Les 21 fichiers ELF du SDK | Acceptés : « 21 ELF files, every dependency resolved inside /nix/store » |
| ELF tronqué | Refusé : « exited with status 127 » |
| Bibliothèque avec une dépendance inexistante (`patchelf --add-needed`) | Refusée : « exited with status 127 » |
| Un fichier défectueux parmi des fichiers sains | Refusé : « FAIL: 1 of 2 ELF files » |
| Appel sans fichier | Refusé (erreur d'usage) |

Relance complète : `nix flake check -L` → « all checks passed! », code 0, en 1 min 42 s
(les deux SDK étaient déjà construits ; seuls les contrôles modifiés ont été rejoués).

**CI du commit `25fdd71` : échec d'un test Debug du SDK (P-17).**

Le job `linux-x86_64` (exécution 44987255472) échoue au bout de 41 min, contre 18 min
pour les deux passages précédents. Un seul test sur 2 234 échoue, dans le contrôle
`rexglue-sdk-debug-tests` : « XamGetOverlappedResult sees the event set once the result
is complete (Timeout) ». Le dispositif de test exige que ce test finisse en 20 s
(`kernel_fixture.cpp:341`, `CHECK( finished_in_time )`) ; CTest l'arrête à 60 s.

Faits relevés dans le journal du job :
- le test fait 20 000 allers-retours entre deux fils invités synchronisés par attente
  active (`SpinUntil`, `tests/unit/kernel/overlapped_test.cpp`) ;
- au même moment, la CI compilait le SDK Release (lignes « rexglue-sdk> [1416/1472] » au
  milieu des tests Debug) : les deux dérivations du SDK étaient construites en même
  temps, chacune avec 4 tâches, sur les 4 processeurs virtuels de la machine ;
- le SDK signale « Too few processor cores - scheduling will be wonky », et le fil invité
  reste « still running » pendant plus de 40 s ;
- les tests Debug durent 269 s, contre 93 s en local.

Mesures locales :
- sans contention, ce test dure 1,65 s (passage Debug réussi) ;
- essai de reproduction : SDK Debug recompilé et testé pendant que 4 boucles de calcul
  occupent les 4 processeurs. Le test de la CI **passe** (1,41 s), mais un **autre**
  test de synchronisation du noyau échoue : « A KeReleaseMutant by the old owner after a
  KeInitializeMutant is refused », SIGSEGV en `tests/unit/kernel/sync_test.cpp:855`
  (99 % réussis, 1 échec sur 2 234).

Conclusion. Le dépassement de délai précis de la CI n'est pas reproduit, mais deux échecs
différents des tests de synchronisation du noyau de ReXGlue apparaissent tous deux sous
contention processeur, et jamais sans elle (2 CI et 3 passages locaux réussis). La
dérivation Debug de `25fdd71` est identique à celle des deux CI réussies : le changement
de la PR n'en est pas la cause. Ce qui expose ce contrôle à la contention, c'est la
construction simultanée des deux SDK par `nix flake check`.

Correction : la dérivation `rexglue-sdk-debug-tests` référence la sortie du SDK Release
(`FIFA2010WC_BUILT_AFTER`). Nix construit donc toujours le SDK Debug après le Release, en
local comme en CI, quel que soit `max-jobs`. Vérifié avec `nix derivation show` : la
dérivation Release figure parmi les entrées de la dérivation Debug. Aucun test n'est
sauté, désactivé ni relancé automatiquement.

Vérification locale du même contrôle après correction :
`nix build .#checks.x86_64-linux.rexglue-sdk-debug-tests` → code 0, en 8 min 35 s ;
« 100% tests passed, 0 tests failed out of 2234 », 91,75 s. Les deux tests en cause
passent : « XamGetOverlappedResult sees the event set once the result is complete » en
0,70 s, « A KeReleaseMutant by the old owner after a KeInitializeMutant is refused » en
0,05 s.

CI du commit `d31d4c2` (exécution 44992169209) : job `linux-x86_64` du 2026-11-22
06:05:27 au 06:23:21 UTC (17 min 54 s), conclusion **success**. Le SDK Debug est
désormais construit en dernier, et ses tests figurent dans la partie lisible du journal :
« rexglue-sdk-debug-tests> 100% tests passed, 0 tests failed out of 2234 », en
82,31 s, contre 269,32 s lors de l'échec. Les deux tests en cause passent : « XamGetOverlappedResult
sees the event set once the result is complete » en 1,43 s, « A KeReleaseMutant by the
old owner after a KeInitializeMutant is refused » en 0,07 s. Le journal affiche aussi
« all checks passed! » ; la sonde Vulkan, informative, rend 4 (pas de GPU sur la machine
de la CI) ; l'artefact `j1-evidence` est publié.

Le SIGSEGV sous charge laisse soupçonner une condition de course dans ReXGlue lui-même
(fil propriétaire d'un mutant réinitialisé par un autre fil), en Debug. C'est à signaler
en amont (§6).

## 5. Problèmes constatés

| ID | Problème | Cause | Traitement |
|---|---|---|---|
| P-01 | L'étiquette `v0.11.0` ne désigne pas le commit `ebac1cf` cité par l'audit | `ebac1cf` est la fusion « Release v0.11.0 » sur `main` ; l'étiquette désigne `a3e1d82`, la pointe de la branche fusionnée | Arbres identiques vérifiés (`bd12f1aa…`) ; épinglage sur `a3e1d82` ; documents mis à jour |
| P-02 | `Git submodule 'cli11' is not initialized` | `thirdparty/CMakeLists.txt` teste `<sous-module>/.git`, absent d'une source récupérée par Nix | Dossier `.git` vide créé pour chaque chemin de `.gitmodules`, en échec si un sous-module manque |
| P-03 | Erreur dans `GetGitRevisionDescription.cmake` de SDL3 | Un **fichier** `.git` est lu comme pointeur de sous-module | Marqueur en **dossier** : SDL3 ne trouve pas `HEAD` et abandonne proprement |
| P-04 | `Package 'xdmcp', required by 'xcb', not found` | Dépendances de `xcb.pc` non transitives sous Nix | `libxau` et `libxdmcp` ajoutés |
| P-05 | Binaires sans RUNPATH vers libstdc++, X11, Wayland | ReXGlue lie toutes ses cibles avec `clang --ld-path=<ld.lld>` (modèle de code `large`) ; le `ld.lld` brut contourne l'enveloppe Nix qui ajoute les RUNPATH | `-DREXGLUE_LLD=…/llvmPackages_20.bintools/bin/ld.lld`. **À reprendre à J2** : l'exécutable du jeu devra recevoir la même option (exportée dans `nix develop` sous `REXGLUE_LLD`) |
| P-06 | `auto-patchelf could not satisfy dependency libsteam_api.so` | Les notes ELF `dlopen` de SDL3 3.4 citent la bibliothèque Steamworks de Valve | Ignorée explicitement : bibliothèque propriétaire, facultative pour SDL ; le projet n'en dépend pas |
| P-07 | `vulkan-loader` absent du RUNPATH du pilote Vulkan | `runtimeDependencies` d'autoPatchelf ne s'applique qu'aux exécutables ; `dlopen` cherche dans le RUNPATH de l'objet appelant | `appendRunpaths` sur tous les fichiers ELF ; défaut trouvé par le contrôle C1.3, avant toute exécution du jeu |
| P-08 | Version du SDK « 0.11.0.0-dev.unknown » | Sans `.git` à la racine, `rex_resolve_version` prend la version de repli ; le fichier de version CMake indique `0.11.0.0` | Accepté, sans effet sur `find_package(rexglue 0.11)` ; à revoir si une vérification de version l'exige à J2 |
| P-09 | `sandbox-fallback = true` sur l'hôte | Nix peut construire sans bac à sable s'il ne peut pas l'établir | Le contrôle C1.3 échoue si `/usr/lib` est visible, ce qui détecte un repli |
| P-10 | Fixtures `gdfx.iso` et `stfs_con.bin` dans la source de ReXGlue | Tests du système de fichiers du SDK | Inspectées : synthétiques (fichiers `a.txt`, `big.bin`, motifs ASCII), aucun contenu de jeu ; autorisées par chemin et SHA-256 (`tools/proprietary-data-allowlist.json`) |
| P-11 | `ROADMAP.md` §4.5 demandait de détecter des « clés XEX ou AES connues » | Stocker ces clés, ou leurs empreintes, dans le dépôt est indésirable | Détection de tout jeton hexadécimal de 128 bits, sans aucune liste de clés |
| P-12 | `nix flake check` copie les fichiers suivis dans `/nix/store` | Fonctionnement normal des flakes Git | Le hook pre-commit et la CI contrôlent les fichiers **avant** qu'ils ne soient suivis |
| P-13 | L'API GitHub est bloquée depuis cet environnement (`github:` refusé) | Politique réseau de la session | Entrées en `https://releases.nixos.org/…` et `git+https://…`, également valables en CI |
| P-14 | Échec du contrôle `proprietary-data-closure` : « Permission denied » | Défaut dans ce contrôle : `cp` gardait le mode lecture seule du fichier copié depuis le magasin, et l'ajout suivant échouait. Aucune donnée n'avait été détectée | Fichier écrit avec `cat` ; contrôle réussi ensuite |
| P-15 | Revue de l'orchestrateur : le mode `staged` lisait l'arbre de travail, pas l'index | `check_repo_file` lisait le fichier sur disque. Après un `git add` suivi d'une modification, le hook vérifiait un autre contenu que celui du commit | Lecture des objets de l'index (`git ls-files --stage`, puis `git cat-file blob`) et tests de non-régression (§4.10) |
| P-16 | Revue de l'orchestrateur : le contrôle ELF masquait l'échec de `ld.so --list` (`if ...; then :; fi`) | Un fichier du magasin que le chargeur ne peut pas analyser passait le contrôle : ses lignes d'erreur commencent par `/nix/store/` | Script strict `tools/check_elf_deps.sh`, contrôle `elf-deps-check-selftest` (§4.10) |
| P-17 | CI de `25fdd71` : un test Debug du SDK dépasse son délai (« XamGetOverlappedResult sees the event set once the result is complete ») | Tests de synchronisation du noyau ReXGlue sensibles à la contention ; `nix flake check` construisait les SDK Release et Debug en même temps sur 4 processeurs virtuels. Sous charge locale, un autre test de ce groupe plante (SIGSEGV) | SDK Debug construit après le Release (§4.10) ; condition de course possible à signaler en amont (§6) |

## 6. Constats utiles pour J2

1. Passer `-DREXGLUE_LLD=$REXGLUE_LLD` (P-05) et corriger le RUNPATH de l'exécutable du
   jeu (P-07) ; sinon il ne démarrera pas sous NixOS.
2. Le contrôle de données doit rester actif sur le dossier privé de génération : le code
   généré est refusé par ses marqueurs (`// Generated by rexglue`, `DEFINE_REX_FUNC`).
3. La transposition des correctifs 0002 et 0003 du projet A reste à faire (J2).
4. D-008 (déchiffrement des XEX) reste ouverte et bloque toujours J2. *État à J1. Depuis
   le 2026-11-22, D-008 est une décision de projet clôturée (O3). J2 est autorisé le
   2026-11-23 (D-015) ; sa phase B attend PB-0 (`docs/DECISIONS.md`).*
5. Les tests de synchronisation du noyau de ReXGlue v0.11.0 échouent sous forte
   contention processeur, en Debug (P-17), et l'un d'eux plante. À signaler en amont, et à
   prendre en compte dans le risque R-05 (maturité du runtime sous Linux) : un jeu sollicite
   ces mêmes primitives.

## 7. Validations matérielles (tests impossibles à exécuter dans le conteneur ou en CI)

Ni ce conteneur ni les machines hébergées de la CI n'ont de GPU ou de NixOS ; ce n'est
pas un défaut du développement. Ces validations ont été faites, en partie, par
l'utilisateur sur sa machine (§7.1). Le tableau qui suit le §7.1 liste ce qui reste.

### 7.1 Résultats sur l'hôte NixOS de l'utilisateur (2026-11-22)

Source : sortie de terminal collée par l'utilisateur dans la conversation. Elle a été
relue ligne à ligne. Les extraits ci-dessous en sont recopiés tels quels.

| Vérification | Résultat | Extrait |
|---|---|---|
| Même dérivation que la PR | **Oui** : le chemin de sortie Debug de l'hôte est celui que donne l'évaluation du flake de la PR (`nix eval .#checks.x86_64-linux.rexglue-sdk-debug-tests.outPath`). Les entrées sont donc identiques | `/nix/store/sdn1xyd79jjv2ibisi5npm2bj929kpv6-rexglue-sdk-debug-tests-0.11.0` |
| C1.2 — tests Debug du SDK | **Réussi** : 0 échec ; 2 tests sautés, les mêmes qu'en CI (§4.4). Durée 33,87 s | `100% tests passed, 0 tests failed out of 2234` ; `742 - unit.A write to a watched host page … (Skipped)` ; `2003 - unit.HostStat names the entry as the folder holds it (Skipped)` |
| C1.3 — `rexglue --help` | Aide affichée | `ReXGlue v0.11.0.0-dev.unknown Recompilation Toolkit` |
| C1.4 — `vulkaninfo --summary` | Version d'instance 1.4.341, celle du `vulkan-loader` épinglé. GPU0 matériel, GPU1 logiciel | `deviceName = AMD Radeon 860M Graphics (RADV KRACKAN1)`, `deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU`, `driverInfo = Mesa 26.1.8` ; GPU1 `llvmpipe (LLVM 21.1.8, 256 bits)` |
| C1.4 — `nix run .#vulkan-probe` | **Réussi**. Cette ligne n'est écrite que sur le chemin qui rend 0 (`tools/vulkan_probe.py`) | `independentBlend = true`, `fragmentStoresAndAtomics = true`, `vertexPipelineStoresAndAtomics = true` ; `RESULT: a GPU with the features ReXGlue requires was found` |

Réserves :

- La sortie transmise commence au milieu de `nix flake check`, au test Debug 2 215. Le
  code de sortie final de `nix flake check` sur l'hôte n'est donc pas visible ; la même
  suite complète est verte en CI sur `134a2a6` (§4.9).
- Ni la commande qui a lancé `rexglue --help` ni son code de sortie ne figurent dans la
  sortie.
- Deux avertissements, sans effet sur les résultats :
  - `auto-patchelf ignoring missing libsteam_api.so` : comportement voulu
    (`autoPatchelfIgnoreMissingDeps`, P-06). SDL3 déclare cette bibliothèque Steam,
    facultative, dans ses notes `dlopen` ;
  - `terminator_CreateInstance: Received return code -9 … libvulkan_dzn.so` : l'ICD
    `dzn` de Mesa (Vulkan au-dessus de Direct3D 12, pour Windows et WSL) refuse de
    démarrer sous Linux, et le chargeur l'ignore. Les pilotes RADV et llvmpipe sont
    chargés.

### 7.2 Ce qui reste

| Test | Raison | Ce qui a été fait à la place | Pour le réaliser |
|---|---|---|---|
| Code de sortie de `nix flake check -L` sur NixOS | Absent de la sortie transmise (§7.1) | Suite complète verte en CI ; tests Debug réussis sur l'hôte | Relancer sur l'hôte et noter le code de sortie (`echo $?`) |
| Test de machine virtuelle NixOS (`nixosTest`) | Pas de `/dev/kvm` | — | Sur une machine avec KVM |
| Pilote Vulkan Xenos de ReXGlue sur un vrai périphérique | Aucun test du SDK ne crée de périphérique Vulkan, et aucune application ne le fait avant J2 | Présence et RUNPATH du module vérifiés (C1.3) | À J3, avec le jeu |

## 8. Arrêt

J1 s'arrête ici. Rien de J2 n'est commencé : pas de manifeste, pas de génération de code,
pas de correctif du SDK, pas de code dans `app/`, `hooks/` ou `platform/`.

La PR #2 a été fusionnée sur `main` le 2026-11-22 (commit de fusion `1fd73d8`), après la
décision de l'orchestrateur (revue du 2026-11-22 : « J1 validé ; fusion de la PR #2
autorisée ») et l'accord de l'utilisateur, avec une CI verte sur le dernier commit
`134a2a6`.

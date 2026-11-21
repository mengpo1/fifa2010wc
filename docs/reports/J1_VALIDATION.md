# Rapport de validation — Jalon J1 : infrastructure native Linux/NixOS

> Mission 002, 2026-11-21. Branche `claude/j1-linux-nix-infra`, issue de `main` au commit
> `9869c30` (fusion de la PR #1). Aucune ressource du jeu n'a été utilisée, lue, produite
> ou déchiffrée. Le travail s'arrête après J1 : J2 n'est pas commencé.
>
> Règle de ce rapport : chaque résultat renvoie à une commande exécutée et à son journal.
> Ce qui n'a pas pu être exécuté figure à part, au §7.

## 1. Synthèse

| Critère (`docs/ROADMAP.md` §4) | Statut | Preuve |
|---|---|---|
| C1.1 — Le SDK se compile depuis un dépôt propre par une seule commande Nix | **Validé** (environnement Nix sur Ubuntu) | §4.3 : `nix build .#rexglue-sdk`, code de sortie 0 |
| C1.2 — Les tests unitaires du SDK passent | **Validé** en bac à sable Nix : Release 2 213 réussis, 0 échec, 10 sautés ; Debug 2 232 réussis, 0 échec, 2 sautés (raisons au §4.4) ; exécution « sous NixOS » non vérifiable ici (§7) | §4.4 : rapport JUnit installé avec le SDK |
| C1.3 — `rexglue` s'exécute sans `nix-ld` ni `steam-run` | **Validé** dans le bac à sable Nix, sans aucun dossier de bibliothèques FHS ; sur un hôte NixOS réel : non vérifiable ici (§7) | §4.5 : contrôle `rexglue-cli-runs` |
| C1.4 — Le pilote Vulkan trouve le GPU | **Non vérifiable** : pas de GPU dans cet environnement (§7). La sonde est livrée et validée sur un périphérique logiciel | §4.7 |
| C1.5 — Aucune donnée du jeu requise ni présente | **Validé** | §4.6 : contrôles du dépôt, de la clôture Nix et du hook |

Commande de synthèse, rejouée sur l'arbre final de la branche : `nix flake check -L` →
« all checks passed! », code de sortie 0. Les 6 contrôles sont `rexglue-sdk`,
`rexglue-sdk-debug-tests`, `rexglue-cli-runs`, `cmake-skeleton`,
`proprietary-data-source` et `proprietary-data-closure` ; les paquets et l'environnement
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
3. il résout, avec `ld.so --list`, toutes les dépendances de chaque fichier ELF du SDK,
   et échoue si l'une est introuvable ou hors de `/nix/store` ;
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
| Tests du script de contrôle | `python3 -I tools/test_check_proprietary_data.py` | 12 tests, tous réussis |
| Fichiers suivis | `python3 -I tools/check_proprietary_data.py repo` | « OK: 28 files checked, no proprietary data found » (arbre final) |
| Fichiers indexés | `python3 -I tools/check_proprietary_data.py staged` | « OK: 21 files checked, no proprietary data found » (les 21 fichiers ajoutés par J1) |
| Source du flake (bac à sable) | contrôle `proprietary-data-source` | « OK: 28 files checked, no proprietary data found » sur l'arbre final ; les 12 tests du script passent aussi dans le bac à sable |
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

## 6. Constats utiles pour J2

1. Passer `-DREXGLUE_LLD=$REXGLUE_LLD` (P-05) et corriger le RUNPATH de l'exécutable du
   jeu (P-07) ; sinon il ne démarrera pas sous NixOS.
2. Le contrôle de données doit rester actif sur le dossier privé de génération : le code
   généré est refusé par ses marqueurs (`// Generated by rexglue`, `DEFINE_REX_FUNC`).
3. La transposition des correctifs 0002 et 0003 du projet A reste à faire (J2).
4. D-008 (déchiffrement des XEX) reste ouverte et bloque toujours J2.

## 7. Tests impossibles à exécuter faute de matériel ou d'environnement adapté

| Test | Raison | Ce qui a été fait à la place | Pour le réaliser |
|---|---|---|---|
| C1.4 — détection d'un GPU Vulkan par la pile du SDK | Aucun GPU ni pilote Vulkan dans le conteneur (`/dev/dri` absent) | Sonde exécutée (aucun pilote, code 4) et validée avec lavapipe (code 3) | Sur une machine NixOS avec GPU et `hardware.graphics.enable = true` : `nix run .#vulkan-probe` doit rendre 0 |
| C1.2 et C1.3 sur un hôte **NixOS** réel | L'environnement est Ubuntu avec Nix, pas NixOS | Exécution dans le bac à sable Nix, sans aucun dossier FHS (contrôlé) | Sur NixOS 26.05 : `nix flake check -L`, puis `nix run .#rexglue-sdk -- --help` |
| Test de machine virtuelle NixOS (`nixosTest`) | Pas de `/dev/kvm` | — | Sur une machine avec KVM |
| Pilote Vulkan Xenos de ReXGlue sur un vrai périphérique | Aucun test du SDK ne crée de périphérique Vulkan, et aucune application ne le fait avant J2 | Présence et RUNPATH du module vérifiés (C1.3) | À J3, avec le jeu |

## 8. Arrêt

J1 s'arrête ici. Rien de J2 n'est commencé : pas de manifeste, pas de génération de code,
pas de correctif du SDK, pas de code dans `app/`, `hooks/` ou `platform/`. La PR de J1
reste en brouillon, sans fusion, en attente de la validation de l'orchestrateur.

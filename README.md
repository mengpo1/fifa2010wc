# fifa2010wc

Recompilation statique de *2010 FIFA World Cup South Africa* (Xbox 360) en exécutable
natif, sans émulateur à l'utilisation. Plateforme prioritaire : Linux x86_64 sous NixOS ;
macOS ARM64 est prévu plus tard.

Ce dépôt ne contient et ne contiendra aucun fichier du jeu : ni ISO, ni exécutable, ni
code généré depuis le jeu, ni ressource. Chacun utilise sa propre copie.

La documentation du projet est dans `docs/` : audit (`docs/audit/`), feuille de route
(`docs/ROADMAP.md`), décisions (`docs/DECISIONS.md`), dépendances
(`docs/DEPENDENCIES.md`), rapports de validation (`docs/reports/`).

## Infrastructure de compilation (jalon J1)

Prérequis : Nix 2.34 ou plus récent, avec les fonctionnalités `nix-command` et `flakes`.

Compiler le SDK ReXGlue v0.11.0 depuis les sources ; ses tests unitaires s'exécutent
pendant la compilation :

```bash
nix build .#rexglue-sdk
```

Lancer toutes les vérifications (SDK et tests, outil `rexglue`, squelette CMake, contrôle
des données propriétaires) :

```bash
nix flake check -L
```

Lister les périphériques Vulkan et les fonctionnalités exigées par ReXGlue :

```bash
nix run .#vulkan-probe
```

Environnement de développement (clang 20, CMake, Ninja, SDK sur `CMAKE_PREFIX_PATH`) :

```bash
nix develop
```

Configurer le squelette du projet depuis cet environnement :

```bash
cmake --preset linux-amd64-release
```

Activer le contrôle des données propriétaires avant chaque commit :

```bash
git config core.hooksPath .githooks
```

Le jeu lui-même n'est pas encore compilé : la génération de code arrive au jalon J2.

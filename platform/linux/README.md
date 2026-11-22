# platform/linux/ — implémentation Linux

Rôle (D-001, D-006) : les implémentations Linux des interfaces de `platform/common/`,
par exemple les dossiers XDG, le gestionnaire de plantage par signaux et le journal.

Règles :
- seul endroit, avec `platform/macos/`, où les en-têtes système sont permis ;
- aucune hypothèse NixOS dans le code : les chemins des bibliothèques viennent du
  paquet Nix (`flake.nix`), pas du code.

État : vide jusqu'au jalon J2. `CMakeLists.txt` choisit déjà ce dossier sous Linux x86_64.

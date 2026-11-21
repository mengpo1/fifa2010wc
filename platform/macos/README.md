# platform/macos/ — implémentation macOS ARM64 (jalon J6)

Rôle (D-001, D-006) : les implémentations macOS des interfaces de `platform/common/`.

État : réservé. macOS ARM64 est une plateforme secondaire, traitée au jalon J6, après une
version Linux jouable et stabilisée (`docs/ROADMAP.md`). Le dossier existe dès J1 pour que
l'organisation des couches ne change pas. Il ne contient aucune implémentation, et
`CMakeLists.txt` refuse explicitement la configuration sous macOS avant J6.

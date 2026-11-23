# app/ — application portable

Rôle (`docs/audit/LINUX_FEASIBILITY.md` §6.2, D-006) : l'application `TitleApp` du jeu,
en C++23 portable. Elle couvre les chemins, la configuration et les réglages GPU propres au
jeu (`allow_invalid_fetch_constants`, `execute_unclipped_draw_vs_on_cpu`).

Règles :
- aucun en-tête système, aucun appel direct à Vulkan, SDL ou POSIX ;
- les services du SDK (graphismes, audio, entrées, interface) s'utilisent par leurs
  interfaces (D-003, D-004) ; rien de ce que ReXGlue fournit n'est réimplémenté ici ;
- ce qui dépend du système passe par `platform/common/`.

État : vide jusqu'au jalon J2. Le code de cette couche n'a de sens qu'avec la génération
de code du jeu. Elle suit la voie retenue par D-008 (O3). J2 est autorisé (D-015) ; la
génération de code attend la phase B, après PB-0 (`docs/J2_PLAN.md`).

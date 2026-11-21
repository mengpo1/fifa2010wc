# hooks/ — correctifs propres au jeu

Rôle (D-006) : les correctifs du code recompilé (crochets ReXGlue sur des fonctions
invitées, aux adresses du jeu), comme l'équivalent du `boot_fixes.cpp` du projet A
(`docs/audit/EXISTING_PROJECTS.md` §A).

Règles :
- C++23 portable, sans appel système ;
- adresses et noms de fonctions invitées autorisés ; aucun code généré par
  `rexglue codegen` (le contrôle `tools/check_proprietary_data.py` le refuse) ;
- chaque correctif cite sa provenance (projet A, projet B ou travail propre), avec la
  notice de licence exigée (D-010).

État : vide jusqu'au jalon J2. Les adresses dépendent de la version de l'ISO, encore
inconnue (J0, `docs/audit/ISO_REQUIREMENTS.md` §3).

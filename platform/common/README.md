# platform/common/ — interfaces de la couche plateforme

Rôle (D-006) : les interfaces des services qui dépendent du système d'exploitation et que
le SDK ne fournit pas. Les candidats repérés à l'audit sont les dossiers de données de
l'utilisateur, le rapport de plantage et les dialogues
(`docs/audit/LINUX_FEASIBILITY.md` §6.2).

Règles :
- en-têtes C++23 sans aucune inclusion système ;
- une interface n'est ajoutée que lorsqu'une couche (`app/`, `hooks/`) en a besoin, et
  après avoir vérifié que ReXGlue ne fournit pas déjà ce service.

État : vide jusqu'au jalon J2.

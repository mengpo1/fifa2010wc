# J2, étape A8-bis — Comparateur d'adresses

> Étape A8-bis de `docs/J2_A8_ADDRESS_VALIDATION.md` (§4) et ticket #22, sous l'autorisation
> PA-0 (D-015). **Phase A : aucune donnée du jeu.** L'outil n'a vu que des données
> synthétiques ; il ne traitera les sorties privées qu'en phase B, après PB-0.
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Résultat

- **L'outil** : `tools/address_compare.py`, empaqueté en `nix run .#address-compare`.
  - Il compare les entrées configurées (`[functions]`, `setjmp_address`, `longjmp_address`)
    aux listes et aux diagnostics de ReXGlue, et à un relevé d'examens manuels.
  - Il attribue à chaque élément un niveau de preuve, de N0 à N2, et signale les cas
    d'arrêt (STOP).
- **Strictement analytique** : il ne lit ni image, ni XEX, ni corps de code généré, ni
  donnée du jeu. Il n'écrit que son rapport, dans le dossier privé.
- **Il échoue en refusant** :
  - un format inconnu ou partiel est refusé, et rien n'est écrit (code 2) ;
  - ce qui n'est pas établi reste au niveau inférieur ;
  - les données et les pointeurs restent N3, non vérifiés.
- **Il ne conclut jamais** à une validation de toutes les adresses, ni à l'identité avec
  le projet A. Le rapport et la sortie le disent.
- **Limite principale** (§3) : N2 n'est pas calculé à partir du code généré, dont les
  commentaires ne portent pas d'adresse. Il vient d'un relevé d'examen manuel, que
  l'outil contrôle.

## 2. Entrées et formats

Les formats sont ceux de la source de ReXGlue v0.11.0 (`a3e1d82`). Aucun n'est supposé.

| Entrée | Contenu | Format, et sa référence |
|---|---|---|
| `--entries KIND=PATH` | Une configuration de ReXGlue, d'un seul type : `function` (débuts de fonctions, graines « autofix ») ou `pointer` (pointeurs de code). `setjmp_address` et `longjmp_address` y sont de type `crt` | Table `[functions]` à clés d'adresse (`src/codegen/config.cpp:221-262`). L'outil est plus strict que ReXGlue : une clé doit être `0x` suivi de 1 à 8 chiffres hexadécimaux, et l'adresse alignée sur 4 |
| `--mappings-with` | Le fichier `<préfixe>_init.cpp` généré **avec** les entrées | Liste `kPPCFuncMappings`, une ligne `\t{ 0x<ADRESSE>, <nom> },` par fonction, terminée par `\t{ 0, nullptr }` puis `};` (`resources/templates/codegen/init_cpp.inja:34-37`) |
| `--mappings-without` | Le même fichier, généré **sans** les entrées (facultatif) | Idem |
| `--log` | Le journal de la génération avec les entrées | Messages de `src/codegen/phase_validate.cpp:57,61,78` (« is not a function entry point », « outranked by », « split by »), de `src/codegen/phase_discover.cpp:78,94` (« not in any code region », « no blocks found »), de `src/codegen/config.cpp:227-262` (erreurs de configuration), et erreurs d'analyse imprimées par `AnalysisErrorLog::PrintReport` (`src/codegen/analyze.cpp:103-129`) avec le résumé « Validation failed: N unresolved calls, M millicode errors » (`phase_validate.cpp:196-200`). Le texte est cherché dans la ligne : le préfixe du journal n'importe pas |
| `--claims` | Le relevé des examens manuels de N2 : `[[claim]]` avec `name`, `kind` (`crt`, `hook`, `data`), `address`, et selon le cas `offset`, `referenced_by`, `examined`, `boot_critical`, `expected`, `observed` | Défini par ce projet, aux **types exacts** (P-45) : `address`, `offset` et `referenced_by` sont des entiers (un booléen est refusé) ; `examined` et `boot_critical` sont `true` ou `false` (une chaîne est refusée) ; `expected` et `observed` sont des séquences d'instructions écrites en texte, non vides, par exemple `"mflr r12 / stw r12,-8(r1)"`, comparées à espaces près. Un relevé `examined = true` exige les deux séquences. Une clé inconnue est refusée |
| `--out` | Le rapport détaillé, en JSON | Créé dans le dossier privé, ancré à sa racine (§4), jamais écrasé, jamais à travers un lien |

**Ordre** (P-43) : **tous les chemins sont contrôlés avant la lecture du moindre fichier**.
Une entrée hors du dossier privé n'est donc jamais ouverte.

**Refus, avec code 2 et rien d'écrit** :
- une liste `kPPCFuncMappings` absente, une ligne inconnue, un terminateur ou une fin
  absents, une adresse listée deux fois ;
- un journal vide, faute de diagnostic ;
- une ligne de journal qui parle d'une entrée sous une forme inconnue ;
- des erreurs sans le résumé « Validation failed », ou un résumé dont les nombres
  diffèrent des erreurs listées, car le journal est alors partiel ;
- une clé `[functions]` refusée par ReXGlue ;
- une entrée ou une réclamation mal formée, ou mal typée ;
- un chemin hors du dossier privé, ou un rapport à un chemin relatif.

## 3. Niveaux de preuve et cas d'arrêt

Niveaux, selon `docs/J2_A8_ADDRESS_VALIDATION.md` §3 :

| Niveau | Attribué quand | Jamais attribué quand |
|---|---|---|
| refusé | ReXGlue signale une erreur de configuration pour l'entrée | — |
| N0 | Le journal existe et l'entrée a été lue | — |
| N1 | Aucun diagnostic pour l'entrée, la génération a réussi, et une fonction a été générée à cette adresse, avec les entrées ou sans elles | Un diagnostic, une collision, une génération en échec, ou une entrée présente seulement dans la configuration |
| N2 | `crt` et `hook` : un relevé marqué `examined`, pour une fonction présente dans `kPPCFuncMappings` et sans diagnostic, dont la séquence observée est égale à celle attendue. `data` : de même, avec un déplacement valide (16 bits signés) et une fonction de référence présente | Sans relevé, relevé non examiné, fonction absente, séquence absente ou différente |
| N3 | Jamais atteint : c'est l'état de toute valeur de données et de tout pointeur dans les données, noté comme tel | — |

**Cas d'arrêt (STOP, code 1)**, selon le §4 du même document :
- `setjmp_address` ou `longjmp_address` sous N2 : arrêt PB-2 ;
- un relevé `crt`, ou marqué `boot_critical`, sous N2 ;
- une génération en échec : les erreurs sont listées dans le rapport comme graines à
  ajouter, selon la méthode d'`autofix_codegen.py`, avant de recommencer.

Un début de fonction ou un pointeur sous N1 n'est pas un arrêt. Il est écarté, puis
réanalysé (M3), comme le prévoit A8.

**Pourquoi N2 n'est pas calculé** [V] :
- le code généré commente chaque instruction par `// <mnémonique> <opérandes>`, **sans son
  adresse** (`src/codegen/function_graph.cpp:644,648`) ;
- deux instructions fusionnées (`consumed == 2`) n'ont qu'un commentaire
  (`function_graph.cpp:641,679-712`), et les étiquettes `loc_<adresse>:` ne marquent que les
  cibles de branchement (`:598`) ;
- l'adresse d'une instruction ne se retrouve donc pas de façon sûre en comptant les
  commentaires. Plutôt que de deviner, l'outil s'en tient au relevé manuel, et il en
  contrôle la cohérence.

## 4. Sortie

- **Sortie standard, agrégée** : la phrase de méthode, les nombres par type et par
  niveau, les raisons d'arrêt et le chemin du rapport. **Aucune adresse** (P-44) :
  - les messages de refus ne citent ni la ligne fautive ni l'adresse, seulement le
    fichier, le numéro de ligne et la nature du problème ;
  - une raison d'arrêt désigne un relevé par son numéro, jamais par son nom libre, qui
    peut contenir une adresse ;
  - par précaution, tout motif hexadécimal ou mot de 8 chiffres hexadécimaux restant dans
    un message est remplacé par `<address>` avant l'affichage.
- **Rapport JSON, dans le dossier privé** :
  - les mêmes nombres ;
  - pour chaque entrée, son adresse, son type, son origine, son niveau et ses notes ;
  - les erreurs de la génération.

  Il ne contient ni désassemblée, ni code généré, ni contenu du jeu. Il n'entre dans le
  dépôt qu'après PB-3, et seulement pour des adresses et des métadonnées (A8 §4, D-007).
- **Création du rapport, ancrée** (P-46) :
  - la racine du dossier privé est ouverte une fois, par son chemin réel ;
  - chaque dossier du chemin du rapport est ouvert avec `O_DIRECTORY | O_NOFOLLOW`,
    relativement au descripteur de son parent ;
  - le fichier est créé par `O_CREAT | O_EXCL | O_NOFOLLOW`.

  Un dossier remplacé par un lien entre les contrôles et la création fait échouer
  celle-ci, sans rien écrire. Comme pour A5, cela ne couvre pas le renommage, par un
  processus du même utilisateur, d'un vrai dossier déjà ouvert vers l'extérieur.

## 5. Vérifications

**Tests unitaires** (`tools/test_address_compare.py`, 30 tests, dans le contrôle Nix
`address-compare-selftest`). Les données sont synthétiques, aux adresses `0x8C01xxxx` :

| Faux positif de A8 §4 | Test |
|---|---|
| Adresse dans la configuration mais non découverte | `test_entry_in_configuration_only_stays_n0` : acceptée sans avertissement, jamais générée, elle reste N0 |
| Décalage de données invalide | `test_invalid_data_offset_stays_unverified` : un déplacement de `0x10000` laisse la donnée sous N2, avec un arrêt |
| Collision de fonctions | `test_function_collision_is_reported` : « outranked by », et une adresse configurée deux fois |
| Absence de diagnostic | `test_absent_diagnostics_are_refused` : journal vide refusé |
| Erreur de format | `test_unknown_or_partial_mappings_are_refused` (cinq cas), `test_diagnostic_in_an_unknown_format_is_refused`, `test_partial_failed_log_is_refused` |

Autres tests :
- chacun des cinq diagnostics garde l'entrée en N0 ;
- une erreur de configuration donne le niveau « refusé » ;
- un pointeur reste noté « non vérifié dans les données (N3) » ;
- une génération en échec n'établit rien et s'arrête ;
- `crt` sans examen s'arrête ; avec un examen cohérent, il atteint N2 ;
- une référence absente ou incohérente (non examinée, fonction inconnue, séquence
  différente ou absente) reste sous N2 et s'arrête si elle est nécessaire au démarrage ;
- une valeur de données, même en N2, reste notée N3 ;
- le rapport ne prétend jamais valider toutes les adresses, et la sortie standard ne
  contient aucune adresse ;
- un chemin hors du dossier privé est refusé et rien n'est écrit ;
- le rapport n'est jamais écrasé, ni écrit à travers un lien.

Tests de la revue du 24 novembre (commentaire 7127281995) :

| Constat | Test | Contrôle par mutation |
|---|---|---|
| P-43 | `test_paths_are_checked_before_any_file_is_read` : une entrée hors du dossier privé n'est jamais lue (aucun appel de lecture) | Avec l'ancien ordre, le fichier extérieur est lu : le test échoue |
| P-44 | `test_refusals_print_no_address`, `test_stop_lines_print_no_address` : une ligne fautive, une clé ou un nom de relevé qui contient `0x8C010000` ne paraît pas sur la sortie standard ; le rapport garde le nom | — |
| P-45 | `test_badly_typed_claims_are_refused_and_cannot_lift_a_stop` : `examined = "false"` ou `1`, séquences `42` ou vides ou absentes, adresse `true`, `boot_critical = "yes"`, décalage `true` sont refusés (code 2, aucun rapport), donc ne peuvent lever l'arrêt PB-2 ; `test_setjmp_entry_must_be_an_integer` | — |
| P-46 | `test_report_parent_swapped_for_a_link_is_refused` : entre les contrôles et la création, le dossier du rapport devient un lien vers l'extérieur ; la création est refusée, et l'extérieur reste vide | Avec une création par chemin, le rapport est écrit à l'extérieur : le test échoue |

**Commande empaquetée** (même contrôle) [V] : sur un dossier privé synthétique, la sortie
est agrégée et sans adresse, et le rapport est créé dans le dossier privé. Un rapport
demandé hors de ce dossier est refusé, sans rien écrire.

## 6. Limites

- Les formats viennent de la source de ReXGlue, pas d'une génération réelle : la phase B
  le confirmera. Un écart de format sera refusé, pas mal lu.
- N2 repose sur un examen manuel de la désassemblée privée. L'outil n'en vérifie que la
  cohérence : la séquence observée est égale à l'attendue, la fonction existe et n'a pas
  de diagnostic.
- Une adresse au milieu d'une fonction n'est pas détectée, sauf par les diagnostics de
  ReXGlue : `kPPCFuncMappings` ne donne pas les bornes des fonctions (A1 §5).
- L'outil ne franchit pas PB-0 à lui seul.

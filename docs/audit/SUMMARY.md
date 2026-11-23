# Rapport synthétique — Mission 001 (Linux prioritaire)

> Pour l'orchestrateur : de quoi choisir le premier jalon d'implémentation.
> Audit du 2026-11-21. Aucun code du jeu n'a été modifié, généré ou compilé.
> Détails : `EXISTING_PROJECTS.md`, `LINUX_FEASIBILITY.md`, `ISO_REQUIREMENTS.md`,
> `RISKS.md`, `../ROADMAP.md`, `../DECISIONS.md`.

## 1. Conclusions en six points

1. **Les deux projets existants** (CalinGraphics, BSD 3-Clause, v0.3.1 « released » ;
   RamiChaaben8, MIT, v0.8 « experimental ») sont des recompilations statiques ReXGlue
   **pour Windows et Direct3D 12 uniquement**. Aucun n'a été essayé sous Linux. [V]
2. **ReXGlue v0.11.0 compile sous Linux x86_64 avec la chaîne de nixos-26.05**
   (clang 20.1.8, CMake 4.1.6) : vérifié pendant l'audit (1 051 étapes, 3 min 44 s),
   avec deux adaptations propres à Nix (bibliothèques X11 explicites, durcissement
   `fortify` désactivé) et sans modifier le SDK. XenonRecomp compile aussi sous Linux,
   mais il n'a pas de runtime. [V]
3. **Direct3D, XAudio et XInput ne sont pas des dépendances du jeu recompilé.** Ce sont
   des backends hôtes. ReXGlue fournit déjà leurs équivalents Linux : Vulkan (choisi
   par défaut hors Windows), SDL3 audio et SDL3 entrées. Il n'y a **pas de backend Vulkan
   à écrire**, seulement à valider pour ce jeu. [V]
4. **Le code Windows des ports existants se limite à leur couche applicative** (environ
   300 lignes pour le projet A, plus son lanceur WPF) et à un seul correctif du SDK, qui
   prévoit un repli portable. [V]/[H]
5. **Point bloquant non technique** : ReXGlue (comme les deux ports) **déchiffre les XEX**
   avec des clés intégrées, à la génération de code et à chaque lancement. Cela heurte
   la contrainte « ne pas engager de contournement des protections techniques ».
   Décision **D-008** requise avant toute génération de code. [V]/[I]
   *2026-11-22 : D-008 est une décision de projet clôturée, O3 retenue ; la contrainte
   est reformulée ; le risque juridique résiduel reste ouvert (`../DECISIONS.md`).*
6. **Première inconnue de données** : la version de l'ISO de l'utilisateur. La
   configuration d'analyse du projet A (environ 17 700 lignes) ne vaut que pour le
   disque Europe (En, Es, Nl), identifié par deux SHA-256. On peut le vérifier **sans
   déchiffrer** (`ISO_REQUIREMENTS.md` §3). [V]/[I]

## 2. Vérifications réalisées pendant l'audit

| Vérification | Résultat |
|---|---|
| Lecture des sources des deux ports, de ReXGlue v0.11.0 et de XenonRecomp | Faits consignés avec chemins et commits |
| Compilation de XenonRecomp sous Linux x86_64 (clang 18) | Succès, 7 s |
| Compilation de ReXGlue v0.11.0 depuis les sources, chaîne Nix 26.05 | Succès au 3e essai (deux causes Nix identifiées et corrigées dans l'environnement) |
| Inspection statique du SDK Linux précompilé v0.11.0 | Pilote Vulkan présent, pas de D3D12 ; GLIBC 2.38 ; SDL3 charge une quinzaine de bibliothèques par `dlopen` |
| Évaluation des paquets de nixos-26.05 | Chaîne complète disponible (clang 20, Vulkan 1.4.341, SDL 3.4, Wayland, PipeWire, extract-xiso…) |
| Non fait, volontairement | Exécution d'un binaire, téléchargement ou lecture de fichiers du jeu, génération de code du jeu |

## 3. Décisions attendues de l'orchestrateur

| Décision | Question | Recommandation de l'audit | Bloque |
|---|---|---|---|
| **D-008** | Comment traiter le déchiffrement des XEX ? | Attendre un avis juridique (O1) ; aucune clé ni code de déchiffrement dans le projet. *Recommandation historique. 2026-11-22 : décision de projet clôturée, O3 retenue par le porteur du projet ; le risque juridique résiduel reste ouvert (`docs/DECISIONS.md`)* | Ne bloque plus J2 au plan de la gouvernance ; PJ2-3 n'est pas donné |
| **D-011** | Quelle base de SDK ? | Tranchée par l'orchestrateur : ReXGlue v0.11.0 | — |
| — | Qui fournit l'identification de l'ISO (J0) ? | L'utilisateur, avec la procédure sans déchiffrement | J2 |

## 4. Premier jalon recommandé : **J1 — chaîne de compilation Linux et NixOS, sans le jeu**

Il est mené en parallèle de J0 (décisions et identification de l'ISO).

**Pourquoi celui-ci** : c'est le seul jalon utile qui ne dépend ni de D-008 ni de la
version de l'ISO. Il convertit en livrable le résultat le plus solide de l'audit (la
compilation sous Nix), il réduit les risques R-08 et R-15, et tout ce qu'il produit
servira quelle que soit la suite.

**Périmètre**

1. `flake.nix` épinglé sur nixos-26.05 : dérivation du SDK ReXGlue v0.11.0 depuis les
   sources (sous-modules épinglés, X11 explicite, durcissement réglé, rpath corrigé),
   `devShell` et enveloppe d'exécution.
2. Compilation et exécution des tests unitaires du SDK sous NixOS.
3. Squelette du projet portable : CMake et préréglages `linux-amd64-*`, couches `app/`,
   `hooks/` et `platform/{common,linux,macos}` (macOS en bouchons), sans code généré.
4. `.gitignore` strict et script de contrôle des données propriétaires (`ROADMAP.md` §4.5).

La transposition vers v0.11.0 des correctifs 0002 et 0003 du projet A relève de J2
(`ROADMAP.md` §2, J2), comme le prévoit la feuille de route.

**Critères d'acceptation** : C1.1 à C1.5 de `ROADMAP.md` §4. En bref : compilation en une
commande Nix, tests du SDK verts sous NixOS, `rexglue --help` exécutable sans `nix-ld`,
périphérique Vulkan détecté, aucune donnée du jeu présente.

**Hors périmètre** : génération de code du jeu, exécution du jeu, macOS, lanceur
graphique.

## 5. Ce qui suit J1

J2 (génération de code et édition de liens) dès que D-008 est tranchée et l'ISO
identifiée. *2026-11-22 : les deux sont faits ; J2 attend l'autorisation PJ2-3, et son
plan est dans `../J2_PLAN.md`.* Puis viennent J3 (écran-titre sous Vulkan) ; J4
(**premier match jouable**, 11 critères mesurables : trois matchs complets sans
plantage, ≥ 30 i/s, audio sans sous-alimentation notable, manette et clavier,
persistance, hygiène des données) ;
J5 (stabilisation Linux) ; J6 (macOS ARM64).

## 6. Principaux risques (registre complet dans `RISKS.md`)

| Risque | Niveau | Parade |
|---|---|---|
| R-01 Déchiffrement et protections techniques | Élevé ; chiffrement des deux modules constaté à J0. Risque juridique résiduel, accepté par le porteur du projet | D-008 tranchée (O3) ; aucune clé ni aucun outil de déchiffrement propres au projet ; D-007 ; aucune distribution |
| R-02 Disque différent de celui du projet A (empreintes différentes, constat de J0) | Élevé | Configuration à revalider, puis à refaire si nécessaire ; outils du projet A réutilisables (`docs/J2_PREREQUISITES.md`) |
| R-03 Rendu sous Vulkan jamais essayé avec ce jeu | Élevé | J3 dédié ; deux pilotes GPU ; deux chemins de cibles de rendu |
| R-06 Longue traîne de défauts du code recompilé | Élevé | Critères par parcours ; outils et correctifs du projet A |
| R-04 API ReXGlue instable | Moyen | Épinglage et série de correctifs |

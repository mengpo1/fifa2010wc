# Feuille de route — Recompilation native de *2010 FIFA World Cup South Africa*

> Révisée le 2026-11-21 (mission 001, « Linux prioritaire »).
> **Plateforme prioritaire : Linux x86_64, sous NixOS 26.05.** macOS ARM64 n'est
> plus planifié avant qu'une version Linux soit jouable (jalon J5 atteint). Sa
> compatibilité future reste garantie par les règles d'architecture (D-006), qui
> s'appliquent dès J1.
> Les faits qui fondent cette feuille de route sont dans `docs/audit/`. Les décisions
> sont dans `docs/DECISIONS.md`.

## 1. Stratégie

1. **Ne rien réécrire de ce qui existe** : ReXGlue fournit le recompilateur, le runtime
   (noyau, XAM, système de fichiers), le backend Vulkan, l'audio SDL3 et les entrées
   SDL3, et il compile sous Linux et NixOS (vérifié pendant l'audit).
2. **Écrire un projet portable mince** au-dessus de ReXGlue : application, correctifs du
   jeu, couche plateforme isolée, configuration d'analyse, intégration Nix.
3. **Réutiliser le savoir des ports Windows** existants, surtout celui du projet A
   (BSD 3-Clause) : configuration d'analyse, correctifs du SDK, contournements GPU.
4. **Valider par jalons courts et mesurables**, chacun avec des critères objectifs (§4).
5. **Ressources propriétaires toujours hors du dépôt et hors du magasin Nix.**

## 2. Jalons

| Jalon | Objectif | Dépend de | Données du jeu requises |
|---|---|---|---|
| **J0** | Décisions préalables et identification de l'ISO | — | Lecture des en-têtes en clair et empreintes uniquement |
| **J1** | Chaîne de compilation Linux et NixOS (SDK, outils, tests), sans le jeu | D-009, D-011 | Aucune |
| **J2** | Projet portable : génération de code et édition de liens de l'exécutable Linux | J0, J1, **D-008** | XEX |
| **J3** | Démarrage jusqu'à l'écran-titre sous Vulkan | J2 | Jeu complet |
| **J4** | **Premier match jouable** (critères §4) | J3 | Jeu complet |
| **J5** | Stabilisation Linux : tous les modes, 60 i/s, sauvegardes, paquet Nix | J4 | Jeu complet |
| **J6** | macOS ARM64 (plateforme secondaire) | J5 | Jeu complet |

### J0 — Décisions préalables et identification de l'ISO (aucun code)

- Trancher **D-008** (déchiffrement des XEX).
- Appliquer la procédure d'identification sans déchiffrement
  (`docs/audit/ISO_REQUIREMENTS.md` §3) : format du disque, liste des fichiers,
  SHA-256 des deux XEX, en-têtes en clair (identifiant du titre, version, chiffrement,
  bibliothèques importées).
- Livrable : un rapport d'identification sans contenu propriétaire, avec le verdict
  « disque Europe du projet A, oui ou non ».

### J1 — Chaîne de compilation Linux et NixOS (sans le jeu)

- `flake.nix` épinglé sur nixos-26.05 :
  - dérivation du SDK ReXGlue depuis les sources, au commit retenu (D-011), avec la série
    de correctifs ; durcissement réglé ; rpath corrigé ;
  - `devShell` pour la compilation impure du jeu ;
  - enveloppe d'exécution (Vulkan, Wayland, X11, audio).
- Compilation et exécution des tests unitaires du SDK sous NixOS.
- Squelette du projet portable (CMake, préréglages `linux-amd64-*`, couches `app/`,
  `hooks/`, `platform/`), sans code généré.
- Pas de données du jeu, ce qui permet une CI publique.

### J2 — Génération de code et édition de liens

- Manifeste à deux modules (`default.xex` et `fifadllzf.xex`) et configuration
  d'analyse : celle du projet A si les empreintes concordent, sinon une analyse refaite
  avec ses outils.
- Correctifs du SDK nécessaires à ce jeu transposés vers le commit retenu. Au minimum
  l'équivalent de 0003 (table de fonctions) et de 0002 (module chargé par son nom nu) ;
  0005 (ISO comme racine) est facultatif, car l'ISO peut être extraite.
- Couche `platform/linux` : répertoires XDG, journaux, gestionnaire de plantage par
  signaux.

### J3 — Écran-titre sous Vulkan

- Contournements GPU du projet A activés par défaut.
- Correctif de démarrage équivalent à `boot_fixes.cpp`, si la même lecture d'adresse
  quasi nulle se produit.
- Captures et journaux de référence conservés **localement** pour les comparaisons.

### J4 — Premier match jouable

Voir les critères du §4.

### J5 — Stabilisation Linux

- Parcours de tous les modes hors ligne (Coupe du monde, Capitaine de son pays, tirs au
  but, entraînement ; liste exacte à établir depuis le menu du jeu à J4), sauvegardes,
  profils.
- 60 i/s en match ; échelle de rendu ; réglages.
- Paquet Nix « joueur » (sans aucune donnée du jeu) et documentation d'installation.

### J6 — macOS ARM64 (plateforme secondaire, après J5)

- Préréglages `mac-arm64-*` (déjà fournis par ReXGlue), Vulkan via MoltenVK.
- Implémentation de `platform/macos`.
- Validation des risques F-01 à F-04 de `docs/audit/RISKS.md`.

## 3. Premier jalon d'implémentation : options pour l'orchestrateur

Le choix porte sur **J1**, le seul jalon que le point juridique D-008 ne bloque pas, et
sur la base du SDK qu'il fixe.

| Option | Contenu | Avantages | Inconvénients |
|---|---|---|---|
| **1 — J1 sur ReXGlue v0.11.0** (retenue) | `flake.nix`, dérivation du SDK v0.11.0, tests du SDK, squelette du projet | Compilation sous Nix **déjà vérifiée** ; API actuelle (modules de pilotes) ; CI Linux et ARM64 en amont | Correctifs du projet A à réécrire pour v0.11.0 avant J2 (0003 et 0002 au minimum) |
| 2 — J1 sur `bd833a2` + correctifs du projet A | Reproduire la base exacte du port Windows qui fonctionne | Écart minimal avec une configuration connue pour faire tourner le jeu | Compilation Linux ou Nix de ce commit non vérifiée ; ancienne API ; migration vers v0.11 inévitable plus tard |
| 3 — J0 seul | Attendre D-008 et l'identification de l'ISO | Aucun travail perdu si l'ISO est d'une autre version | Le chemin critique ne progresse pas |

Recommandation : **option 1, menée en parallèle de J0.** J1 ne touche aucune donnée du
jeu et n'engage aucun déchiffrement. Il réduit les risques R-08 et R-15, et son résultat
reste valable quelle que soit la version de l'ISO.

**Décision** : l'orchestrateur a retenu l'option 1 (D-011, mission 002).

## 4. Critères de validation objectifs

Chaque critère est vérifiable par une commande, un compteur ou une liste de contrôle.
La machine de référence (processeur, GPU, pilote, NixOS 26.05) est consignée à chaque
validation.

### J1 — Chaîne de compilation

| ID | Critère | Mesure |
|---|---|---|
| C1.1 | Le SDK se compile depuis un dépôt propre par une seule commande Nix | Code de sortie 0 |
| C1.2 | Les tests unitaires du SDK passent sous NixOS | Rapport Catch2 sans échec |
| C1.3 | L'outil `rexglue` s'exécute sous NixOS sans `nix-ld` ni `steam-run` | `rexglue --help` rend 0 |
| C1.4 | Le pilote GPU Vulkan trouve le GPU sous NixOS | Journal d'initialisation du périphérique ; `vulkaninfo` dans l'enveloppe |
| C1.5 | Aucune donnée du jeu n'est requise ni présente | Script de contrôle des motifs interdits (§4.5) |

### J2 — Génération de code et édition de liens

| ID | Critère | Mesure |
|---|---|---|
| C2.1 | Génération de code sans erreur d'analyse | Résumé de `rexglue codegen` : 0 `UnresolvedCall`, 0 erreur de validation |
| C2.2 | L'exécutable est un ELF x86-64 natif | `readelf -h` ; aucune dépendance à Wine ni à une bibliothèque Windows |
| C2.3 | Aucun émulateur de processeur | Le code invité est entièrement recompilé ; ReXGlue n'a ni interpréteur ni JIT |
| C2.4 | Le code généré n'est pas versionné | `git status` et le script §4.5 |

### J3 — Écran-titre

| ID | Critère | Mesure |
|---|---|---|
| C3.1 | L'écran-titre s'affiche en moins de 60 s après le lancement | Horodatage dans le journal |
| C3.2 | Aucun accès invalide non géré ni erreur fatale | 0 occurrence dans le journal |
| C3.3 | Aucun écran noir de plus d'une seconde dans les séquences d'introduction | Inspection de la capture vidéo locale |

### J4 — Premier match jouable (critère de réussite de la phase Linux)

Définition : depuis le lancement, sous NixOS 26.05 x86_64, l'exécutable natif
permet de démarrer un **match amical** (« coup d'envoi »), de le jouer **jusqu'au
coup de sifflet final** et de revenir au menu principal, **trois fois de suite sans
plantage**.

| ID | Domaine | Critère | Mesure |
|---|---|---|---|
| C4.1 | Parcours | Titre → menu → choix des équipes → match → mi-temps → seconde période → écran de résultat → menu principal | Liste de contrôle ; 3 parcours sur 3 |
| C4.2 | Durée | Au moins un match avec la durée de mi-temps par défaut du jeu | Chronomètre du jeu en fin de match |
| C4.3 | Stabilité | 0 plantage, 0 blocage de plus de 2 s, 0 accès invalide non géré | Journaux des 3 parcours |
| C4.4 | Cadence | ≥ 30 i/s en match (cadence d'origine) ; temps d'image médian ≤ 33,4 ms ; 1 % des pires images ≥ 25 i/s | Statistiques du système graphique (`GetFrameStats`) consignées chaque seconde |
| C4.5 | Rendu | Visibles et corrects : terrain et lignes, joueurs, ballon, public et stade, score et chronomètre, noms des joueurs, ralentis, textes des menus | Liste de contrôle de 9 éléments ; aucun artefact persistant |
| C4.6 | Rendu (référence) | 5 scènes fixes (titre, menu principal, choix des équipes, coup d'envoi, ralenti) comparées à des captures de référence de la version d'origine, prises par l'utilisateur sur sa console ou avec un oracle de développement | Comparaison locale, écarts listés et acceptés ; aucune image versionnée |
| C4.7 | Audio | Musique des menus, foule, sifflet, commentaires audibles et synchrones | Liste de contrôle ; sous-alimentations < 1 % des périodes (`IAudioSystem::GetStats`) ; 0 erreur XMA dans le journal |
| C4.8 | Entrées | Manette par SDL3 : déplacement, passe courte, tir, passe en profondeur, centre, sprint, gestes techniques, pause ; clavier : mêmes actions | Liste de contrôle des actions |
| C4.9 | Persistance | Un réglage modifié et le profil sont conservés après redémarrage | Test « modifier, quitter, relancer » |
| C4.10 | Fidélité | Aucune ressource du jeu modifiée ni remplacée ; données lues depuis la copie de l'utilisateur | Empreintes de l'ISO inchangées avant et après |
| C4.11 | Hygiène | Aucune donnée propriétaire dans le dépôt ni dans `/nix/store` | Script §4.5 et recherche des empreintes dans le magasin |

### J5 — Stabilisation (aperçu)

60 i/s en match, tous les modes hors ligne parcourus, sauvegardes de tournoi rechargées,
une heure de jeu sans plantage, et le paquet Nix installé sur une machine NixOS vierge.

### 4.5 Contrôle des données propriétaires (à automatiser dès J1)

Un script du projet vérifie, avant chaque commit et en CI :
- l'absence de fichiers `*.iso`, `*.xex`, `*.xexp`, `*.big`, `*.bin` et de dossiers
  `generated/` ou `out/` dans l'arbre suivi ;
- l'absence de chaînes de clés XEX ou AES connues ;
- la taille des fichiers ajoutés (alerte au-delà de 1 Mo).

## 5. Ce qui a changé par rapport à la planification initiale

- macOS ARM64 passe de cible prioritaire à **plateforme secondaire différée (J6)**. Son
  architecture reste prévue (D-006).
- Linux x86_64 sous NixOS devient la **seule cible des jalons J1 à J5**.
- Le backend graphique est **Vulkan** (D-003) ; D3D12 sort du périmètre.
- Le point juridique du déchiffrement des XEX devient une **décision bloquante explicite**
  (D-008), avant J2.

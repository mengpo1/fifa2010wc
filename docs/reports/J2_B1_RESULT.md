# Rapport de l'étape B1 de J2 — extraction de l'arborescence du disque, et PB-1

> Étape B1 de `docs/J2_PLAN.md` §4.1, [ticket #32](https://github.com/mengpo1/fifa2010wc/issues/32).
> **B1 est exécutée et validée : PB-1 est franchi** (D-020), le 2026-11-27.
> Ce rapport ne reprend que des nombres et des statuts. Il ne contient ni fichier du jeu,
> ni rapport brut, ni empreinte privée, ni chemin du dossier privé (D-007, CP-5).
> Étiquettes : **[V]** fait vérifié, **[H]** hypothèse, **[I]** inconnue.

## 1. Sources

- **Autorisation de l'extraction réelle par le porteur**, et avis favorable de
  l'orchestrateur sur la répétition :
  [commentaire 7218617373](https://github.com/mengpo1/fifa2010wc/issues/32#issuecomment-7218617373).
- **Validation de l'orchestrateur, PB-1 franchi** :
  [commentaire 7218840297](https://github.com/mengpo1/fifa2010wc/issues/32#issuecomment-7218840297).
- **Outil** : `tools/b1_extract.py`, version 6, `main` à `773d1a8` (fusion de la PR #34),
  procédure `docs/J2_B1_EXTRACTION.md`.
- **Machine** : la machine NixOS du porteur, dans `$WC2010_PRIVATE_DIR`. Rien ne s'est
  exécuté en CI ni dans le conteneur de Claude Code.

Les résultats viennent des résumés locaux transmis par le porteur, après CP-5.
L'orchestrateur et Claude Code n'ont aucun accès aux données privées : ces résultats ne
sont pas vérifiés de façon indépendante.

## 2. Répétition et dernier `prepare`

| Élément | Résultat |
|---|---|
| `rehearse`, 2026-11-27 à 12:30:49 UTC | Sans interruption ; seul constat initial `core-proof-missing` |
| Sonde de confinement | 26 sur 26 |
| Fermeture du magasin (D-019) | 273 chemins, valide |
| Preuve de l'option B (D-018) | `proof_acquired True` |
| Plantage témoin, limite `0` | Signal 11, identifié, journalisé par le programme du tube, sans fichier *core* |
| Plantage à la limite `1` | Signal 11, identifié, **aucune entrée** observée |
| `preflight`, `postflight` | OK |
| Montages, *core dumps*, CP-3 | Aucun changement de montage, aucun *core dump* inattendu, aucune nouvelle correspondance |
| `prepare`, 12:36:06 UTC | Code 0, aucun constat, `proof_found True`, rapport J0 concordant, `game/` vide |

## 3. Extraction (`run`) et critères de PB-1

Exécution commencée à 12:47:21 UTC.

| Critère | Attendu | Résultat |
|---|---|---|
| Code de sortie de l'outil | 0 | **0**, `outcome: no finding` |
| `rexglue vfs dump` | Code 0 | **0**, type GDFX |
| Nœuds de ReXGlue, racine comprise | 58 | **58** |
| Fichiers, racine non comptée | 49 | **49** |
| Dossiers | 8 | **8** |
| Anomalies, noms cachés | 0 | **0**, **0** |
| SHA-256 de `default.xex` et de `fifadllzf.xex` | Ceux du rapport J0 | **concordants** (`match`) |
| Image (SHA-256 et identité) | Inchangée, et égale au rapport J0 avant et après | **inchangée et concordante** |
| Sonde, fermeture, preuve | 26 sur 26, valide, reconnue | **26 sur 26, 273 chemins, preuve reconnue** |
| `preflight`, `postflight` | OK | **OK** ; 6 dossiers systemd exclus, selon la portée documentée (`J2_PHASE_B_CONTROLS.md` §3.1) |
| Montages | Aucun changement, aucun événement | **aucun** |
| *Core dumps* | Aucun | **aucun** |
| CP-3 | Aucune nouvelle correspondance | **aucune** |
| Dossier privé | Aucun dossier remplacé | **aucun** |

**Décision de l'orchestrateur** : B1 validée, **PB-1 franchi**.

## 4. Limites

- Les résultats proviennent du résumé transmis par le porteur. Il n'y a ni accès
  indépendant aux données privées, ni garantie exhaustive d'absence de fuite.
- La preuve de l'option B est une observation, dans les conditions essayées, et non une
  garantie absolue (`J2_B1_EXTRACTION.md` §6.3).
- **R-01** (risque juridique résiduel) reste ouvert.
- D-007, D-018 et D-019 restent en vigueur.

## 5. Ce qui suit

- `game/` contient désormais l'arborescence validée. C'est l'entrée de B2, qui doit la
  trouver inchangée (`J2_B2_COMPATIBILITY.md`).
- **B2 reste soumis à un mandat distinct.** PB-1 n'autorise ni l'analyse des modules, ni
  la génération de code. Sa procédure est proposée dans `docs/J2_B2_COMPATIBILITY.md`, sans
  données du jeu.

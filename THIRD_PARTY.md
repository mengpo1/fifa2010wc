# Éléments repris d'autres projets

> Tenu selon D-010 (`docs/DECISIONS.md`) : chaque élément importé d'un autre projet est
> listé ici avec sa provenance et la notice de sa licence. Les dépendances que Nix
> construit ou télécharge (ReXGlue, nixpkgs) sont décrites dans `docs/DEPENDENCIES.md`.

## Projet A — CalinGraphics/fifa-world-cup-2010-recompiled

- **Source** : <https://github.com/CalinGraphics/fifa-world-cup-2010-recompiled>, commit
  `498d18a`.
- **Licence** : BSD 3-Clause, notice reproduite ci-dessous. Elle ne couvre que le code du
  projet, ni le jeu, ni son contenu, ni du code recompilé à partir de lui.

| Élément repris | Fichier du projet A | Fichier ici | Adaptation |
|---|---|---|---|
| Correctif du SDK 0003 « function-table-base », et la partie de 0002 qui transmet la base au chargement d'un module | `patches/rexglue-sdk/0003-function-table-base.patch` et `0002-find-module-by-file-name.patch` (pour `rexglue-sdk` `bd833a2`) | `patches/rexglue-sdk/0001-function-table-base.patch` | Réécrit pour ReXGlue v0.11.0. Ajouts : plages et tailles sur 64 bits, contrôle de la table face à sa propre image, allocation exclusive des pages, validation de la clé, tests unitaires (`docs/J2_A3_FUNCTION_TABLE.md` §5) |

Aucune adresse ni aucune valeur de la configuration d'analyse du projet A n'est reprise
(CP-7, `docs/J2_PREREQUISITES.md` §6).

```text
BSD 3-Clause License

Copyright (c) 2026, Miertescu Stefan-Calin

This license covers only this project's own code. It does not cover the game,
its content, or any code recompiled from it.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

#!/usr/bin/env python3
"""J2 step B2: the compatibility check (docs/J2_B2_COMPATIBILITY.md).

A first `rexglue codegen` of the two modules extracted at B1, with the configuration of
project A as a test input only, run as a controlled step of the engine of
tools/b1_extract.py (docs/J2_LOCAL_STEP_ENGINE.md). This file is the B2 profile of that
engine: it reuses its checks, sandbox, proof of option B (D-018), store closure (D-019),
preflight and postflight, state, resume, summary and diagnosis, and its tree survey, and
adds only what is proper to B2:

- game/ is an input, read-only in the sandbox; it must still be the tree that PB-1
  validated, and its inventory (content, metadata and identity of every entry) must be
  the same before and after the step;
- the configuration inputs that codegen consumes (the manifest, the configurations it
  includes, transitively, hook sources and templates) are inventoried; all but the
  manifest must lie in project/config/, read-only in the sandbox; the manifest may change
  only by its sdk_version line, and codegen.d must list nothing else;
- the arbitrations of D-021: no consumed configuration sets function_table_base (F-a),
  config/default.toml is the kept original less that one line and nothing else (G-3),
  the original is consumed by nothing, the time-out is two hours at most (T-a), the log
  level is info (L-a);
- the sandboxed command is `rexglue --log-level info --log-file <run folder>/codegen.log
  codegen <manifest>`, never with --force;
- C2.1 (0 unresolved call, 0 validation error) is read from that log by the parser of
  tools/address_compare.py (A8-bis), which refuses an empty or truncated log; the
  completeness of the generation (a valid codegen.stamp per module, every output it
  lists present, nothing unlisted) is a separate criterion.

A proposal: a real run of B2 needs its own mandate (D-020). Nothing here reads a game file
before the step, decodes, or writes outside the private folder.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import time
import tomllib

VERSION = 1
HERE = os.path.dirname(os.path.realpath(__file__))
MANIFEST = os.path.join("project", "wc2010_manifest.toml")
CONFIG_DIR = os.path.join("project", "config")
RUN_STEP = "codegen"

# What ReXGlue v0.11.0 reads and writes, from its sources (docs/J2_B2_COMPATIBILITY.md §3,
# §6): include depth (src/codegen/config.cpp:24), hook sources (src/codegen/hook_scan.cpp
# :527), keys that name a file or a folder (src/codegen/config_keys.cpp:25-34), outputs
# (src/codegen/codegen_writer.cpp:306-417, project_recompiler.cpp:575-709).
MAX_INCLUDE_DEPTH = 32
HOOK_SUFFIXES = (".cpp", ".cc", ".h", ".hpp")
MANIFEST_ONLY_KEYS = ("file_path", "out_directory_path", "guest_path", "hook_sources")
STAMP = "codegen.stamp"
BUILD_STAMP = "codegen.build.stamp"
DEPFILE = "codegen.d"
REGISTRY_FILES = ("module_registry.cpp", "dll_targets.cmake")
REQUIRED_OUTPUTS = ("_pch.h", "_funcs.h", "_init.h", "_init.cpp", "_register.cpp")
REQUIRED_NAMES = ("sources.cmake", "codegen.partition.json", "codegen.mmio.json")
NUMBERED_OUTPUTS = (re.compile(r"_funcs\.\d+\.h$"), re.compile(r"_recomp\.\d+\.cpp$"))
# The arbitrations of the owner for B2 (D-021, docs/J2_B2_COMPATIBILITY.md §11):
# F-a, no value of function_table_base imposed: a consumed configuration that sets it, even
# to 0, which does not undo an inherited value (src/codegen/config.cpp:40-41), is a
# conflict to arbitrate, never resolved here; T-a, two hours at most; L-a, the info level.
TABLE_BASE_KEY = "function_table_base"
MAX_TIMEOUT = 7200
LOG_LEVEL = "info"
MIB = 1 << 20
# Anomalies of survey_tree that mean the inventory could not be completed.
UNREADABLE = ("unreadable folder", "unreadable entry", "changed while counted")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"error: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(path, folder):
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def inventory(engine, root, content=True):
    """The inventory of a tree by the engine's survey (links never followed, every
    anomaly reported): its entries, their SHA-256 as one digest, and its anomalies split
    into the unreadable ones (the inventory is incomplete) and the others (links, special
    files, hard links, other file systems)."""
    survey = engine.survey_tree(root, [], listing=True, content=content)
    entries = survey.get("entries", [])
    digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
    unreadable = [a for a in survey["anomalies"] if a[0] in UNREADABLE]
    others = [a for a in survey["anomalies"] if a[0] not in UNREADABLE]
    return {"survey": survey, "entries": entries, "digest": digest,
            "unreadable": unreadable, "others": others}


def config_inputs(manifest, config_root):
    """The configuration inputs `rexglue codegen` consumes for this manifest, resolved as
    ReXGlue does (src/codegen/config.cpp:428-480, manifest.cpp:68-160,
    project_recompiler.cpp:57-75 and 278-290), but with no link followed:

    - the `includes` of the top level of the manifest (the shared layer) and of each binary
      table, relative to the manifest folder, then those of each included file, relative
      to it, depth first, at most 32 levels, circular includes refused;
    - `template_dir`, wherever it is set, relative to the manifest folder;
    - the hook sources of [project].hook_sources.

    Every input must be a regular file (or folder) inside project/config/, reached with no
    link. Returns (inputs, findings): inputs holds the configuration files in load order,
    those reached from binary tables (the ones codegen.d lists), the hook files, the
    template folders, the deepest level and the counts of entries, function_table_base
    settings included."""
    findings = []
    base = os.path.dirname(os.path.realpath(manifest))
    root = os.path.realpath(config_root)
    inputs = {"configs": [], "binary_configs": [], "shared_configs": [], "hook_files": [],
              "template_dirs": [], "depth": 0, "functions": 0, "crt": 0, "table_base": 0}

    def placed(label, path, folder=False):
        """The real path of an input, or None with a finding."""
        if not os.path.lexists(path):
            findings.append(("test-config-invalid", f"{label}: not found"))
            return None
        real = os.path.realpath(path)
        if real != path:
            findings.append(("config-outside", f"{label}: reached through a link"))
            return None
        if not inside(real, root) or real == root and not folder:
            findings.append(("config-outside", f"{label}: outside {CONFIG_DIR}/"))
            return None
        st = os.lstat(real)
        if folder and not stat.S_ISDIR(st.st_mode) or not folder and (
                not stat.S_ISREG(st.st_mode) or st.st_nlink != 1):
            findings.append(("config-outside", f"{label}: not a regular "
                                               f"{'folder' if folder else 'file'}"))
            return None
        return real

    def count(table):
        functions = table.get("functions", {})
        inputs["functions"] += len(functions) if isinstance(functions, dict) else 0
        inputs["crt"] += sum(1 for key in ("setjmp_address", "longjmp_address")
                             if key in table)
        inputs["table_base"] += TABLE_BASE_KEY in table
        if "template_dir" in table:
            value = table["template_dir"]
            if not isinstance(value, str) or not value:
                findings.append(("test-config-invalid", "template_dir is not a string"))
            else:
                real = placed("template_dir", os.path.normpath(os.path.join(base, value)),
                              folder=True)
                if real and real not in inputs["template_dirs"]:
                    inputs["template_dirs"].append(real)

    def visit(table, folder, depth, chain, layer, label):
        includes = table.get("includes", [])
        if not isinstance(includes, list):
            findings.append(("test-config-invalid", f"{label}: includes is not an array"))
            return
        for index, include in enumerate(includes):
            where = f"{label} includes #{index}"
            if not isinstance(include, str) or not include:
                # ReXGlue skips such an element silently: refused here.
                findings.append(("test-config-invalid", f"{where}: not a path"))
                continue
            if depth + 1 > MAX_INCLUDE_DEPTH:
                findings.append(("test-config-invalid", f"{where}: deeper than "
                                                        f"{MAX_INCLUDE_DEPTH} levels"))
                continue
            real = placed(where, os.path.normpath(os.path.join(folder, include)))
            if real is None:
                continue
            rel = os.path.relpath(real, root)
            if real in chain:
                findings.append(("test-config-invalid", f"{where}: circular include"))
                continue
            try:
                with open(real, "rb") as f:
                    parsed = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                findings.append(("test-config-invalid", f"{rel}: {type(exc).__name__}"))
                continue
            inputs["depth"] = max(inputs["depth"], depth + 1)
            reached = inputs[f"{layer}_configs"]
            if real not in reached:
                reached.append(real)
            if real not in inputs["configs"]:
                inputs["configs"].append(real)
                count(parsed)
                for key in MANIFEST_ONLY_KEYS:
                    if key in parsed:
                        findings.append(("test-config-invalid", f"{rel}: {key} belongs to "
                                                                "the manifest"))
            visit(parsed, os.path.dirname(real), depth + 1, chain + [real], layer, rel)

    with open(manifest, "rb") as f:
        table = tomllib.load(f)
    shared = {k: v for k, v in table.items() if k not in ("project", "entrypoint", "modules")}
    count(shared)
    visit(shared, base, 0, [], "shared", "manifest")
    binaries = [table.get("entrypoint")] + list(table.get("modules", []) or [])
    for index, binary in enumerate(binaries):
        if isinstance(binary, dict):
            count(binary)
            visit(binary, base, 0, [], "binary", f"binary #{index}")
    project = table.get("project", {})
    for index, folder in enumerate(project.get("hook_sources", []) or []):
        if not isinstance(folder, str) or not folder:
            continue  # private_project.check_manifest reports it
        real = placed(f"hook_sources #{index}", os.path.normpath(os.path.join(base, folder)),
                      folder=True)
        if real is None:
            continue
        for top, _, names in os.walk(real, onerror=lambda exc: findings.append(
                ("tree-unreadable", f"hook_sources #{index}: {exc.strerror}"))):
            inputs["hook_files"] += [os.path.join(top, n) for n in sorted(names)
                                     if n.endswith(HOOK_SUFFIXES)]
    return inputs, findings


def read_depfile(path):
    """The inputs of codegen.d (output_stamp.cpp:84-119): `target:` then one escaped
    absolute path per continued line. Returns (target, inputs) or None if unreadable or in
    another format."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.endswith("\n"):
        return None
    parts = text[:-1].split(" \\\n  ")
    if not parts[0].endswith(":"):
        return None

    def unescape(value):
        out, i = [], 0
        while i < len(value):
            if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in " #":
                out.append(value[i + 1])
                i += 2
            elif value.startswith("$$", i):
                out.append("$")
                i += 2
            else:
                out.append(value[i])
                i += 1
        return "".join(out)

    return unescape(parts[0][:-1]), [os.path.normpath(unescape(p)) for p in parts[1:]]


def read_stamp(path):
    """The outputs listed by a codegen.stamp (output_stamp.cpp:18-46), or None if it is
    missing, not a regular file, or not a stamp of version 1 with a fingerprint and a
    non-empty list of plain names."""
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            return None
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict) or doc.get("version") != 1:
        return None
    fingerprint, outputs = doc.get("fingerprint"), doc.get("outputs")
    if not isinstance(fingerprint, str) or not fingerprint or not isinstance(outputs, list):
        return None
    if not outputs or len(set(outputs)) != len(outputs) or not all(
            isinstance(n, str) and n and n not in (".", "..") and os.sep not in n
            for n in outputs):
        return None
    return {"fingerprint": fingerprint, "outputs": outputs}


def make_profile(engine, compare, project):
    """The B2 profile, built on the loaded engine and tools."""

    # Names, codes and facts of B2, in the allowlists of the engine's summary.
    engine.STEP_NAMES = engine.STEP_NAMES + (
        "game-tree", "project", "test-config", "resources", "game-before",
        "before-codegen", RUN_STEP,
        "game-after", "config-after", "manifest-after", "generated", "outputs",
        "codegen-inputs", "c21")
    engine.FINDING_CODES.update({
        "game-tree-differs": "game/ is not the tree validated at PB-1 (counts, anomalies or "
                             "module hashes)",
        "game-changed": "the inventory of game/ (content, metadata or identity of an "
                        "entry) changed during the step",
        "tree-unreadable": "an entry of game/, project/config/ or generated/ could not be "
                           "read or changed while read: the inventory is incomplete",
        "manifest-invalid": "the private manifest fails the checks of private_project",
        "manifest-changed": "the manifest changed otherwise than by its sdk_version line",
        "project-unexpected-entry": "project/ holds something else than the manifest and "
                                    "config/",
        "config-outside": "a configuration input lies outside project/config/, is reached "
                          "through a link, or is not a regular file",
        "config-changed": "the inventory of project/config/ changed between prepare and "
                          "the step, or during the step",
        "codegen-input-unexpected": "codegen.d lists an input outside the inventory of B2",
        "config-inventory-differs": "a configuration of the inventory is missing from "
                                    "codegen.d: ReXGlue did not consume what B2 checked",
        "generated-not-empty": "an output folder of the manifest is missing or not empty",
        "generated-anomaly": "a link, a special file, a hard link or a file outside the "
                             "output folders in generated/",
        "generation-incomplete": "codegen returned 0, but generated/ could not be read "
                                 "whole, or an output folder lacks a valid codegen.stamp, "
                                 "a listed output, an expected kind of output, or the "
                                 "files of the entry module, or the log summary disagrees "
                                 "with the stamps",
        "generated-unlisted": "an output folder holds a file that no codegen.stamp lists",
        "test-config-absent": "the private copy consumes no configuration file: the test "
                              "input of project A is missing",
        "table-base-conflict": "a consumed configuration sets function_table_base: option "
                               "F-a (D-021) imposes none; a separate arbitration is needed "
                               "before B2, nothing is changed here",
        "timeout-above-t-a": "--timeout is above the two hours of option T-a (D-021), or "
                             "not positive",
        "g3-original-missing": "config/original/default.toml, the pinned original kept for "
                               "the derogation G-3 (D-021), is missing or not a regular file",
        "g3-derogation-invalid": "config/default.toml is not the kept original less its one "
                                 "function_table_base line (G-3), or is not consumed",
        "g3-original-consumed": "an include reaches config/original/: the kept original "
                                "must stay out of the consumed inputs (G-3)",
        "test-config-invalid": "an included configuration is missing, unreadable, not "
                               "TOML, circular, too deep, or sets a key of the manifest",
        "app-config-present": "app/rexglue.toml exists: ReXGlue would read it",
        "xexp-present": "a .xexp file lies next to a module: ReXGlue would apply it",
        "codegen-not-started": "bubblewrap did not start the code generation",
        "codegen-timeout": "the code generation was stopped after the time-out",
        "codegen-crashed": "the code generation was killed by a signal",
        "codegen-failed": "the code generation exited with an error",
        "codegen-log-refused": "the codegen log is empty, truncated, or in an unknown "
                               "format (address_compare refused it)",
        "c21-not-met": "C2.1 is not met: an unresolved call, a millicode error or a "
                       "configuration error",
    })
    engine.EXTRACTION_GATES.update(("test-config-absent", "table-base-conflict",
                                    "timeout-above-t-a", "g3-original-missing",
                                    "g3-derogation-invalid", "g3-original-consumed"))
    engine.PROBE_CHECK_NAMES.update(("write-denied-game", "write-denied-project-config",
                                     "writable-generated", "writable-project",
                                     "shm-private"))
    _int, _bool = engine._int, engine._bool
    engine.SUMMARY_FACTS.update({
        "game-tree": {"game_files": _int, "game_directories": _int, "game_anomalies": _int,
                      "game_modules_match": _bool},
        "project": {"manifest_findings": _int, "output_folders": _int,
                    "output_folders_empty": _bool, "project_entries_ok": _bool},
        "test-config": {"config_files": _int, "binary_config_files": _int,
                        "shared_config_files": _int, "config_tree_files": _int,
                        "config_unused_files": _int, "include_depth": _int,
                        "hook_files": _int, "template_dirs": _int,
                        "function_entries": _int, "crt_entries": _int,
                        "table_base_settings": _int, "timeout_seconds": _int,
                        "g3_original_present": _bool, "g3_derogation_ok": _bool},
        "resources": {"memory_total_mib": _int, "memory_available_mib": _int,
                      "swap_total_mib": _int, "disk_free_mib": _int,
                      "shm_default_limit_mib": _int},
        "game-before": {"game_files": _int, "game_modules_match": _bool,
                        "game_entries_hashed": _int},
        RUN_STEP: {"signal": engine.SIGNAL_NUMBER},
        "game-after": {"game_unchanged": _bool, "game_modules_match": _bool,
                       "game_unreadable": _int},
        "config-after": {"config_unchanged": _bool, "project_entries_ok": _bool},
        "manifest-after": {"manifest_rewritten": _bool, "only_sdk_version_changed": _bool},
        "generated": {"generated_files": _int, "generated_anomalies": _int,
                      "generated_unreadable": _int},
        "outputs": {"modules_expected": _int, "modules_with_valid_stamp": _int,
                    "listed_outputs": _int, "missing_outputs": _int,
                    "modules_with_every_kind": _int, "unlisted_files": _int,
                    "entry_files_ok": _bool, "log_summary_matches": _bool,
                    "generation_complete": _bool},
        "codegen-inputs": {"depfile_found": _bool, "depfile_inputs": _int,
                           "unexpected_inputs": _int, "configs_not_in_depfile": _int},
        "c21": {"unresolved_calls": _int, "millicode_errors": _int, "config_errors": _int,
                "entry_diagnostics": _int, "validation_failed": _bool, "c21_met": _bool},
    })

    class B2Profile(engine.Profile):
        name = "b2"
        title = "B2"
        tool = "b2_codegen"
        version = VERSION
        run_step = RUN_STEP
        description = ("J2 step B2: compatibility check, a first rexglue codegen of the "
                       "modules extracted at B1, on the user's machine "
                       "(docs/J2_B2_COMPATIBILITY.md).")
        # project/ stays writable: ReXGlue rewrites the manifest through a temporary file
        # in its folder, then a rename (manifest.cpp:204-261). Its configuration inputs, in
        # project/config/, are bound read-only again over it.
        writable = ("generated", "project", "app", "tmp")
        read_only = ("game", CONFIG_DIR)
        components = engine.PRIVATE_COMPONENTS + ("generated", "project", CONFIG_DIR)
        required = ("game", "logs", "generated", "project", CONFIG_DIR)
        decision = ("this tool does not declare PB-2; the orchestrator, then the owner, "
                    "decide. A success does not prove the identity of the code.")
        file = os.path.realpath(__file__)

        def probe_checks(self):
            """The checks of B1, with game/ and project/config/ write-denied, generated/
            and project/ writable, and a private /dev/shm for the guest memory."""
            return super().probe_checks() + ("shm-private",)

        def manifest(self, ctx):
            return os.path.join(ctx.private, MANIFEST)

        def config_root(self, ctx):
            return os.path.join(ctx.private, CONFIG_DIR)

        def g3_state(self, ctx, inputs):
            """Derogation G-3 (D-021), checked at each prepare by the same function as
            stage-config (private_project.g3_check): the kept original is a regular file,
            consumed by nothing, and config/default.toml, consumed, is exactly the
            original less its one top-level function_table_base line."""
            root = os.path.realpath(self.config_root(ctx))
            original = os.path.join(root, project.G3_ORIGINAL)
            staged = os.path.join(root, project.G3_FILE)
            findings, present, ok = [], False, False
            try:
                st = os.lstat(original)
                present = stat.S_ISREG(st.st_mode) and st.st_nlink == 1
            except OSError:
                pass
            if not present:
                findings.append(("g3-original-missing", project.G3_ORIGINAL))
            else:
                try:
                    with open(original, "rb") as f:
                        kept = f.read()
                    with open(staged, "rb") as f:
                        copy = f.read()
                    problems = project.g3_check(kept, copy)
                except OSError as exc:
                    problems = [f"{project.G3_FILE}: {exc.strerror}"]
                consumed = (inputs or {}).get("configs", [])
                if consumed and staged not in consumed:  # none: test-config-absent says it
                    problems.append(f"{project.G3_FILE} is not consumed")
                ok = not problems
                findings += [("g3-derogation-invalid", text) for text in problems]
            folder = os.path.dirname(original)
            if any(inside(path, folder) for path in (inputs or {}).get("configs", [])):
                findings.append(("g3-original-consumed", "an include"))
            return {"g3_original_present": present, "g3_derogation_ok": ok}, findings

        def resources(self, ctx):
            """Option T-a: the memory and the free disk of the private folder, in MiB,
            before the step. The sandbox's /dev/shm, where the guest memory goes, is a
            tmpfs of the default size, half the memory (measured, §11.3). Only numbers;
            no need is claimed."""
            facts = {}
            try:
                with open(ctx.args.meminfo, encoding="ascii") as f:
                    info = {line.split(":")[0]: int(line.split()[1]) for line in f
                            if line.split()[1:2] and line.split()[1].isdigit()}
                facts.update(memory_total_mib=info.get("MemTotal", 0) // 1024,
                             memory_available_mib=info.get("MemAvailable", 0) // 1024,
                             swap_total_mib=info.get("SwapTotal", 0) // 1024,
                             shm_default_limit_mib=info.get("MemTotal", 0) // 2048)
            except (OSError, ValueError, IndexError):
                pass
            try:
                st = os.statvfs(ctx.private)
                facts["disk_free_mib"] = st.f_bavail * st.f_frsize // MIB
            except OSError:
                pass
            return facts

        # --- inventories ----------------------------------------------------------------

        def game_figures(self, ctx, content=False):
            """The tree of game/ against the reference of PB-1: counts, no anomaly, module
            hashes. With `content`, also the inventory of every entry."""
            reference = ctx.reference
            survey = engine.survey_tree(ctx.game, list(reference["modules"]),
                                        listing=content, content=content)
            modules_match = all(
                survey["modules"].get(name, {}).get("sha256") == sha
                for name, sha in reference["modules"].items())
            facts = {"game_files": survey["files"], "game_directories": survey["directories"],
                     "game_anomalies": len(survey["anomalies"]),
                     "game_modules_match": modules_match}
            met = (survey["files"] == reference["files"] and
                   survey["directories"] == reference["directories"] and
                   not survey["anomalies"] and modules_match)
            return survey, facts, met

        def project_entries_ok(self, ctx):
            """project/ holds the manifest, a regular file, and config/, nothing else."""
            folder = os.path.join(ctx.private, "project")
            try:
                names = set(os.listdir(folder))
                st = os.lstat(self.manifest(ctx))
            except OSError:
                return False
            return (names == {os.path.basename(MANIFEST), "config"} and
                    stat.S_ISREG(st.st_mode) and st.st_nlink == 1)

        def config_state(self, ctx):
            """The inventory of project/config/ and the configuration inputs: (inputs,
            inventory, findings)."""
            tree = inventory(engine, self.config_root(ctx))
            findings = [("tree-unreadable", f"{CONFIG_DIR}/: {kind}")
                        for kind, _ in tree["unreadable"]]
            findings += [("config-outside", f"{CONFIG_DIR}/: {kind}")
                         for kind, _ in tree["others"]]
            try:
                inputs, found = config_inputs(self.manifest(ctx), self.config_root(ctx))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                inputs, found = None, [("manifest-invalid", type(exc).__name__)]
            return inputs, tree, findings + found

        # --- prepare --------------------------------------------------------------------

        def prepare_inputs(self, ctx, steps):
            findings, facts = [], {}
            for rel in self.components:
                engine.check_component(ctx, rel, findings, required=rel in self.required)
            steps.add("folders", "ok", facts=facts, findings=findings)

            survey, facts, met = self.game_figures(ctx)
            findings = [] if met else [("game-tree-differs", "game/ is not the PB-1 tree")]
            for xex in ctx.reference["modules"]:
                stem = os.path.splitext(xex)[0]
                if os.path.lexists(os.path.join(ctx.game, stem + ".xexp")):
                    findings.append(("xexp-present", f"{stem}.xexp next to {xex}"))
            steps.add("game-tree", "ok", facts=facts, findings=findings)

            findings, facts = [], {}
            manifest = self.manifest(ctx)
            found, resolved = project.check_manifest(manifest, ctx.private)
            findings += [("manifest-invalid", text) for text in found]
            outputs = [path for label, path in resolved.items()
                       if label.endswith(".out_directory_path")]
            facts["manifest_findings"] = len(found)
            facts["output_folders"] = len(outputs)
            empty = True
            for out in outputs:
                try:
                    if os.path.islink(out) or not os.path.isdir(out) or os.listdir(out):
                        empty = False
                except OSError:
                    empty = False
            if not empty or not outputs:
                findings.append(("generated-not-empty", "an output folder is missing, not a "
                                                        "folder, or not empty"))
            facts["output_folders_empty"] = empty and bool(outputs)
            facts["project_entries_ok"] = self.project_entries_ok(ctx)
            if not facts["project_entries_ok"]:
                findings.append(("project-unexpected-entry", "project/"))
            if os.path.lexists(os.path.join(ctx.private, "app", "rexglue.toml")):
                findings.append(("app-config-present", "app/rexglue.toml"))
            steps.add("project", "ok", facts=facts, findings=findings)
            # The binaries in manifest order (entry first, as ReXGlue writes them), their
            # modules and output folders, relative to the private folder.
            self._binaries = []
            for label in [label for label in resolved if label.endswith(".file_path")]:
                head = label[:-len(".file_path")]
                out = resolved.get(f"{head}.out_directory_path")
                if out:
                    self._binaries.append({
                        "label": head, "entry": head == "[entrypoint]",
                        "module": os.path.relpath(resolved[label], ctx.private),
                        "out": os.path.relpath(out, ctx.private)})

        def prepare_last(self, ctx, steps):
            """The test input of project A: the configuration inputs codegen will consume,
            and the inventory of project/config/. Only counts reach the summary; the
            addresses, paths and hashes stay local."""
            facts = {"config_files": 0, "binary_config_files": 0, "shared_config_files": 0,
                     "config_tree_files": 0, "config_unused_files": 0, "include_depth": 0,
                     "hook_files": 0, "template_dirs": 0, "function_entries": 0,
                     "crt_entries": 0, "table_base_settings": 0,
                     "timeout_seconds": ctx.args.timeout}
            inputs, tree, findings = self.config_state(ctx)
            files = [e[0] for e in tree["entries"] if e[1] == "file"]
            facts["config_tree_files"] = len(files)
            if inputs:
                root = os.path.realpath(self.config_root(ctx))
                used = {os.path.relpath(p, root) for p in inputs["configs"] +
                        inputs["hook_files"]}
                for folder in inputs["template_dirs"]:
                    used.update(f for f in files
                                if inside(os.path.join(root, f), folder))
                facts.update(config_files=len(inputs["configs"]),
                             binary_config_files=len(inputs["binary_configs"]),
                             shared_config_files=len(inputs["shared_configs"]),
                             config_unused_files=len(set(files) - used),
                             include_depth=inputs["depth"],
                             hook_files=len(inputs["hook_files"]),
                             template_dirs=len(inputs["template_dirs"]),
                             function_entries=inputs["functions"],
                             crt_entries=inputs["crt"],
                             table_base_settings=inputs["table_base"])
            if not facts["config_files"]:
                findings.append(("test-config-absent", "no configuration file consumed"))
            if facts["table_base_settings"]:
                findings.append(("table-base-conflict", f"{facts['table_base_settings']} "
                                                        "consumed tables"))
            if not 0 < ctx.args.timeout <= MAX_TIMEOUT:
                findings.append(("timeout-above-t-a", f"{ctx.args.timeout} s"))
            g3_facts, g3_findings = self.g3_state(ctx, inputs)
            facts.update(g3_facts)
            findings += g3_findings
            steps.add("test-config", "ok", facts=facts, findings=findings)
            steps.add("resources", "ok", facts=self.resources(ctx),
                      notes=["recorded before the step; the needs of a real generation "
                             "are unknown (docs/J2_B2_COMPATIBILITY.md §11.3)"])
            try:
                manifest_sha = file_sha256(self.manifest(ctx))
            except OSError:
                manifest_sha = None
            private = os.path.realpath(ctx.private)
            return {"manifest_sha256": manifest_sha, "config_digest": tree["digest"],
                    "binary_configs": [os.path.relpath(p, private) for p in
                                       (inputs or {}).get("binary_configs", [])],
                    "binaries": getattr(self, "_binaries", []),
                    "outputs": [os.path.join(ctx.private, b["out"])
                                for b in getattr(self, "_binaries", [])]}

        # --- around the marker ----------------------------------------------------------

        def before_marker(self, ctx, steps, state, extract):
            """game/ before the step: the PB-1 figures again, and the inventory of every
            entry, its content hashed."""
            if not extract:
                return
            started = time.monotonic()
            survey, facts, met = self.game_figures(ctx, content=True)
            entries = survey["entries"]
            state["game_before"] = {
                "digest": hashlib.sha256(json.dumps(entries, separators=(",", ":"))
                                         .encode()).hexdigest(),
                "files": survey["files"]}
            with open(self.manifest(ctx), encoding="utf-8") as f:
                state["manifest_before"] = f.read()
            findings = [] if met else [("game-tree-differs", "before the step")]
            steps.add("game-before", "ok",
                      facts={"game_files": facts["game_files"],
                             "game_modules_match": facts["game_modules_match"],
                             "game_entries_hashed": sum(1 for e in entries
                                                        if e[1] == "file" and e[8])},
                      findings=findings, duration=time.monotonic() - started)

        def before_run(self, ctx, findings, state):
            """Right before codegen: the output folders are still empty, the manifest and
            the inventory of project/config/ are the ones checked by prepare."""
            for out in state.get("outputs", []):
                try:
                    if os.path.islink(out) or not os.path.isdir(out) or os.listdir(out):
                        findings.append(("generated-not-empty", "before the step"))
                        break
                except OSError:
                    findings.append(("generated-not-empty", "before the step"))
                    break
            try:
                if file_sha256(self.manifest(ctx)) != state.get("manifest_sha256"):
                    findings.append(("manifest-changed", "between prepare and the step"))
            except OSError:
                findings.append(("manifest-changed", "unreadable before the step"))
            tree = inventory(engine, self.config_root(ctx))
            if tree["unreadable"]:
                findings.append(("tree-unreadable", f"{CONFIG_DIR}/ before the step"))
            if tree["digest"] != state.get("config_digest"):
                findings.append(("config-changed", "between prepare and the step"))
            if not self.project_entries_ok(ctx):
                findings.append(("project-unexpected-entry", "before the step"))

        def run(self, ctx, steps, run_dir, env, state):
            """`rexglue codegen` in the sandbox, from the project folder, with its log in
            the run folder. Never --force: validation errors must stop it."""
            manifest = self.manifest(ctx)
            rexglue = os.path.join(ctx.sdk, "bin", "rexglue")
            command = [rexglue, "--log-level", LOG_LEVEL, "--log-file",
                       os.path.join(run_dir, "codegen.log"), RUN_STEP, manifest]
            started = time.monotonic()
            final, facts, findings = engine.supervise(
                ctx, run_dir, command, env, state, RUN_STEP, "codegen",
                chdir=os.path.dirname(manifest))
            state.update(phase="extracted", codegen_status=final)
            engine.write_state(run_dir, state)
            return steps.add(RUN_STEP, "ok", exit_code=final, facts=facts, findings=findings,
                             output="codegen.stdout, codegen.stderr, codegen.log",
                             duration=time.monotonic() - started)

        # --- after ----------------------------------------------------------------------

        def after_controls(self, ctx, steps, run_dir, state, results):
            seen = {}

            def game_after():
                survey, facts, met = self.game_figures(ctx, content=True)
                digest = hashlib.sha256(json.dumps(survey["entries"], separators=(",", ":"))
                                        .encode()).hexdigest()
                unreadable = [a for a in survey["anomalies"] if a[0] in UNREADABLE]
                unchanged = digest == state["game_before"]["digest"] and met
                results["game_unchanged"] = unchanged
                findings = [("tree-unreadable", "game/ after the step")] if unreadable else []
                if not unchanged:
                    findings.append(("game-changed", "after the step"))
                steps.add("game-after", "ok", facts={"game_unchanged": unchanged,
                                                     "game_modules_match":
                                                     facts["game_modules_match"],
                                                     "game_unreadable": len(unreadable)},
                          findings=findings)
                return True

            def config_after():
                tree = inventory(engine, self.config_root(ctx))
                unchanged = (tree["digest"] == state.get("config_digest") and
                             not tree["unreadable"])
                entries_ok = self.project_entries_ok(ctx)
                results["config_unchanged"] = unchanged and entries_ok
                findings = [("tree-unreadable", f"{CONFIG_DIR}/ after the step")] \
                    if tree["unreadable"] else []
                if tree["digest"] != state.get("config_digest"):
                    findings.append(("config-changed", "after the step"))
                if not entries_ok:
                    findings.append(("project-unexpected-entry", "after the step"))
                steps.add("config-after", "ok", facts={"config_unchanged": unchanged,
                                                       "project_entries_ok": entries_ok},
                          findings=findings)
                return True

            def manifest_after():
                with open(self.manifest(ctx), encoding="utf-8") as f:
                    after = f.read()
                before = state["manifest_before"]
                old, new = before.splitlines(), after.splitlines()
                changed = [i for i in range(max(len(old), len(new)))
                           if (old[i] if i < len(old) else None) !=
                           (new[i] if i < len(new) else None)]
                only_version = len(old) == len(new) and all(
                    new[i].strip().startswith("sdk_version") and
                    old[i].strip().startswith("sdk_version") for i in changed)
                results["manifest_ok"] = only_version
                steps.add("manifest-after", "ok",
                          facts={"manifest_rewritten": bool(changed),
                                 "only_sdk_version_changed": only_version},
                          findings=[] if only_version else [("manifest-changed",
                                                             "after the step")])
                return True

            def generated():
                root = os.path.join(ctx.private, "generated")
                tree = inventory(engine, root, content=False)
                outs = [b["out"][len("generated") + 1:] for b in state.get("binaries", [])]
                files, anomalies = {}, len(tree["others"])
                for path, kind, *_ in tree["entries"]:
                    if path == ".":
                        continue
                    owner = next((o for o in outs if inside(path, o)), None)
                    if kind == "dir":
                        if owner is None and not any(inside(o, path) for o in outs):
                            anomalies += 1
                        elif owner is not None and path != owner:
                            files.setdefault(owner, []).append(path[len(owner) + 1:] + "/")
                    elif owner is None:
                        anomalies += 1
                    else:
                        files.setdefault(owner, []).append(path[len(owner) + 1:])
                seen["files"] = files
                # An inventory that is incomplete, or holds an anomaly, proves no
                # completeness.
                seen["clean"] = not tree["unreadable"] and not anomalies
                count = sum(len(v) for v in files.values())
                results["generated"] = {"files": count}
                findings = [("tree-unreadable", "generated/")] if tree["unreadable"] else []
                if anomalies:
                    findings.append(("generated-anomaly", f"{anomalies} entries"))
                steps.add("generated", "ok",
                          facts={"generated_files": count, "generated_anomalies": anomalies,
                                 "generated_unreadable": len(tree["unreadable"])},
                          findings=findings)
                return True

            def outputs():
                """The completeness of the generation, apart from C2.1: generated/ was
                read whole, with no anomaly; what each codegen.stamp lists must be there,
                of every expected kind, and nothing else; the entry folder holds codegen.d,
                codegen.build.stamp (one fingerprint per module, in order) and, with
                modules, the module registry; the log summary counts what the stamps
                list."""
                status = state.get("codegen_status")
                binaries = state.get("binaries", [])
                files = seen.get("files", {})
                facts = {"modules_expected": len(binaries), "modules_with_valid_stamp": 0,
                         "listed_outputs": 0, "missing_outputs": 0,
                         "modules_with_every_kind": 0, "unlisted_files": 0,
                         "entry_files_ok": False, "log_summary_matches": False}
                fingerprints = []
                for binary in binaries:
                    owner = binary["out"][len("generated") + 1:]
                    present = set(files.get(owner, []))
                    stamp = read_stamp(os.path.join(ctx.private, binary["out"], STAMP))
                    allowed = {STAMP}
                    if binary["entry"]:
                        allowed |= {DEPFILE, BUILD_STAMP}
                        if len(binaries) > 1:
                            allowed |= set(REGISTRY_FILES)
                    if stamp:
                        facts["modules_with_valid_stamp"] += 1
                        fingerprints.append(stamp["fingerprint"])
                        listed = stamp["outputs"]
                        facts["listed_outputs"] += len(listed)
                        facts["missing_outputs"] += sum(1 for n in listed if n not in present)
                        kinds = (all(any(n.endswith(s) for n in listed)
                                     for s in REQUIRED_OUTPUTS) and
                                 all(n in listed for n in REQUIRED_NAMES) and
                                 all(any(p.search(n) for n in listed)
                                     for p in NUMBERED_OUTPUTS))
                        facts["modules_with_every_kind"] += kinds
                        allowed |= set(listed)
                    facts["unlisted_files"] += len(present - allowed)
                entry = next((b for b in binaries if b["entry"]), None)
                if entry and len(fingerprints) == len(binaries):
                    folder = os.path.join(ctx.private, entry["out"])
                    try:
                        with open(os.path.join(folder, BUILD_STAMP), encoding="utf-8") as f:
                            build = f.read()
                        registry = all(os.path.isfile(os.path.join(folder, n)) and
                                       not os.path.islink(os.path.join(folder, n))
                                       for n in (REGISTRY_FILES if len(binaries) > 1 else ()))
                        facts["entry_files_ok"] = (
                            build == "".join(fp + "\n" for fp in fingerprints) and
                            registry and os.path.isfile(os.path.join(folder, DEPFILE)))
                    except (OSError, UnicodeDecodeError):
                        pass
                try:
                    with open(os.path.join(run_dir, "codegen.log"), encoding="utf-8",
                              errors="replace") as f:
                        counts = compare.codegen_summary(f.read())
                except (OSError, compare.Refused):
                    counts = None
                if counts:
                    written, unchanged, deleted, up_to_date = counts
                    extra = len(REGISTRY_FILES) if len(binaries) > 1 else 0
                    facts["log_summary_matches"] = (
                        written + unchanged == facts["listed_outputs"] + extra and
                        unchanged == 0 and deleted == 0 and up_to_date == 0)
                complete = (bool(binaries) and seen.get("clean", False) and
                            facts["modules_with_valid_stamp"] == len(binaries) and
                            facts["missing_outputs"] == 0 and
                            facts["modules_with_every_kind"] == len(binaries) and
                            facts["entry_files_ok"] and facts["log_summary_matches"])
                facts["generation_complete"] = complete
                results["outputs"] = {"expected": len(binaries),
                                      "stamps": facts["modules_with_valid_stamp"],
                                      "complete": complete,
                                      "unlisted": facts["unlisted_files"]}
                findings = []
                if status == 0 and not complete:
                    findings.append(("generation-incomplete", "see the local report"))
                if facts["unlisted_files"]:
                    findings.append(("generated-unlisted", f"{facts['unlisted_files']} "
                                                           "files"))
                steps.add("outputs", "ok", facts=facts, findings=findings)
                return True

            def codegen_inputs():
                """What ReXGlue says it consumed (codegen.d): nothing outside the modules,
                the manifest and project/config/, and every configuration of the
                inventory reached from a binary table (shared ones are not listed by
                ReXGlue, project_recompiler.cpp:57-75)."""
                status = state.get("codegen_status")
                binaries = state.get("binaries", [])
                entry = next((b for b in binaries if b["entry"]), None)
                facts = {"depfile_found": False, "depfile_inputs": 0, "unexpected_inputs": 0,
                         "configs_not_in_depfile": 0}
                findings = []
                parsed = read_depfile(os.path.join(ctx.private, entry["out"], DEPFILE)) \
                    if entry else None
                if parsed:
                    _, listed = parsed
                    listed = {os.path.realpath(p) for p in listed}
                    allowed = {os.path.realpath(self.manifest(ctx))} | {
                        os.path.realpath(os.path.join(ctx.private, b["module"]))
                        for b in binaries}
                    root = os.path.realpath(self.config_root(ctx))
                    unexpected = [p for p in listed if p not in allowed and
                                  not inside(p, root)]
                    missing = [c for c in state.get("binary_configs", [])
                               if os.path.realpath(os.path.join(ctx.private, c))
                               not in listed]
                    facts.update(depfile_found=True, depfile_inputs=len(listed),
                                 unexpected_inputs=len(unexpected),
                                 configs_not_in_depfile=len(missing))
                    if unexpected:
                        findings.append(("codegen-input-unexpected", f"{len(unexpected)}"))
                    if missing:
                        findings.append(("config-inventory-differs", f"{len(missing)}"))
                elif status == 0:
                    findings.append(("generation-incomplete", "codegen.d is missing or "
                                                              "unreadable"))
                steps.add("codegen-inputs", "ok", facts=facts, findings=findings)
                return True

            def c21():
                log = os.path.join(run_dir, "codegen.log")
                status = state.get("codegen_status")
                try:
                    diagnostics, errors, failed = compare.parse_log(log,
                                                                    completed=status == 0)
                except compare.Refused as exc:
                    results["c21"] = None
                    steps.add("c21", "finding", facts={"c21_met": False},
                              findings=[("codegen-log-refused", str(exc))])
                    return True
                unresolved = sum(1 for kind, _, _ in errors if kind == "unresolved_call")
                millicode = sum(1 for kind, _, _ in errors if kind == "millicode")
                kinds = [kind for found in diagnostics.values() for kind in found]
                config_errors = kinds.count("config_error")
                met = (status == 0 and not failed and not unresolved and not millicode
                       and not config_errors)
                results["c21"] = {"status": status, "unresolved": unresolved,
                                  "millicode": millicode, "config_errors": config_errors,
                                  "diagnostics": len(kinds) - config_errors, "met": met}
                steps.add("c21", "ok",
                          facts={"unresolved_calls": unresolved, "millicode_errors": millicode,
                                 "config_errors": config_errors,
                                 "entry_diagnostics": len(kinds) - config_errors,
                                 "validation_failed": failed, "c21_met": met},
                          findings=[] if met else [("c21-not-met", "see the local report")])
                return True

            controls = []
            if state.get("command") == "run" and state.get("game_before"):
                controls += [("game-after", game_after), ("config-after", config_after),
                             ("manifest-after", manifest_after)]
                if state.get("phase_reached_extraction"):
                    controls += [("generated", generated), ("outputs", outputs),
                                 ("codegen-inputs", codegen_inputs), ("c21", c21)]
            return controls

        def result(self, results):
            return results or None

        def summary_lines(self, ctx, figures):
            results = figures
            if not results:
                return []
            source = ("PB-1 tree, J0 reference" if ctx.reference is engine.J0_REFERENCE
                      else "--reference test file")
            lines = [f"B2 figures (game/ against the {source}; C2.1, docs/ROADMAP.md §4):"]

            def mark(ok):
                return "match" if ok else "DIFFERS"

            if "game_unchanged" in results:
                lines.append("  game/ unchanged (content, metadata and identity of every "
                             f"entry; PB-1 figures): {mark(results['game_unchanged'])}")
            if "config_unchanged" in results:
                lines.append("  configuration inputs unchanged (project/config/, project/): "
                             f"{mark(results['config_unchanged'])}")
            if "manifest_ok" in results:
                lines.append("  manifest changed only by its sdk_version line: "
                             f"{mark(results['manifest_ok'])}")
            c21 = results.get("c21")
            if c21 is None and "c21" in results:
                lines.append("  C2.1: the log was refused, not measured")
            elif c21:
                status = c21["status"] if engine._int(c21["status"]) else "none"
                lines.append(f"  codegen exit status: expected 0, found {status}: "
                             f"{mark(c21['status'] == 0)}")
                for label, key in (("unresolved calls", "unresolved"),
                                   ("millicode errors", "millicode"),
                                   ("configuration errors", "config_errors")):
                    lines.append(f"  {label}: expected 0, found {c21[key]}: "
                                 f"{mark(c21[key] == 0)}")
                lines.append(f"  diagnostics on configured entries: {c21['diagnostics']} "
                             "(not errors; levels by address_compare)")
                lines.append(f"  C2.1 met: {'yes' if c21['met'] else 'no'}")
            out = results.get("outputs")
            if out:
                lines.append(f"  output folders with a valid codegen.stamp: expected "
                             f"{out['expected']}, found {out['stamps']}: "
                             f"{mark(out['stamps'] == out['expected'])}")
                lines.append(f"  files listed by no codegen.stamp: expected 0, found "
                             f"{out['unlisted']}: {mark(out['unlisted'] == 0)}")
                lines.append("  generation complete (every listed output, every kind, the "
                             f"entry files, the log summary): "
                             f"{'yes' if out['complete'] else 'no'}")
            if out is not None or "c21" in results:
                done = bool(c21 and c21["met"] and out and out["complete"] and
                            not out["unlisted"])
                lines.append("  B2 result for PB-2 (C2.1 met and generation complete): "
                             f"{'yes' if done else 'no'}")
            return lines

    return B2Profile()


def main(argv):
    if argv[:1] in (["_probe"], ["_crash"]):
        raise SystemExit("error: the probes run in the engine, not here")
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--engine", default=os.path.join(HERE, "b1_extract.py"))
    pre.add_argument("--address-compare", default=os.path.join(HERE, "address_compare.py"))
    pre.add_argument("--private-project", default=os.path.join(HERE, "private_project.py"))
    known, rest = pre.parse_known_args(argv)
    engine = load_module(known.engine, "b1_extract")
    compare = load_module(known.address_compare, "address_compare")
    project = load_module(known.private_project, "private_project")
    profile = make_profile(engine, compare, project)

    def add_arguments(parser):
        parser.add_argument("--meminfo", default="/proc/meminfo",
                            help="memory of the machine, recorded by prepare (T-a)")
    return engine.main(rest, profile=profile, add_arguments=add_arguments)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

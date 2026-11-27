#!/usr/bin/env python3
"""J2 step B2: the compatibility check (docs/J2_B2_COMPATIBILITY.md).

A first `rexglue codegen` of the two modules extracted at B1, with the configuration of
project A as a test input only, run as a controlled step of the engine of
tools/b1_extract.py (docs/J2_LOCAL_STEP_ENGINE.md). This file is the B2 profile of that
engine: it reuses its checks, sandbox, proof of option B (D-018), store closure (D-019),
preflight and postflight, state, resume, summary and diagnosis, and adds only what is
proper to B2:

- game/ is an input, read-only in the sandbox, and must still be the tree that PB-1
  validated (the figures of tools/b1_extract.py, against the J0 reference);
- the private manifest is checked by tools/private_project.py;
- the sandboxed command is `rexglue --log-level info --log-file <run folder>/codegen.log
  codegen <manifest>`, never with --force;
- C2.1 (0 unresolved call, 0 validation error) is read from that log by the parser of
  tools/address_compare.py (A8-bis).

A proposal: a real run of B2 needs its own mandate (D-020). Nothing here reads a game file
before the step, decodes, or writes outside the private folder.
"""

import argparse
import hashlib
import importlib.util
import os
import stat
import sys
import time
import tomllib

VERSION = 1
HERE = os.path.dirname(os.path.realpath(__file__))
MANIFEST = os.path.join("project", "wc2010_manifest.toml")
RUN_STEP = "codegen"


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


def tree_listing(root):
    """Every entry below root, links never followed: (relative path, kind, size, mtime_ns),
    sorted, and its SHA-256. Detects any file written, removed or replaced."""
    entries = []
    for top, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = os.path.join(top, name)
            st = os.lstat(path)
            kind = "dir" if stat.S_ISDIR(st.st_mode) else "file" if stat.S_ISREG(
                st.st_mode) else "other"
            entries.append((os.path.relpath(path, root), kind,
                            st.st_size if kind == "file" else 0, st.st_mtime_ns))
    entries.sort()
    digest = hashlib.sha256(repr(entries).encode()).hexdigest()
    return entries, digest


def make_profile(engine, compare, project):
    """The B2 profile, built on the loaded engine and tools."""

    # Names, codes and facts of B2, in the allowlists of the engine's summary.
    engine.STEP_NAMES = engine.STEP_NAMES + (
        "game-tree", "project", "test-config", "game-before", "before-codegen", RUN_STEP,
        "game-after", "manifest-after", "generated", "c21")
    engine.FINDING_CODES.update({
        "game-tree-differs": "game/ is not the tree validated at PB-1 (counts or module "
                             "hashes)",
        "game-changed": "game/ changed during the step",
        "manifest-invalid": "the private manifest fails the checks of private_project",
        "manifest-changed": "the manifest changed otherwise than by its sdk_version line",
        "generated-not-empty": "an output folder of the manifest is missing or not empty",
        "generated-anomaly": "a link, a special file or a file outside the output folders "
                             "in generated/",
        "test-config-absent": "the private copy holds no included configuration: the test "
                              "input of project A is missing",
        "test-config-invalid": "an included configuration is unreadable or not TOML",
        "app-config-present": "app/rexglue.toml exists: ReXGlue would read it",
        "xexp-present": "a .xexp file lies next to a module: ReXGlue would apply it",
        "codegen-not-started": "bubblewrap did not start the code generation",
        "codegen-timeout": "the code generation was stopped after the time-out",
        "codegen-crashed": "the code generation was killed by a signal",
        "codegen-failed": "the code generation exited with an error",
        "codegen-log-refused": "the codegen log is in an unknown or partial format "
                               "(address_compare refused it)",
        "c21-not-met": "C2.1 is not met: an unresolved call, a millicode error or a "
                       "configuration error",
    })
    engine.EXTRACTION_GATES.add("test-config-absent")
    engine.PROBE_CHECK_NAMES.update(("write-denied-game", "writable-generated",
                                     "writable-project", "shm-private"))
    engine.SUMMARY_FACTS.update({
        "game-tree": {"game_files": engine._int, "game_directories": engine._int,
                      "game_anomalies": engine._int, "game_modules_match": engine._bool},
        "project": {"manifest_findings": engine._int, "output_folders": engine._int,
                    "output_folders_empty": engine._bool},
        "test-config": {"config_files": engine._int, "function_entries": engine._int,
                        "crt_entries": engine._int},
        "game-before": {"game_files": engine._int, "game_modules_match": engine._bool},
        RUN_STEP: {"signal": engine.SIGNAL_NUMBER},
        "game-after": {"game_unchanged": engine._bool, "game_modules_match": engine._bool},
        "manifest-after": {"manifest_rewritten": engine._bool,
                           "only_sdk_version_changed": engine._bool},
        "generated": {"generated_files": engine._int, "modules_with_stamp": engine._int,
                      "generated_anomalies": engine._int},
        "c21": {"unresolved_calls": engine._int, "millicode_errors": engine._int,
                "config_errors": engine._int, "entry_diagnostics": engine._int,
                "validation_failed": engine._bool, "c21_met": engine._bool},
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
        writable = ("generated", "project", "app", "tmp")
        read_only = ("game",)
        components = engine.PRIVATE_COMPONENTS + ("generated", "project")
        required = ("game", "logs", "generated", "project")
        decision = ("this tool does not declare PB-2; the orchestrator, then the owner, "
                    "decide. A success does not prove the identity of the code.")
        file = os.path.realpath(__file__)

        def probe_checks(self):
            """The checks of B1, with game/ write-denied, generated/ and project/ writable,
            and a private /dev/shm for the guest memory."""
            return super().probe_checks() + ("shm-private",)

        def manifest(self, ctx):
            return os.path.join(ctx.private, MANIFEST)

        # --- prepare --------------------------------------------------------------------

        def game_figures(self, ctx):
            """The tree of game/ against the reference of PB-1: counts, no anomaly, module
            hashes."""
            reference = ctx.reference
            survey = engine.survey_tree(ctx.game, list(reference["modules"]))
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
            if os.path.lexists(os.path.join(ctx.private, "app", "rexglue.toml")):
                findings.append(("app-config-present", "app/rexglue.toml"))
            steps.add("project", "ok", facts=facts, findings=findings)
            self._outputs = outputs
            self._includes = [path for label, path in resolved.items() if ".includes #" in label]

        def prepare_last(self, ctx, steps):
            """The test input of project A: the configurations included by the private
            copy. Only counts reach the summary; the addresses stay local."""
            findings, facts = [], {"config_files": 0, "function_entries": 0,
                                   "crt_entries": 0}
            for path in getattr(self, "_includes", []):
                try:
                    with open(path, "rb") as f:
                        table = tomllib.load(f)
                except (OSError, tomllib.TOMLDecodeError) as exc:
                    findings.append(("test-config-invalid", f"{path}: {type(exc).__name__}"))
                    continue
                facts["config_files"] += 1
                functions = table.get("functions", {})
                facts["function_entries"] += len(functions) if isinstance(functions,
                                                                          dict) else 0
                facts["crt_entries"] += sum(1 for key in ("setjmp_address", "longjmp_address")
                                            if key in table)
            if not facts["config_files"]:
                findings.append(("test-config-absent", "no included configuration"))
            steps.add("test-config", "ok", facts=facts, findings=findings)
            manifest = self.manifest(ctx)
            try:
                manifest_sha = file_sha256(manifest)
            except OSError:
                manifest_sha = None
            return {"manifest_sha256": manifest_sha,
                    "outputs": getattr(self, "_outputs", [])}

        # --- around the marker ----------------------------------------------------------

        def before_marker(self, ctx, steps, state, extract):
            """game/ before the step: the PB-1 figures again, and its listing."""
            if not extract:
                return
            started = time.monotonic()
            survey, facts, met = self.game_figures(ctx)
            listing, digest = tree_listing(ctx.game)
            state["game_before"] = {"listing_sha256": digest, "files": survey["files"],
                                    "modules": {k: v.get("sha256") for k, v in
                                                survey["modules"].items()}}
            with open(self.manifest(ctx), encoding="utf-8") as f:
                state["manifest_before"] = f.read()
            findings = [] if met else [("game-tree-differs", "before the step")]
            steps.add("game-before", "ok", facts={"game_files": facts["game_files"],
                                                  "game_modules_match":
                                                  facts["game_modules_match"]},
                      findings=findings, duration=time.monotonic() - started)

        def before_run(self, ctx, findings, state):
            """Right before codegen: the output folders are still empty, the manifest is
            the one checked."""
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

        def run(self, ctx, steps, run_dir, env, state):
            """`rexglue codegen` in the sandbox, from the project folder, with its log in
            the run folder. Never --force: validation errors must stop it."""
            manifest = self.manifest(ctx)
            rexglue = os.path.join(ctx.sdk, "bin", "rexglue")
            command = [rexglue, "--log-level", "info", "--log-file",
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
            def game_after():
                survey, facts, met = self.game_figures(ctx)
                _, digest = tree_listing(ctx.game)
                before = state["game_before"]
                unchanged = digest == before["listing_sha256"] and met
                results["game_unchanged"] = unchanged
                findings = [] if unchanged else [("game-changed", "after the step")]
                steps.add("game-after", "ok", facts={"game_unchanged": unchanged,
                                                     "game_modules_match":
                                                     facts["game_modules_match"]},
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
                outputs = [os.path.realpath(p) for p in state.get("outputs", [])]
                files = anomalies = 0
                stamps = 0
                for top, dirs, names in os.walk(root, followlinks=False):
                    for name in dirs + names:
                        path = os.path.join(top, name)
                        st = os.lstat(path)
                        inside = any(engine.under_or_self(os.path.realpath(path), out)
                                     for out in outputs)
                        if stat.S_ISDIR(st.st_mode):
                            if not inside and not any(engine.under_or_self(out, path)
                                                      for out in outputs):
                                anomalies += 1
                            continue
                        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not inside:
                            anomalies += 1
                            continue
                        files += 1
                        if name == "codegen.stamp":
                            stamps += 1
                results["generated"] = {"files": files, "stamps": stamps}
                steps.add("generated", "ok",
                          facts={"generated_files": files, "modules_with_stamp": stamps,
                                 "generated_anomalies": anomalies},
                          findings=[("generated-anomaly", f"{anomalies} entries")]
                          if anomalies else [])
                return True

            def c21():
                log = os.path.join(run_dir, "codegen.log")
                status = state.get("codegen_status")
                try:
                    diagnostics, errors, failed = compare.parse_log(log)
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
                controls += [("game-after", game_after), ("manifest-after", manifest_after)]
                if state.get("phase_reached_extraction"):
                    controls += [("generated", generated), ("c21", c21)]
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
            c21 = results.get("c21")
            if "game_unchanged" in results:
                mark = "match" if results["game_unchanged"] else "DIFFERS"
                lines.append(f"  game/ unchanged, PB-1 figures and module hashes: {mark}")
            if "manifest_ok" in results:
                mark = "match" if results["manifest_ok"] else "DIFFERS"
                lines.append(f"  manifest changed only by its sdk_version line: {mark}")
            if c21 is None and "c21" in results:
                lines.append("  C2.1: the log was refused, not measured")
            elif c21:
                status = c21["status"] if engine._int(c21["status"]) else "none"
                lines.append(f"  codegen exit status: expected 0, found {status}: "
                             f"{'match' if c21['status'] == 0 else 'DIFFERS'}")
                for label, key in (("unresolved calls", "unresolved"),
                                   ("millicode errors", "millicode"),
                                   ("configuration errors", "config_errors")):
                    lines.append(f"  {label}: expected 0, found {c21[key]}: "
                                 f"{'match' if c21[key] == 0 else 'DIFFERS'}")
                lines.append(f"  diagnostics on configured entries: {c21['diagnostics']} "
                             "(not errors; levels by address_compare)")
                lines.append(f"  C2.1 met: {'yes' if c21['met'] else 'no'}")
            if "generated" in results:
                lines.append(f"  output folders with a codegen.stamp: "
                             f"{results['generated']['stamps']}")
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
    return engine.main(rest, profile=profile)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

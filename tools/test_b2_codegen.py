#!/usr/bin/env python3
"""Tests of tools/b2_codegen.py (J2 step B2, docs/J2_B2_COMPATIBILITY.md), on synthetic
folders only.

No disc image, no module and no game file is used. game/ holds a few lines of text named
like the two modules, the configuration of "project A" is made of obviously synthetic
addresses, and `rexglue codegen` is a small Python script that writes outputs and a log in
the formats of ReXGlue v0.11.0 (the formats address_compare.py reads). The fixture of the
B1 tests is reused as it is: the same synthetic machine, fake bubblewrap, journal, store
closure and private_guard (tools/test_b1_extract.py). RealSandboxTest runs the real
bubblewrap where the machine allows it. The Nix check b2-codegen-selftest also runs the
real `rexglue codegen` on a synthetic project, in the real sandbox.

Run: python3 -I tools/test_b2_codegen.py, as an unprivileged user, with TMPDIR outside
/tmp for RealSandboxTest.
"""

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
B2_TOOL = os.path.join(HERE, "b2_codegen.py")
TEMPLATE = os.path.join(ROOT, "config", "private-template", "wc2010_manifest.toml")
B2_PROOF_DIR = "b2-rehearse-20000101T000000Z"


def load(path, name):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


t1 = load(os.path.join(HERE, "test_b1_extract.py"), "test_b1_extract")
b1 = t1.b1
b2 = load(B2_TOOL, "b2_codegen")
B2 = b2.make_profile(b1, load(os.path.join(HERE, "address_compare.py"), "address_compare"),
                     load(os.path.join(HERE, "private_project.py"), "private_project"))
SENTINEL = t1.SENTINEL

# The fake `rexglue codegen`. It records its arguments, working folder, core size limit and
# environment in the run folder, then follows the plan, in the formats of ReXGlue v0.11.0
# (docs/J2_B2_COMPATIBILITY.md §6): in each output folder the ten outputs of a module and a
# codegen.stamp that lists them; in the folder of the entry module codegen.d (the inputs:
# modules, manifest, configurations included, transitively), codegen.build.stamp and the
# module registry; the `Codegen summary` line in the log; the rewrite of
# [project].sdk_version after a success. It can also misbehave: write in game/,
# project/config/, project/ or outside, change a file at constant size and mtime, change the
# manifest, leave out or spoil an output, list another input, write a partial, truncated or
# empty log, crash or hang.
FAKE_CODEGEN = r'''
import errno, hashlib, json, os, resource, signal, sys, time, tomllib
plan = json.loads(os.environ["B1_FAKE_PLAN_JSON"]) if "B1_FAKE_PLAN_JSON" in os.environ \
    else json.load(open(os.environ["B1_FAKE_PLAN"]))
args = sys.argv[1:]
run_dir = os.environ["REX_APP_LOG_ROOT"]
record = {"argv": args, "cwd": os.getcwd(),
          "core": list(resource.getrlimit(resource.RLIMIT_CORE)), "attempts": {}}
def save():
    with open(os.path.join(run_dir, "fake-record.json"), "w") as f:
        json.dump(record, f)
save()
if args[:4] != ["--log-level", "info", "--log-file", args[3]] or args[4] != "codegen":
    sys.exit(106)
log_path, manifest = args[3], args[5]
base = os.path.dirname(manifest)
with open(manifest, "rb") as f:
    table = tomllib.load(f)
binaries = [table["entrypoint"]] + table.get("modules", [])
INFO = "[2026-11-27 12:00:00.000] [rexglue] [info] "
log = open(log_path, "a")
log.write(INFO + "Recompiling wc2010\n")
for line in plan.get("log_lines", []):
    log.write(line + "\n")
errors = plan.get("unresolved", 0) + plan.get("millicode", 0)
for i in range(plan.get("unresolved", 0)):
    log.write(f"  bl 0x8200{i:04X} from 0x8210{i:04X} has a target in no function\n")
for i in range(plan.get("millicode", 0)):
    log.write(f"  bl 0x8300{i:04X} from 0x8310{i:04X} is inside a millicode run, off its "
              "entries\n")
if errors and not plan.get("partial_log"):
    log.write(f"[error] Validation failed: {plan.get('unresolved', 0)} unresolved calls, "
              f"{plan.get('millicode', 0)} millicode errors\n")
log.close()
def attempt(name, action):
    try:
        action()
        record["attempts"][name] = "written"
    except OSError as exc:
        record["attempts"][name] = errno.errorcode.get(exc.errno, str(exc.errno))
for path in plan.get("write_outside", []):
    def action(path=path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("written outside\n")
    attempt(path, action)
if plan.get("modify_module"):
    def action():
        with open(os.path.join(base, "..", "game", "default.xex"), "a") as f:
            f.write("changed\n")
    attempt("module", action)
if plan.get("modify_config"):
    def action():
        with open(os.path.join(base, "config", "default.toml"), "a") as f:
            f.write("# changed\n")
    attempt("config", action)
for rel in plan.get("same_stat", []):
    # One byte changed, the size and the modification time kept.
    def action(path=os.path.normpath(os.path.join(base, rel))):
        st = os.stat(path)
        with open(path, "r+b") as f:
            data = f.read()
            f.seek(0)
            f.write(bytes([data[0] ^ 1]) + data[1:])
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    attempt(rel, action)
save()
if plan.get("sleep"):
    time.sleep(plan["sleep"])
if plan.get("signal"):
    os.kill(os.getpid(), getattr(signal, "SIG" + plan["signal"]))
if errors:
    sys.exit(1)
def consumed(tbl, folder, chain):
    found = []
    for include in tbl.get("includes", []):
        path = os.path.realpath(os.path.join(folder, include))
        if path in chain:
            continue
        with open(path, "rb") as f:
            sub = tomllib.load(f)
        found += [path] + consumed(sub, os.path.dirname(path), chain + [path])
    return found
def escape(path):
    return path.replace("$", "$$").replace(" ", "\\ ").replace("#", "\\#")
SUFFIXES = ("_pch.h", "_funcs.h", "_init.h", "_init.cpp", "_register.cpp", "_funcs.0.h",
            "_recomp.0.cpp")
fingerprints, inputs, listed = [], [], 0
for index, binary in enumerate(binaries):
    if plan.get("no_outputs"):
        break
    out = os.path.normpath(os.path.join(base, binary["out_directory_path"]))
    # Every binary takes the project name as prefix (src/codegen/manifest.cpp:59).
    names = [table["project"]["name"] + s for s in SUFFIXES] + [
        "sources.cmake", "codegen.partition.json", "codegen.mmio.json"]
    for name in names:
        with open(os.path.join(out, name), "w") as f:
            if name.endswith("_init.cpp"):
                f.write("const PPCFuncMapping kPPCFuncMappings[] = {\n"
                        "\t{ 0x82000000, sub_82000000 },\n\t{ 0, nullptr }\n};\n")
            else:
                f.write("// synthetic output\n")
    module_inputs = [base + "/" + binary["file_path"], manifest] + consumed(binary, base, [])
    fingerprint = hashlib.sha256(json.dumps([names, module_inputs]).encode()).hexdigest()
    with open(os.path.join(out, "codegen.stamp"), "w") as f:
        if plan.get("bad_stamp") == index:
            f.write("not a stamp\n")
        elif plan.get("no_stamp") != index:
            json.dump({"version": 1, "fingerprint": fingerprint, "outputs": sorted(names)},
                      f, indent=2)
    if plan.get("no_stamp") == index:
        os.unlink(os.path.join(out, "codegen.stamp"))
    if plan.get("missing_output") == index:
        os.unlink(os.path.join(out, names[6]))
    fingerprints.append(fingerprint)
    inputs += module_inputs
    listed += len(names)
entry = os.path.normpath(os.path.join(base, binaries[0]["out_directory_path"]))
if not plan.get("no_outputs"):
    listing = sorted(set(inputs)) + plan.get("depfile_extra", [])
    if plan.get("depfile_skip_configs"):
        listing = [p for p in listing if not p.endswith(".toml") or p == manifest]
    build_stamp = os.path.join(entry, "codegen.build.stamp")
    with open(os.path.join(entry, "codegen.d"), "w") as f:
        f.write(escape(build_stamp) + ":" + "".join(" \\\n  " + escape(p) for p in listing)
                + "\n")
    with open(build_stamp, "w") as f:
        f.write("".join(fp + "\n" for fp in fingerprints[::-1 if plan.get("swap_build")
                                                         else 1]))
    for name in ("module_registry.cpp", "dll_targets.cmake"):
        if plan.get("no_registry") != name:
            with open(os.path.join(entry, name), "w") as f:
                f.write("// synthetic registry\n")
    if plan.get("unlisted"):
        with open(os.path.join(entry, "stray.txt"), "w") as f:
            f.write("not listed\n")
    if plan.get("leave_link"):
        os.symlink("/etc/passwd", os.path.join(entry, "link"))
    if plan.get("unreadable_dir"):
        os.mkdir(os.path.join(entry, "hidden"))
        os.chmod(os.path.join(entry, "hidden"), 0)
written = listed + 2 + plan.get("summary_offset", 0)
with open(log_path, "a") as log:
    if not plan.get("truncated_log"):
        log.write(INFO + f"Codegen summary: {written} written, 0 unchanged, 0 deleted, "
                  "0 module(s) up to date\n")
if plan.get("empty_log"):
    open(log_path, "w").close()
if plan.get("cut_log"):
    with open(log_path, "rb+") as f:
        f.truncate(os.path.getsize(log_path) - 1)
with open(manifest) as f:
    text = f.read()
text = text.replace('sdk_version = "0.11.0"', 'sdk_version = "0.11.0"  # rewritten', 1)
if plan.get("change_manifest"):
    text = text.replace('name = "wc2010"', 'name = "other"', 1)
tmp = manifest + ".tmp"
with open(tmp, "w") as f:
    f.write(text)
os.rename(tmp, manifest)
if plan.get("extra_project_file"):
    def action():
        with open(os.path.join(base, "stray.toml"), "w") as f:
            f.write("\n")
    attempt("project", action)
    save()
sys.exit(int(plan.get("exit", 0)))
'''

GAME_TREE = {
    "default.xex": "synthetic entry module, not a XEX\n",
    "fifadllzf.xex": "synthetic second module, not a XEX\n",
    "media": {"a.txt": "a\n", "sub": {"b.txt": "b\n"}},
}
# Synthetic configuration of "project A": made-up addresses, not those of any game.
TEST_CONFIG = {
    "default.toml": '[functions]\n0x82000010 = {}\n0x82000020 = {}\n',
    "fifadllzf.toml": ('setjmp_address = 0x82100000\nlongjmp_address = 0x82100040\n'
                       '[functions]\n0x82100080 = {}\n'),
}
# Derogation G-3 (D-021): the kept original of default.toml, with its function_table_base
# line (a made-up value); config/default.toml is that file less the line.
G3_ORIGINAL = "function_table_base = 0x8C100000\n" + TEST_CONFIG["default.toml"]


def read_text(path):
    with open(path) as f:
        return f.read()


def write_tree(folder, tree):
    for name, value in tree.items():
        path = os.path.join(folder, name)
        if isinstance(value, dict):
            os.mkdir(path)
            write_tree(path, value)
        else:
            with open(path, "w") as f:
                f.write(value)


class B2Fixture(t1.Fixture):
    """The B1 fixture, after B1: game/ holds the PB-1 tree of the test reference, project/
    holds the copy of the A5 template with the synthetic test configuration included, and
    generated/ holds the two empty output folders."""

    def setUp(self):
        super().setUp()
        write_script = t1.write_script
        write_script(os.path.join(self.sdk, "bin", "rexglue"), FAKE_CODEGEN)
        write_tree(self.game, GAME_TREE)
        self.tree = GAME_TREE
        self.write_reference(t1.reference_for(GAME_TREE))
        self.project = os.path.join(self.private, "project")
        os.mkdir(self.project, 0o700)
        os.mkdir(os.path.join(self.project, "config"), 0o700)
        for name, text in TEST_CONFIG.items():
            with open(os.path.join(self.project, "config", name), "w") as f:
                f.write(text)
        os.mkdir(os.path.join(self.project, "config", "original"), 0o700)
        with open(os.path.join(self.project, "config", "original", "default.toml"), "w") as f:
            f.write(G3_ORIGINAL)
        self.manifest = os.path.join(self.project, "wc2010_manifest.toml")
        self.write_manifest()
        for name in ("default", "fifadllzf"):
            os.mkdir(os.path.join(self.private, "generated", name), 0o700)
        self.plan["probe_results"] = [{"name": n, "ok": True, "detail": ""}
                                      for n in B2.probe_checks()]
        self.write_proof()

    def write_manifest(self, includes=True, extra=""):
        with open(TEMPLATE) as f:
            text = f.read()
        if includes:
            text = text.replace('out_directory_path = "../generated/default"\nincludes = []',
                                'out_directory_path = "../generated/default"\n'
                                'includes = ["config/default.toml"]', 1)
            text = text.replace('out_directory_path = "../generated/fifadllzf"\n'
                                'includes = []',
                                'out_directory_path = "../generated/fifadllzf"\n'
                                'includes = ["config/fifadllzf.toml"]', 1)
        with open(self.manifest, "w") as f:
            f.write(text + extra)

    def argv(self, command, *extra):
        argv = super().argv(command, *extra)
        return [argv[0], "-I", B2_TOOL] + argv[3:]

    def run_dirs(self):
        return sorted(os.path.join(self.logs, name) for name in os.listdir(self.logs)
                      if name.startswith("b2-") and name != B2_PROOF_DIR)

    def remove_proof(self):
        shutil.rmtree(os.path.join(self.logs, B2_PROOF_DIR), ignore_errors=True)

    def write_proof(self, state_changes=None, proved_at=None, profile=None, **changes):
        """A completed B2 rehearsal holding the proof of option B, bound to the B2 profile
        (or to `profile`)."""
        if not hasattr(self, "project"):
            return  # the B1 fixture calls this before game/ and project/ exist
        profile = profile or B2
        folder = os.path.join(self.logs, f"{profile.name}-rehearse-20000101T000000Z")
        os.makedirs(folder, exist_ok=True)
        ctx = types.SimpleNamespace(profile=profile, args=types.SimpleNamespace(
            core_pattern_file=self.core_pattern, suid_dumpable_file=self.suid,
            bwrap=self.bwrap, store_closure=self.closure))
        identity = b1.proof_identity(ctx)
        identity.update(changes)
        state = {"tool_version": b1.TOOL_VERSION, "command": "rehearse",
                 "phase": "complete", "controls_clean": True, "evidence_incomplete": [],
                 "core_proof": dict(identity, result="validated",
                                    proved_at=time.time() if proved_at is None
                                    else proved_at)}
        state.update(state_changes or {})
        b1.write_state(folder, state)

    def fake_rexglue_pids(self):
        pids = []
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                try:
                    with open(f"/proc/{entry}/cmdline", "rb") as f:
                        if self.sdk.encode() in f.read():
                            pids.append(int(entry))
                except OSError:
                    pass
        return pids

    def outputs(self):
        found = []
        for top, dirs, files in os.walk(os.path.join(self.private, "generated")):
            found += [os.path.relpath(os.path.join(top, n), self.private) for n in files]
        return sorted(found)


class PrepareTest(B2Fixture):
    def test_prepare_passes_and_writes_nothing(self):
        before = t1.snapshot(self.w, skip=(self.records,))
        self.assertEqual(self.tool("prepare"), 0, self.output)
        self.assertEqual(t1.snapshot(self.w, skip=(self.records,)), before)
        self.assertIn("fifa2010wc B2 summary", self.output)
        for line in ("game-tree            ok                game_files 4, game_directories 2, "
                     "game_anomalies 0, game_modules_match True",
                     "project              ok                manifest_findings 0, "
                     "output_folders 2, output_folders_empty True, project_entries_ok True",
                     "test-config          ok                config_files 2, "
                     "binary_config_files 2, shared_config_files 0, config_tree_files 3, "
                     "config_unused_files 1, include_depth 1, hook_files 0, template_dirs 0, "
                     "function_entries 3, crt_entries 2, table_base_settings 0, "
                     "timeout_seconds 7200, g3_original_present True, g3_derogation_ok True",
                     "resources            ok                memory_total_mib ",
                     "store-closure        ok"):
            self.assertIn(line, self.output)
        self.assert_shareable(self.output)
        self.assertNotIn("0x82", self.output)

    def test_game_must_be_the_pb1_tree(self):
        """game/ is an input: it must still be the tree PB-1 validated."""
        cases = (("extra file", lambda: self.write_text(os.path.join(self.game, "x"), "x")),
                 ("module changed", lambda: self.write_text(
                     os.path.join(self.game, "default.xex"), "other\n")),
                 ("a .xexp", lambda: self.write_text(
                     os.path.join(self.game, "default.xexp"), "patch\n")))
        for name, change in cases:
            with self.subTest(name=name):
                with open(os.path.join(self.game, "default.xex")) as f:
                    original = f.read()
                change()
                self.assertEqual(self.tool("run"), 1)
                self.assertTrue("finding game-tree-differs" in self.output or
                                "finding xexp-present" in self.output, self.output)
                self.assertIsNone(self.recorded())
                for path in ("x", "default.xexp"):
                    if os.path.exists(os.path.join(self.game, path)):
                        os.unlink(os.path.join(self.game, path))
                self.write_text(os.path.join(self.game, "default.xex"), original)
        self.assertEqual(self.tool("prepare"), 0, self.output)

    def test_unreadable_entries_are_findings(self):
        """An entry the survey cannot read is a finding, not an entry left out: in game/ it
        breaks the PB-1 figures, in project/config/ it makes the inventory incomplete."""
        for folder, code in ((os.path.join(self.game, "media", "sub"), "game-tree-differs"),
                             (os.path.join(self.project, "config", "extra"),
                              "tree-unreadable")):
            with self.subTest(folder=folder):
                os.makedirs(folder, exist_ok=True)
                os.chmod(folder, 0)
                self.addCleanup(lambda folder=folder: os.path.isdir(folder) and
                                os.chmod(folder, 0o700))
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"finding {code}", self.output)
                self.assertIsNone(self.recorded())
                os.chmod(folder, 0o700)
                if folder.endswith("extra"):
                    os.rmdir(folder)
        self.assertEqual(self.tool("prepare"), 0, self.output)

    def test_manifest_outputs_and_test_config(self):
        cases = (("invalid manifest", lambda: self.write_manifest(
                     extra='\n[[modules]]\nguest_path = "x"\nfile_path = "/etc/passwd"\n'
                           'out_directory_path = "../generated/x"\n'), "manifest-invalid"),
                 ("output not empty", lambda: self.write_text(
                     os.path.join(self.private, "generated", "default", "old.cpp"), "x"),
                  "generated-not-empty"),
                 ("app configuration", lambda: self.write_text(
                     os.path.join(self.private, "app", "rexglue.toml"), ""),
                  "app-config-present"),
                 ("no test configuration", lambda: self.write_manifest(includes=False),
                  "test-config-absent"),
                 ("another file in project/", lambda: self.write_text(
                     os.path.join(self.project, "notes.toml"), ""),
                  "project-unexpected-entry"))
        os.makedirs(os.path.join(self.private, "app"), exist_ok=True)
        for name, change, code in cases:
            with self.subTest(name=name):
                change()
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"finding {code}", self.output)
                self.assertIsNone(self.recorded())
                self.write_manifest()
                for path in ("generated/default/old.cpp", "app/rexglue.toml",
                             "project/notes.toml"):
                    if os.path.exists(os.path.join(self.private, path)):
                        os.unlink(os.path.join(self.private, path))
        self.assertEqual(self.tool("prepare"), 0, self.output)

    def test_without_test_configuration_rehearse_still_runs(self):
        """The test input of project A is needed to generate, not to rehearse."""
        self.write_manifest(includes=False)
        self.remove_proof()
        self.assertEqual(self.tool("rehearse"), 1)
        report = self.report()
        self.assertEqual(sorted(set(self.codes(report))),
                         ["core-proof-missing", "test-config-absent"])
        self.assertTrue(self.step(report, "core-probe")["facts"]["proof_acquired"])


class ConfigInputsTest(B2Fixture):
    """Review 7220519596, point 1: the configuration inputs codegen consumes are
    inventoried, transitively, must lie in project/config/, and must not change."""

    def config(self, name, text):
        path = os.path.join(self.project, "config", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_transitive_includes_are_inventoried_and_listed_by_codegen(self):
        self.config("fifadllzf.toml", 'includes = ["common/base.toml"]\n' +
                    TEST_CONFIG["fifadllzf.toml"])
        self.config("common/base.toml", 'includes = ["more.toml"]\n'
                    '[functions]\n0x82000030 = {}\n')
        self.config("common/more.toml", "[functions]\n0x82000040 = {}\n")
        self.config("unused.txt", "notes\n")
        self.assertEqual(self.tool("run"), 0, self.output)
        report = self.report()
        facts = self.step(report, "test-config")["facts"]
        self.assertEqual((facts["config_files"], facts["binary_config_files"],
                          facts["include_depth"], facts["config_tree_files"],
                          facts["config_unused_files"], facts["function_entries"]),
                         (4, 4, 3, 6, 2, 5))
        inputs = self.step(report, "codegen-inputs")["facts"]
        self.assertEqual((inputs["depfile_found"], inputs["unexpected_inputs"],
                          inputs["configs_not_in_depfile"]), (True, 0, 0))
        self.assertNotIn("0x82", self.summary())

    def test_inputs_must_stay_in_config_and_be_valid(self):
        outside = os.path.join(self.private, "app", "x.toml")
        os.makedirs(os.path.dirname(outside), exist_ok=True)
        self.write_text(outside, "[functions]\n")
        target = self.config("real.toml", "[functions]\n")
        cases = (
            ("include outside", '"../app/x.toml"', None, "config-outside"),
            ("include through a link", '"config/link.toml"',
             lambda: os.symlink(target, os.path.join(self.project, "config", "link.toml")),
             "config-outside"),
            ("link to outside", '"config/out.toml"',
             lambda: os.symlink(outside, os.path.join(self.project, "config", "out.toml")),
             "config-outside"),
            ("missing", '"config/none.toml"', None, "test-config-invalid"),
            ("not a path", "1", None, "test-config-invalid"),
            ("circular", '"config/loop.toml"',
             lambda: self.config("loop.toml", 'includes = ["loop.toml"]\n'),
             "test-config-invalid"),
            ("sets a key of the manifest", '"config/path.toml"',
             lambda: self.config("path.toml", 'file_path = "../../game/default.xex"\n'),
             "test-config-invalid"),
            ("too deep", '"config/d0.toml"', lambda: [
                self.config(f"d{i}.toml", f'includes = ["d{i + 1}.toml"]\n')
                for i in range(33)] + [self.config("d33.toml", "\n")],
             "test-config-invalid"))
        for name, include, setup, code in cases:
            with self.subTest(name=name):
                if setup:
                    setup()
                self.write_manifest()
                with open(self.manifest) as f:
                    text = f.read()
                self.write_text(self.manifest, text.replace(
                    'includes = ["config/default.toml"]',
                    f'includes = ["config/default.toml", {include}]', 1))
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"finding {code}", self.output)
                self.assertIsNone(self.recorded())
                for entry in os.listdir(os.path.join(self.project, "config")):
                    path = os.path.join(self.project, "config", entry)
                    if entry not in TEST_CONFIG and entry not in ("real.toml", "original"):
                        os.unlink(path)
        for key, value in (("hook_sources", '["../app"]'), ("template_dir", '"../app"')):
            with self.subTest(key=key):
                self.write_manifest()
                with open(self.manifest) as f:
                    text = f.read()
                if key == "hook_sources":
                    text = text.replace('game_root = "../game"',
                                        f'game_root = "../game"\nhook_sources = {value}', 1)
                else:
                    text = f"template_dir = {value}\n" + text
                self.write_text(self.manifest, text)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding config-outside", self.output)
                self.assertIsNone(self.recorded())
        os.unlink(target)
        self.write_manifest()
        self.assertEqual(self.tool("prepare"), 0, self.output)

    def test_an_include_changed_between_prepare_and_the_step_stops_it(self):
        """Substitution after prepare: the inventory is taken again right before codegen."""
        path = os.path.join(self.project, "config", "default.toml")
        self.plan["probe_writes"] = [[path, TEST_CONFIG["default.toml"].replace("10", "14")]]
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        before = self.step(report, "before-extraction")
        self.assertIn("config-changed", [f["code"] for f in before["findings"]])
        self.assertIsNone(self.recorded())
        self.assertEqual(self.step(report, "codegen")["status"], "skipped")

    def test_changes_during_the_step_are_findings(self):
        """In the fake sandbox nothing is read-only: an include changed, one changed at
        constant size and modification time, and another file in project/ are seen."""
        for plan, code in (({"modify_config": True}, "config-changed"),
                           ({"same_stat": ["config/fifadllzf.toml"]}, "config-changed"),
                           ({"extra_project_file": True}, "project-unexpected-entry")):
            with self.subTest(plan=plan):
                saved = dict(self.plan)
                self.plan.update(plan)
                self.assertEqual(self.tool("run"), 1)
                report = self.report()
                self.assertIn(code, self.codes(report))
                self.assertIn("  configuration inputs unchanged (project/config/, project/): "
                              "DIFFERS", self.output)
                self.plan = saved
                shutil.rmtree(self.run_dir)
                for name in ("default.toml", "fifadllzf.toml"):
                    self.write_text(os.path.join(self.project, "config", name),
                                    TEST_CONFIG[name])
                for out in ("default", "fifadllzf"):
                    folder = os.path.join(self.private, "generated", out)
                    shutil.rmtree(folder)
                    os.mkdir(folder, 0o700)
                if os.path.exists(os.path.join(self.project, "stray.toml")):
                    os.unlink(os.path.join(self.project, "stray.toml"))
                self.write_manifest()

    def test_codegen_inputs_are_checked_against_the_inventory(self):
        for plan, code in (({"depfile_extra": ["/etc/hosts"]}, "codegen-input-unexpected"),
                           ({"depfile_skip_configs": True}, "config-inventory-differs")):
            with self.subTest(plan=plan):
                saved = dict(self.plan)
                self.plan.update(plan)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(code, self.codes(self.report()))
                self.plan = saved
                shutil.rmtree(self.run_dir)
                for out in ("default", "fifadllzf"):
                    folder = os.path.join(self.private, "generated", out)
                    shutil.rmtree(folder)
                    os.mkdir(folder, 0o700)
                self.write_manifest()


class ArbitrationTest(B2Fixture):
    """The arbitrations of the owner (D-021): C-a staged by private_project stage-config,
    F-a (no function_table_base), T-a (two hours at most, resources recorded), L-a (info)."""

    def config(self, name, text):
        path = os.path.join(self.project, "config", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def test_a_table_base_in_any_consumed_configuration_blocks_run(self):
        """F-a: a value set in an include, even an indirect one, is a conflict; a 0 in the
        manifest does not undo it (MergeScalar keeps a non-zero value) and is counted too.
        Nothing is changed in the configuration, and codegen does not start."""
        cases = (
            ("in an include", lambda: self.config(
                "default.toml", "function_table_base = 0x8C100000\n" +
                TEST_CONFIG["default.toml"]), 1),
            ("in an indirect include", lambda: (
                self.config("default.toml", 'includes = ["common/base.toml"]\n' +
                            TEST_CONFIG["default.toml"]),
                self.config("common/base.toml", "function_table_base = 0x8C100000\n")), 1),
            ("a 0 in the manifest over an inherited value", lambda: (
                self.config("default.toml", "function_table_base = 0x8C100000\n" +
                            TEST_CONFIG["default.toml"]),
                self.write_manifest(),
                self.write_text(self.manifest, read_text(self.manifest).replace(
                    'out_directory_path = "../generated/default"\n',
                    'out_directory_path = "../generated/default"\n'
                    'function_table_base = 0\n', 1))), 2))
        for name, setup, count in cases:
            with self.subTest(name=name):
                setup()
                with open(os.path.join(self.project, "config", "default.toml")) as f:
                    staged = f.read()
                # Found by the checks before any write: no run folder, nothing started.
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"table_base_settings {count}, ", self.output)
                self.assertIn("finding table-base-conflict", self.output)
                self.assertEqual(self.run_dirs(), [])
                self.assertIsNone(self.recorded())
                with open(os.path.join(self.project, "config", "default.toml")) as f:
                    self.assertEqual(f.read(), staged)
                self.assertNotIn("0x8C1", self.output)
                self.assert_shareable(self.output)
                self.config("default.toml", TEST_CONFIG["default.toml"])
                shutil.rmtree(os.path.join(self.project, "config", "common"),
                              ignore_errors=True)
                self.write_manifest()
        self.assertEqual(self.tool("prepare"), 0, self.output)

    def test_g3_is_checked_at_each_prepare(self):
        """G-3: the kept original is there and consumed by nothing, and default.toml is it
        less its one function_table_base line, nothing else; a residual inherited value
        elsewhere is still a conflict. Each case stops before anything starts."""
        original = os.path.join(self.project, "config", "original", "default.toml")
        cases = (
            ("original missing", lambda: os.unlink(original), "g3-original-missing"),
            ("another change", lambda: self.config(
                "default.toml", TEST_CONFIG["default.toml"] + "0x82000030 = {}\n"),
             "g3-derogation-invalid"),
            ("line not removed", lambda: self.config("default.toml", G3_ORIGINAL),
             "g3-derogation-invalid"),
            ("original consumed", lambda: self.write_text(self.manifest, read_text(
                self.manifest).replace('includes = ["config/default.toml"]',
                                       'includes = ["config/default.toml", '
                                       '"config/original/default.toml"]', 1)),
             "g3-original-consumed"),
            ("residual inherited value", lambda: self.config(
                "fifadllzf.toml", "function_table_base = 0x8C200000\n" +
                TEST_CONFIG["fifadllzf.toml"]), "table-base-conflict"))
        for name, change, code in cases:
            with self.subTest(name=name):
                change()
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"finding {code}", self.output)
                self.assertEqual(self.run_dirs(), [])
                self.assertIsNone(self.recorded())
                self.write_text(original, G3_ORIGINAL)
                for rel, text in TEST_CONFIG.items():
                    self.config(rel, text)
                self.write_manifest()
        self.assertEqual(self.tool("prepare"), 0, self.output)

    def test_a_time_out_above_two_hours_is_refused(self):
        for value in ("7201", "0"):
            with self.subTest(value=value):
                self.assertEqual(self.tool("run", "--timeout", value), 1)
                self.assertIn("finding timeout-above-t-a", self.output)
                self.assertEqual(self.run_dirs(), [])
                self.assertIsNone(self.recorded())
        self.assertEqual(self.tool("prepare", "--timeout", "7200"), 0, self.output)

    def test_resources_are_recorded_without_a_claimed_need(self):
        meminfo = os.path.join(self.records, "meminfo")
        self.write_text(meminfo, "MemTotal:       16384000 kB\nMemFree:  1 kB\n"
                                 "MemAvailable:    8192000 kB\nSwapTotal:       0 kB\n")
        self.assertEqual(self.tool("prepare", "--meminfo", meminfo), 0, self.output)
        self.assertIn("resources            ok                memory_total_mib 16000, "
                      "memory_available_mib 8000, swap_total_mib 0, disk_free_mib ",
                      self.output)
        self.assertIn(", shm_default_limit_mib 8000\n", self.output)
        self.assert_shareable(self.output)

    def test_the_log_level_is_info_and_local(self):
        """L-a: the command sets the info level, and the log stays in the run folder."""
        self.assertEqual(b2.LOG_LEVEL, "info")
        self.assertEqual(self.tool("run"), 0, self.output)
        record = self.recorded()
        self.assertEqual(record["argv"][:2], ["--log-level", "info"])
        self.assertEqual(os.path.dirname(record["argv"][3]), self.run_dirs()[0])
        for level in ("debug", "trace"):
            self.assertNotIn(level, record["argv"])

    def test_the_staged_configuration_of_c_a_passes_prepare(self):
        """C-a end to end, on a synthetic clone with the layout of project A: stage-config
        copies the files and names them; prepare then sees what codegen will consume."""
        pp = load(os.path.join(HERE, "private_project.py"), "private_project_stage")
        shutil.rmtree(os.path.join(self.project, "config"))
        self.write_text(self.manifest, read_text(TEMPLATE))
        source = os.path.join(self.w, "project-a")
        files = {
            "pc/fifawc10_manifest.toml":
                '[project]\nname = "fifawc10"\n\n[entrypoint]\n'
                'file_path = "../out/game-files/default.xex"\n'
                'includes = ["config/codegen_options.toml", "config/default.toml", '
                '"config/default_pointers.toml"]\n\n[[modules]]\nguest_path = "fifadllzf.xex"\n'
                'file_path = "../out/game-files/fifadllzf.xex"\n'
                'includes = ["config/codegen_options.toml", "config/fifadllzf.toml", '
                '"config/fifadllzf_pointers.toml"]\n',
            "pc/config/codegen_options.toml": "\n",
            "pc/config/default.toml": G3_ORIGINAL,
            "pc/config/default_pointers.toml": "[functions]\n0x82000030 = {}\n",
            "pc/config/fifadllzf.toml": TEST_CONFIG["fifadllzf.toml"],
            "pc/config/fifadllzf_pointers.toml": "[functions]\n0x821000C0 = {}\n"}
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(source, rel)), exist_ok=True)
            self.write_text(os.path.join(source, rel), text)
        git = ["git", "-C", source, "-c", "user.name=test", "-c",
               "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", source], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "synthetic project A"], check=True)
        commit = subprocess.run(["git", "-C", source, "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True).stdout.strip()
        findings, notes = pp.stage_config(self.private, source, t1.GUARD, repo=self.repo,
                                          commit=commit)
        self.assertEqual(findings, [], notes)
        self.assertEqual(self.tool("prepare"), 0, self.output)
        self.assertIn("config_files 5, binary_config_files 5, shared_config_files 0, "
                      "config_tree_files 6, config_unused_files 1, include_depth 1", self.output)
        self.assertIn("function_entries 5, crt_entries 2, table_base_settings 0, "
                      "timeout_seconds 7200, g3_original_present True, g3_derogation_ok True",
                      self.output)
        with open(os.path.join(self.project, "config", "original", "default.toml")) as f:
            self.assertEqual(f.read(), G3_ORIGINAL)
        with open(os.path.join(self.project, "config", "default.toml")) as f:
            self.assertEqual(f.read(), TEST_CONFIG["default.toml"])
        self.assertEqual(self.tool("run"), 0, self.output)
        self.assertIn("  B2 result for PB-2 (C2.1 met and generation complete): yes",
                      self.output)


class RunTest(B2Fixture):
    def reset_outputs(self):
        shutil.rmtree(self.run_dir)
        for out in ("default", "fifadllzf"):
            folder = os.path.join(self.private, "generated", out)
            for top, dirs, _ in os.walk(folder):
                for d in dirs:
                    os.chmod(os.path.join(top, d), 0o700)
            shutil.rmtree(folder)
            os.mkdir(folder, 0o700)
        self.write_manifest()

    def test_run_success(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        record = self.recorded()
        log = os.path.join(self.run_dirs()[0], "codegen.log")
        self.assertEqual(record["argv"], ["--log-level", "info", "--log-file", log,
                                          "codegen", self.manifest])
        self.assertNotIn("-f", record["argv"])
        self.assertNotIn("--force", record["argv"])
        self.assertEqual(record["cwd"], self.project)
        self.assertEqual(record["core"], [1, 1])
        for line in ("  game/ unchanged (content, metadata and identity of every entry; "
                     "PB-1 figures): match",
                     "  configuration inputs unchanged (project/config/, project/): match",
                     "  manifest changed only by its sdk_version line: match",
                     "  codegen exit status: expected 0, found 0: match",
                     "  unresolved calls: expected 0, found 0: match",
                     "  millicode errors: expected 0, found 0: match",
                     "  configuration errors: expected 0, found 0: match",
                     "  C2.1 met: yes",
                     "  output folders with a valid codegen.stamp: expected 2, found 2: match",
                     "  files listed by no codegen.stamp: expected 0, found 0: match",
                     "  generation complete (every listed output, every kind, the entry "
                     "files, the log summary): yes",
                     "  B2 result for PB-2 (C2.1 met and generation complete): yes",
                     "decision: this tool does not declare PB-2"):
            self.assertIn(line, self.output)
        self.assertIn("generated_files 26, generated_anomalies 0, generated_unreadable 0",
                      self.output)
        self.assertIn("game_files 4, game_modules_match True, game_entries_hashed 4",
                      self.output)
        self.assert_shareable(self.output)
        self.assert_shareable(self.summary())
        self.assertNotIn("0x82", self.summary())
        # A second run is refused: the output folders are no longer empty.
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding generated-not-empty", self.output)

    def test_unresolved_calls_fail_c21_and_stay_local(self):
        self.plan.update(unresolved=3, millicode=1)
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(sorted(set(self.codes(report))), ["c21-not-met", "codegen-failed"])
        for line in ("  unresolved calls: expected 0, found 3: DIFFERS",
                     "  millicode errors: expected 0, found 1: DIFFERS",
                     "  C2.1 met: no",
                     "  B2 result for PB-2 (C2.1 met and generation complete): no"):
            self.assertIn(line, self.output)
        self.assertEqual(self.outputs(), [])
        self.assertNotIn("0x82", self.output)
        self.assertNotIn("0x83", self.summary())

    def test_a_partial_log_is_refused_not_counted(self):
        self.plan.update(unresolved=2, partial_log=True)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding codegen-log-refused", self.output)
        self.assertIn("  C2.1: the log was refused, not measured", self.output)

    def test_an_empty_or_truncated_log_after_exit_0_is_refused(self):
        """Review 7220519596, point 2: after an exit status 0, a log without the
        `Codegen summary` line, cut in its last line, or empty, is refused: C2.1 is not
        measured, and B2 does not succeed."""
        for key in ("truncated_log", "cut_log", "empty_log"):
            with self.subTest(key=key):
                self.plan[key] = True
                self.assertEqual(self.tool("run"), 1)
                report = self.report()
                self.assertIn("codegen-log-refused", self.codes(report))
                self.assertIn("  C2.1: the log was refused, not measured", self.output)
                self.assertIn("  B2 result for PB-2 (C2.1 met and generation complete): no",
                              self.output)
                del self.plan[key]
                self.reset_outputs()

    def test_success_needs_a_complete_generation(self):
        """Review 7220519596, point 2: an exit status 0 and a clean log are not enough.
        Each missing or spoiled output is a finding, apart from C2.1."""
        cases = (({"no_outputs": True}, "generation-incomplete"),
                 ({"no_stamp": 1}, "generation-incomplete"),
                 ({"bad_stamp": 0}, "generation-incomplete"),
                 ({"missing_output": 1}, "generation-incomplete"),
                 ({"no_registry": "dll_targets.cmake"}, "generation-incomplete"),
                 ({"swap_build": True}, "generation-incomplete"),
                 ({"summary_offset": 1}, "generation-incomplete"),
                 ({"unlisted": True}, "generated-unlisted"),
                 ({"unreadable_dir": True}, "tree-unreadable"),
                 ({"leave_link": True}, "generated-anomaly"))
        for plan, code in cases:
            with self.subTest(plan=plan):
                self.plan.update(plan)
                self.assertEqual(self.tool("run"), 1)
                report = self.report()
                self.assertIn(code, self.codes(report), self.output)
                self.assertTrue(self.step(report, "c21")["facts"]["c21_met"])
                self.assertIn("  C2.1 met: yes", self.output)
                self.assertIn("  B2 result for PB-2 (C2.1 met and generation complete): no",
                              self.output)
                for key in plan:
                    del self.plan[key]
                self.reset_outputs()

    def test_changes_to_inputs_and_outputs_are_findings(self):
        """In the fake sandbox nothing is read-only: the controls after the step must see a
        changed module, another change to the manifest, and a link in the outputs."""
        self.plan.update(modify_module=True, change_manifest=True, leave_link=True)
        self.assertEqual(self.tool("run"), 1)
        codes = set(self.codes(self.report()))
        self.assertTrue({"game-changed", "manifest-changed", "generated-anomaly"} <= codes,
                        codes)
        self.assertIn("  game/ unchanged (content, metadata and identity of every entry; "
                      "PB-1 figures): DIFFERS", self.output)

    def test_a_module_changed_at_constant_size_and_mtime_is_seen(self):
        """Review 7220519596, point 3: the inventory of game/ hashes every file, so a
        change that keeps the size and the modification time is a finding, for a module
        and for any other file."""
        for rel in ("../game/default.xex", "../game/media/sub/b.txt"):
            with self.subTest(rel=rel):
                path = os.path.normpath(os.path.join(self.project, rel))
                with open(path, "rb") as f:
                    original = f.read()
                before = os.stat(path)
                self.plan["same_stat"] = [rel]
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("game-changed", self.codes(self.report()))
                after = os.stat(path)
                self.assertEqual((after.st_size, after.st_mtime_ns),
                                 (before.st_size, before.st_mtime_ns))
                del self.plan["same_stat"]
                with open(path, "wb") as f:
                    f.write(original)
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                self.reset_outputs()

    def test_crash_and_time_out_are_findings_and_postflight_runs(self):
        for key, value, code in (("signal", "KILL", "codegen-crashed"),
                                 ("sleep", 60, "codegen-timeout")):
            with self.subTest(key=key):
                saved = dict(self.plan)
                self.plan[key] = value
                self.assertEqual(self.tool("run", "--timeout", "2"), 1)
                report = self.report()
                self.assertIn(code, self.codes(report))
                self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
                self.plan = saved
                shutil.rmtree(self.run_dir)

    def test_the_proof_is_per_profile(self):
        """A B1 proof does not open B2: the proof is bound to the profile and its file. A
        B2 rehearsal acquires its own, and run then passes."""
        self.remove_proof()
        self.write_proof(profile=b1.B1_PROFILE)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding core-proof-missing", self.output)
        self.assertIsNone(self.recorded())
        self.write_proof(profile_sha256="0" * 64)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding core-proof-missing", self.output)
        self.remove_proof()
        self.assertEqual(self.tool("rehearse"), 1)
        self.assertEqual(self.codes(self.report()), ["core-proof-missing"])
        self.assertEqual(self.tool("run"), 0, self.output)

    def test_nothing_is_sent_anywhere(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        with open(self.trap) as f:
            calls = f.read().splitlines()
        self.assertEqual([c for c in calls if c.startswith("UPLOAD")], [])

    def test_killed_supervisor_can_be_resumed(self):
        self.plan["sleep"] = 300
        proc = self.start("run")
        deadline = time.monotonic() + 60
        record_file = None
        while time.monotonic() < deadline:
            dirs = self.run_dirs()
            if dirs and os.path.exists(os.path.join(dirs[0], "fake-record.json")):
                record_file = os.path.join(dirs[0], "fake-record.json")
                break
            time.sleep(0.1)
        self.assertIsNotNone(record_file, "codegen did not start")
        proc.kill()
        proc.communicate()
        name = os.path.basename(self.run_dirs()[0])
        state = b1.read_state(self.run_dirs()[0])
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding incomplete-run", self.output)
        os.kill(state["bwrap_pid"], 9)
        for _ in range(100):
            if b1.process_start(state["bwrap_pid"]) is None:
                break
            time.sleep(0.05)
        for pid in self.fake_rexglue_pids():
            os.kill(pid, 9)
        self.assertEqual(self.tool("resume", "--run-folder", name), 1, self.output)
        self.assertIn("interrupted", self.codes(self.report("report-resume.json")))
        self.assertEqual(b1.read_state(self.run_dir)["phase"], "complete")


def real_bwrap():
    return t1.real_bwrap()


class RealSandboxTest(B2Fixture):
    def setUp(self):
        super().setUp()
        self.real, self.reason = real_bwrap()
        self.assertTrue(os.environ.get("B1_PYTHON_CLOSURE"),
                        "set B1_PYTHON_CLOSURE to a closureInfo folder of this Python")

    def test_real_sandbox_keeps_game_read_only(self):
        """With the real bubblewrap: the B2 probe passes (game/ and project/config/
        write-denied, generated/ and project/ writable), and a fake codegen that writes
        into game/, project/config/, the home folder and the repository, even at constant
        size and modification time, is refused by the sandbox, while its outputs and the
        rewrite of the manifest in project/ succeed."""
        if self.real is None:
            self.fail("bubblewrap is required for this test (B1_REAL_BWRAP or PATH)")
        self.bwrap = self.real
        if self.reason:
            t1.say_mode(f"REAL SANDBOX: unavailable ({self.reason})")
            self.assertEqual(self.tool("rehearse"), 1)
            self.assertIn("sandbox-unavailable", self.codes(self.report()))
            return
        t1.say_mode("REAL SANDBOX: available")
        self.remove_proof()
        self.set_core_pattern("core")
        self.assertEqual(self.tool("rehearse"), 1, self.output)
        report = self.report()
        sandbox = self.step(report, "sandbox")
        self.assertEqual(sandbox["facts"]["probe_failed_checks"], [], sandbox)
        self.assertEqual(sandbox["facts"]["probe_checks_passed"], len(B2.probe_checks()))
        self.assertIn("write-denied-game", B2.probe_checks())
        self.assertIn("write-denied-project-config", B2.probe_checks())
        shutil.rmtree(self.run_dir)
        self.set_core_pattern(t1.PIPE)
        self.write_proof()
        targets = [os.path.join(self.game, "leak"), os.path.join(self.home, "leak"),
                   os.path.join(self.repo, "leak"),
                   os.path.join(self.project, "config", "leak.toml")]
        self.plan["write_outside"] = targets
        self.plan["modify_module"] = True
        self.plan["modify_config"] = True
        self.plan["same_stat"] = ["config/default.toml", "../game/fifadllzf.xex"]
        self.assertEqual(self.tool("run"), 0, self.output)
        record = self.recorded()
        for target in targets:
            self.assertEqual(record["attempts"][target], "EROFS")
            self.assertFalse(os.path.exists(target))
        for name in ("module", "config", "config/default.toml", "../game/fifadllzf.xex"):
            self.assertEqual(record["attempts"][name], "EROFS", name)
        self.assertEqual(record["core"], [1, 1])
        for line in ("  C2.1 met: yes",
                     "  game/ unchanged (content, metadata and identity of every entry; "
                     "PB-1 figures): match",
                     "  configuration inputs unchanged (project/config/, project/): match",
                     "  manifest changed only by its sdk_version line: match",
                     "  B2 result for PB-2 (C2.1 met and generation complete): yes"):
            self.assertIn(line, self.output)


class UnitTest(unittest.TestCase):
    def test_probe_checks_of_b2(self):
        checks = B2.probe_checks()
        self.assertEqual(len(checks), len(set(checks)))
        for name in ("write-denied-game", "write-denied-project-config", "writable-generated",
                     "writable-project", "writable-app", "writable-tmp",
                     "store-closure-only", "core-limit-one", "shm-private"):
            self.assertIn(name, checks)
        self.assertNotIn("writable-game", checks)
        self.assertEqual(len(checks), 30)
        self.assertEqual(b1.B1_PROFILE.probe_checks(), b1.PROBE_CHECKS)

    def test_inventory_sees_content_identity_and_errors(self):
        """Review 7220519596, point 3: the inventory hashes every file and keeps its
        identity, so a change at constant size and modification time, or a file replaced
        by an identical copy, changes it; an unreadable folder is an anomaly."""
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            write_tree(root, GAME_TREE)
            before = b2.inventory(b1, root)
            self.assertEqual(b2.inventory(b1, root)["digest"], before["digest"])
            self.assertEqual(sum(1 for e in before["entries"] if e[1] == "file" and e[8]), 4)
            path = os.path.join(root, "media", "a.txt")
            st = os.stat(path)
            with open(path, "w") as f:
                f.write("b\n")
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
            self.assertEqual(os.stat(path).st_size, st.st_size)
            changed = b2.inventory(b1, root)
            self.assertNotEqual(changed["digest"], before["digest"])
            copy = path + ".new"
            shutil.copy2(path, copy)
            os.replace(copy, path)
            self.assertNotEqual(b2.inventory(b1, root)["digest"], changed["digest"])
            sub = os.path.join(root, "media", "sub")
            os.chmod(sub, 0)
            try:
                if os.geteuid() != 0:
                    found = b2.inventory(b1, root)
                    self.assertEqual([a[0] for a in found["unreadable"]],
                                     ["unreadable folder"])
            finally:
                os.chmod(sub, 0o700)

    def test_survey_tree_is_unchanged_without_listing(self):
        """B1 calls survey_tree without listing: its figures keep their keys."""
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            write_tree(root, GAME_TREE)
            figures = b1.survey_tree(root, {"default.xex": ""})
            self.assertNotIn("entries", figures)
            listed = b1.survey_tree(root, {"default.xex": ""}, listing=True, content=True)
            self.assertEqual(figures["modules"], listed["modules"])
            self.assertEqual({k: v for k, v in listed.items() if k != "entries"}, figures)

    def test_depfile_and_stamp_formats(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            dep = os.path.join(root, "codegen.d")
            with open(dep, "w") as f:
                f.write("/a b/codegen.build.stamp: \\\n  /x/y\\ z.toml \\\n  /p/$$q#.xex\n"
                        .replace("#", "\\#"))
            self.assertEqual(b2.read_depfile(dep), ("/a b/codegen.build.stamp",
                                                    ["/x/y z.toml", "/p/$q#.xex"]))
            with open(dep, "w") as f:
                f.write("/a: \\\n  /x")
            self.assertIsNone(b2.read_depfile(dep))
            stamp = os.path.join(root, "codegen.stamp")
            for doc, ok in (({"version": 1, "fingerprint": "f", "outputs": ["a.cpp"]}, True),
                            ({"version": 2, "fingerprint": "f", "outputs": ["a.cpp"]}, False),
                            ({"version": 1, "fingerprint": "", "outputs": ["a.cpp"]}, False),
                            ({"version": 1, "fingerprint": "f", "outputs": []}, False),
                            ({"version": 1, "fingerprint": "f", "outputs": ["../x"]}, False),
                            ({"version": 1, "fingerprint": "f", "outputs": ["a", "a"]},
                             False)):
                with self.subTest(doc=doc):
                    with open(stamp, "w") as f:
                        json.dump(doc, f)
                    self.assertEqual(b2.read_stamp(stamp) is not None, ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)

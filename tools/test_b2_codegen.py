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
# environment in the run folder, then follows the plan: outputs in each output folder of the
# manifest, a log in the formats of ReXGlue v0.11.0, and the rewrite of [project].sdk_version
# after a success. It can also misbehave: write in game/, outside, change the manifest,
# leave a link, write a partial log, crash or hang.
FAKE_CODEGEN = r'''
import errno, json, os, resource, signal, sys, time, tomllib
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
log = open(log_path, "a")
log.write("[2026-11-27 12:00:00.000] [info] codegen: project wc2010, 1 DLL\n")
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
save()
if plan.get("sleep"):
    time.sleep(plan["sleep"])
if plan.get("signal"):
    os.kill(os.getpid(), getattr(signal, "SIG" + plan["signal"]))
if errors:
    sys.exit(1)
for index, binary in enumerate(binaries):
    out = os.path.normpath(os.path.join(base, binary["out_directory_path"]))
    prefix = os.path.splitext(os.path.basename(binary["file_path"]))[0]
    with open(os.path.join(out, f"{prefix}_init.cpp"), "w") as f:
        f.write("const PPCFuncMapping kPPCFuncMappings[] = {\n"
                "\t{ 0x82000000, sub_82000000 },\n\t{ 0, nullptr }\n};\n")
    for name in (f"{prefix}_recomp.0.cpp", f"{prefix}_funcs.h", "codegen.stamp"):
        with open(os.path.join(out, name), "w") as f:
            f.write("// synthetic output\n")
    if index == 0:
        with open(os.path.join(out, "codegen.d"), "w") as f:
            f.write("synthetic dependency list\n")
    if plan.get("leave_link") and index == 0:
        os.symlink("/etc/passwd", os.path.join(out, "link"))
with open(manifest) as f:
    text = f.read()
text = text.replace('sdk_version = "0.11.0"', 'sdk_version = "0.11.0"  # rewritten', 1)
if plan.get("change_manifest"):
    text = text.replace('name = "wc2010"', 'name = "other"', 1)
tmp = manifest + ".tmp"
with open(tmp, "w") as f:
    f.write(text)
os.rename(tmp, manifest)
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
                     "output_folders 2, output_folders_empty True",
                     "test-config          ok                config_files 2, "
                     "function_entries 3, crt_entries 2",
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
                  "test-config-absent"))
        os.makedirs(os.path.join(self.private, "app"), exist_ok=True)
        for name, change, code in cases:
            with self.subTest(name=name):
                change()
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"finding {code}", self.output)
                self.assertIsNone(self.recorded())
                self.write_manifest()
                for path in ("generated/default/old.cpp", "app/rexglue.toml"):
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


class RunTest(B2Fixture):
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
        for line in ("  game/ unchanged, PB-1 figures and module hashes: match",
                     "  manifest changed only by its sdk_version line: match",
                     "  codegen exit status: expected 0, found 0: match",
                     "  unresolved calls: expected 0, found 0: match",
                     "  millicode errors: expected 0, found 0: match",
                     "  configuration errors: expected 0, found 0: match",
                     "  C2.1 met: yes",
                     "  output folders with a codegen.stamp: 2",
                     "decision: this tool does not declare PB-2"):
            self.assertIn(line, self.output)
        self.assertIn("generated_files 9, modules_with_stamp 2, generated_anomalies 0",
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
                     "  C2.1 met: no"):
            self.assertIn(line, self.output)
        self.assertEqual(self.outputs(), [])
        self.assertNotIn("0x82", self.output)
        self.assertNotIn("0x83", self.summary())

    def test_a_partial_log_is_refused_not_counted(self):
        self.plan.update(unresolved=2, partial_log=True)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding codegen-log-refused", self.output)
        self.assertIn("  C2.1: the log was refused, not measured", self.output)

    def test_changes_to_inputs_and_outputs_are_findings(self):
        """In the fake sandbox nothing is read-only: the controls after the step must see a
        changed module, another change to the manifest, and a link in the outputs."""
        self.plan.update(modify_module=True, change_manifest=True, leave_link=True)
        self.assertEqual(self.tool("run"), 1)
        codes = set(self.codes(self.report()))
        self.assertTrue({"game-changed", "manifest-changed", "generated-anomaly"} <= codes,
                        codes)
        self.assertIn("  game/ unchanged, PB-1 figures and module hashes: DIFFERS",
                      self.output)

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
        """With the real bubblewrap: the B2 probe passes (game/ write-denied, generated/
        and project/ writable), and a fake codegen that writes into game/, the home folder
        and the repository is refused by the sandbox, while its outputs and the rewrite of
        the manifest succeed."""
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
        shutil.rmtree(self.run_dir)
        self.set_core_pattern(t1.PIPE)
        self.write_proof()
        targets = [os.path.join(self.game, "leak"), os.path.join(self.home, "leak"),
                   os.path.join(self.repo, "leak")]
        self.plan["write_outside"] = targets
        self.plan["modify_module"] = True
        self.assertEqual(self.tool("run"), 0, self.output)
        record = self.recorded()
        for target in targets:
            self.assertEqual(record["attempts"][target], "EROFS")
            self.assertFalse(os.path.exists(target))
        self.assertEqual(record["attempts"]["module"], "EROFS")
        self.assertEqual(record["core"], [1, 1])
        self.assertIn("  C2.1 met: yes", self.output)
        self.assertIn("  game/ unchanged, PB-1 figures and module hashes: match", self.output)


class UnitTest(unittest.TestCase):
    def test_probe_checks_of_b2(self):
        checks = B2.probe_checks()
        self.assertEqual(len(checks), len(set(checks)))
        for name in ("write-denied-game", "writable-generated", "writable-project",
                     "writable-app", "writable-tmp", "store-closure-only", "core-limit-one",
                     "shm-private"):
            self.assertIn(name, checks)
        self.assertNotIn("writable-game", checks)
        self.assertEqual(b1.B1_PROFILE.probe_checks(), b1.PROBE_CHECKS)

    def test_tree_listing_sees_every_change(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            write_tree(root, GAME_TREE)
            _, before = b2.tree_listing(root)
            self.assertEqual(b2.tree_listing(root)[1], before)
            with open(os.path.join(root, "media", "new"), "w") as f:
                f.write("x")
            self.assertNotEqual(b2.tree_listing(root)[1], before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

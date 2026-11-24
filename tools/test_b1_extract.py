#!/usr/bin/env python3
"""Tests of tools/b1_extract.py (J2 step B1, ticket #32), on synthetic folders only.

No disc image, no module and no game file is used. The "image" is a few lines of text;
`rexglue`, `findmnt`, `coredumpctl` and `nix` are replaced by small Python scripts that
record how they are called. private_guard and find are the real ones. The tool runs as a
subprocess, as on the user's machine, so that its umask, core size limit, working folder
and environment are those of a real run.

The tool refuses root, so the tests that start it need an unprivileged user, as in the Nix
build sandbox. Not covered here, because they need root or a real mount: a folder on
another file system (simulated in unit tests), a real systemd-coredump record, and a real
read-only bind mount. docs/J2_B1_EXTRACTION.md section 6 lists these gaps.

Run: python3 -I tools/test_b1_extract.py
"""

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "b1_extract.py")
GUARD = os.path.join(HERE, "private_guard.py")
SUBFOLDERS = ("iso", "game", "xex", "generated", "cache", "saves", "logs")


def load_tool():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("b1_extract", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b1 = load_tool()

# The fake rexglue. It records its arguments, working folder, umask, core size limit and
# environment, then follows the plan of the test: write a tree, print ReXGlue's summary
# block, write elsewhere, then exit, crash or wait.
FAKE_REXGLUE = r'''
import json, os, resource, signal, sys, time
plan = json.load(open(os.environ["B1_FAKE_PLAN"]))
mask = os.umask(0o077)
os.umask(mask)
keep = ("REX_", "TMPDIR", "XDG_", "NO_COLOR", "HOME", "WC2010_PRIVATE_DIR")
with open(os.environ["B1_FAKE_RECORD"], "w") as f:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "umask": mask,
               "core": list(resource.getrlimit(resource.RLIMIT_CORE)),
               "env": {k: v for k, v in os.environ.items() if k.startswith(keep)}}, f)
dest = sys.argv[-1]
files = dirs = size = 0
def write(folder, tree):
    global files, dirs, size
    for name, value in tree.items():
        path = os.path.join(folder, name)
        if isinstance(value, dict):
            os.makedirs(path, exist_ok=True)
            dirs += 1
            write(path, value)
        else:
            with open(path, "w") as f:
                f.write(value)
            files += 1
            size += len(value.encode())
write(dest, plan.get("tree", {}))
for rel, target in plan.get("links", []):
    os.symlink(target, os.path.join(dest, rel))
for rel in plan.get("fifos", []):
    os.mkfifo(os.path.join(dest, rel))
for src, dst in plan.get("hardlinks", []):
    os.link(os.path.join(dest, src), os.path.join(dest, dst))
for i in range(plan.get("stdout_lines", 0)):
    print(f"spam line {i} from the fake rexglue")
if plan.get("block", True):
    nodes = plan.get("nodes", files + dirs + 1)
    sys.stderr.write("Extracting container:\n  Source: %s\n  Type:   %s\n  Nodes:  %s\n"
                     "  Bytes:  %s\n\n" % (sys.argv[-2], plan.get("type", "GDFX"), nodes,
                                           plan.get("bytes", size)))
log_root = os.environ.get("REX_APP_LOG_ROOT") or os.path.join(os.environ["REX_APP_ROOT"], "logs")
os.makedirs(log_root, exist_ok=True)
with open(os.path.join(log_root, "rexglue_001.log"), "w") as f:
    f.write("fake log\n")
for path in plan.get("write_outside", []):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("written outside\n")
if plan.get("add_mount"):
    with open(os.environ["B1_FAKE_MOUNTS"], "a") as f:
        f.write(plan["add_mount"] + "\n")
if plan.get("modify_image"):
    image = sys.argv[-2]
    os.chmod(image, 0o600)
    with open(image, "a") as f:
        f.write("changed\n")
    os.chmod(image, 0o400)
for path in plan.get("lock", []):
    os.chmod(path, 0)
if plan.get("sleep"):
    time.sleep(plan["sleep"])
if plan.get("signal"):
    os.kill(os.getpid(), getattr(signal, "SIG" + plan["signal"]))
sys.exit(plan.get("exit", 0))
'''

FAKE_FINDMNT = r'''
import os, sys
if sys.argv[1:] != ["-rn", "-o", "TARGET"]:
    sys.exit(64)
if os.environ.get("B1_FAKE_FINDMNT_STATUS"):
    sys.exit(int(os.environ["B1_FAKE_FINDMNT_STATUS"]))
with open(os.environ["B1_FAKE_MOUNTS"], "rb") as f:
    sys.stdout.buffer.write(f.read())
'''

FAKE_COREDUMPCTL = r'''
import os, re, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("coredumpctl " + " ".join(sys.argv[1:]) + "\n")
if len(sys.argv) != 4 or sys.argv[1:3] != ["list", "--no-pager"] or \
        not re.fullmatch(r"--since=@[0-9]+", sys.argv[3]):
    sys.exit(64)
entries = os.environ.get("B1_FAKE_COREDUMPS", "")
if entries:
    print("TIME PID UID GID SIG COREFILE EXE SIZE")
    print(entries)
    sys.exit(0)
print("No coredumps found.", file=sys.stderr)
sys.exit(1)
'''

FAKE_NIX = r'''
import os, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("nix " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1:3] != ["store", "verify"] or len(sys.argv) != 4:
    sys.exit(64)
sys.exit(int(os.environ.get("B1_FAKE_NIX_STATUS", "0")))
'''

# Commands that could send data elsewhere. They must never run.
TRAP = r'''
import os, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("UPLOAD " + os.path.basename(sys.argv[0]) + " " + " ".join(sys.argv[1:]) + "\n")
sys.exit(1)
'''

# git, logged, then the real git.
FAKE_GIT = r'''
import os, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("git " + " ".join(sys.argv[1:]) + "\n")
os.execv(REAL_GIT, [REAL_GIT] + sys.argv[1:])
'''

# A private_guard whose preflight or postflight exits with a given status; every other use
# is the real guard, also as a module.
FAKE_GUARD = r'''
import os, runpy, sys
REAL = {real!r}
if __name__ == "__main__":
    for name in ("preflight", "postflight"):
        if name in sys.argv and os.environ.get("B1_FAKE_GUARD_" + name.upper()):
            sys.exit(int(os.environ["B1_FAKE_GUARD_" + name.upper()]))
    sys.argv[0] = REAL
    runpy.run_path(REAL, run_name="__main__")
else:
    globals().update(runpy.run_path(REAL))
'''

DEFAULT_TREE = {
    "default.xex": "synthetic entry module, not a XEX\n",
    "fifadllzf.xex": "synthetic second module, not a XEX\n",
    ".hidden": "a name that starts with a dot\n",
    "media": {"a.txt": "a\n", "sub": {"b.txt": "b\n"}},
}


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def reference_for(tree):
    files = dirs = 0

    def walk(node):
        nonlocal files, dirs
        for value in node.values():
            if isinstance(value, dict):
                dirs += 1
                walk(value)
            else:
                files += 1
    walk(tree)
    return {"source": "synthetic test reference", "files": files, "directories": dirs,
            "modules": {"default.xex": sha256(tree["default.xex"]),
                        "fifadllzf.xex": sha256(tree["fifadllzf.xex"])}}


def write_script(path, body, **values):
    with open(path, "w") as f:
        f.write(f"#!{sys.executable} -I\n")
        for name, value in values.items():
            f.write(f"{name} = {value!r}\n")
        f.write(body)
    os.chmod(path, 0o755)


def snapshot(top, skip=()):
    """Every path under `top`, with its type, size and modification time. `skip` holds the
    folders left out: the records of the fake commands, and .git, whose index `git status`
    refreshes (private_guard leaves it out of its search for the same reason)."""
    seen = {}
    for root, dirs, files in os.walk(top):
        dirs[:] = [name for name in dirs
                   if name != ".git" and os.path.join(root, name) not in skip]
        for name in dirs + files:
            path = os.path.join(root, name)
            st = os.lstat(path)
            seen[path] = (stat.S_IFMT(st.st_mode), st.st_size, st.st_mtime_ns)
    return seen


@unittest.skipIf(os.geteuid() == 0, "the tool refuses root: run the tests as an "
                                    "unprivileged user, as in the Nix build sandbox")
class Fixture(unittest.TestCase):
    """A synthetic machine: a home folder holding the private folder and the repository,
    a /tmp, a /dev/shm, a store with the SDK and the entry CP-3 already knows, and the fake
    commands."""

    def setUp(self):
        self.w = tempfile.mkdtemp(prefix="b1-test-")
        self.addCleanup(self.cleanup)
        w = self.w
        self.home = os.path.join(w, "home")
        self.private = os.path.join(self.home, "private")
        os.makedirs(self.private)
        os.chmod(self.home, 0o700)
        os.chmod(self.private, 0o700)
        for name in SUBFOLDERS:
            os.mkdir(os.path.join(self.private, name), 0o700)
        self.iso = os.path.join(self.private, "iso", b1.ISO_NAME)
        with open(self.iso, "w") as f:
            f.write("synthetic disc image, no game data\n" * 100)
        os.chmod(self.iso, 0o444)
        self.game = os.path.join(self.private, "game")
        self.logs = os.path.join(self.private, "logs")

        self.repo = os.path.join(self.home, "dev", "repo")
        os.makedirs(self.repo)
        git = shutil.which("git")
        self.assertIsNotNone(git, "git is needed")
        quiet = {"capture_output": True, "check": True}
        subprocess.run([git, "init", "-q", self.repo], **quiet)
        with open(os.path.join(self.repo, "README"), "w") as f:
            f.write("synthetic repository\n")
        subprocess.run([git, "-C", self.repo, "add", "README"], **quiet)
        subprocess.run([git, "-C", self.repo, "-c", "user.name=test", "-c",
                        "user.email=test@example.invalid", "commit", "-q", "-m", "init"],
                       **quiet)

        self.store = os.path.join(w, "store")
        self.sdk = os.path.join(self.store, "fake-rexglue-sdk-0.11.0")
        os.makedirs(os.path.join(self.sdk, "bin"))
        write_script(os.path.join(self.sdk, "bin", "rexglue"), FAKE_REXGLUE)
        self.known = os.path.join(self.store, b1.KNOWN_STORE_ENTRY)
        with open(self.known, "wb") as f:
            f.truncate(101 * 1024 * 1024)  # sparse: over the 100 MiB threshold of CP-3

        self.tmp = os.path.join(w, "tmp")
        self.shm = os.path.join(w, "shm")
        self.records = os.path.join(w, "records")
        self.bin = os.path.join(w, "bin")
        for path in (self.tmp, self.shm, self.records, self.bin):
            os.mkdir(path, 0o700)
        self.record = os.path.join(self.records, "rexglue.json")
        self.trap = os.path.join(self.records, "trap.log")
        self.mounts = os.path.join(self.records, "mounts.txt")
        self.persist = os.path.join(self.home, "persist")
        self.persist_space = os.path.join(self.home, ".local", "share", "persist b")
        os.makedirs(self.persist)
        os.makedirs(self.persist_space)
        self.bound_file = os.path.join(self.home, ".bash_history")
        with open(self.bound_file, "w") as f:
            f.write("bound file\n")
        self.set_mounts(["/", "/nix/store", self.home, self.persist,
                         self.persist_space.replace(" ", "\\x20"), self.bound_file,
                         "/proc"])
        write_script(os.path.join(self.bin, "findmnt"), FAKE_FINDMNT)
        write_script(os.path.join(self.bin, "coredumpctl"), FAKE_COREDUMPCTL)
        write_script(os.path.join(self.bin, "nix"), FAKE_NIX)
        write_script(os.path.join(self.bin, "git"), FAKE_GIT, REAL_GIT=git)
        for name in ("curl", "wget", "ssh", "scp", "rsync", "nc", "gh", "nix-store", "nix-copy-closure"):
            write_script(os.path.join(self.bin, name), TRAP)
        self.guard = GUARD
        self.tree = dict(DEFAULT_TREE)
        self.plan = {"tree": self.tree}
        self.reference = os.path.join(self.records, "reference.json")
        self.write_reference(reference_for(self.tree))
        self.extra_env = {}

    def cleanup(self):
        for root, dirs, files in os.walk(self.w):
            for name in dirs:
                try:
                    os.chmod(os.path.join(root, name), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.w, ignore_errors=True)

    def set_mounts(self, targets):
        with open(self.mounts, "w") as f:
            f.write("".join(target + "\n" for target in targets))

    def write_reference(self, reference):
        with open(self.reference, "w") as f:
            json.dump(reference, f)

    def env(self):
        env = {"PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
               "HOME": self.home, "WC2010_PRIVATE_DIR": self.private,
               "B1_FAKE_PLAN": os.path.join(self.records, "plan.json"),
               "B1_FAKE_RECORD": self.record, "B1_FAKE_TRAP": self.trap,
               "B1_FAKE_MOUNTS": self.mounts,
               # Inherited ReXGlue settings that the tool must drop.
               "REX_LOG_LEVEL": "trace", "REX_LOG_FILE": "true"}
        env.update(self.extra_env)
        return env

    def tool(self, command, *extra, timeout=None):
        with open(os.path.join(self.records, "plan.json"), "w") as f:
            json.dump(self.plan, f)
        argv = [sys.executable, "-I", TOOL, "--repo", self.repo, "--sdk", self.sdk,
                "--guard", self.guard, "--store-dir", self.store, "--tmp-watch", self.tmp,
                "--shm-dir", self.shm, "--nix", os.path.join(self.bin, "nix"),
                "--findmnt", os.path.join(self.bin, "findmnt"),
                "--coredumpctl", os.path.join(self.bin, "coredumpctl"),
                "--reference", self.reference, *extra, command]
        result = subprocess.run(argv, capture_output=True, text=True, env=self.env(),
                                cwd=self.w, timeout=timeout or 300)
        self.output = result.stdout + result.stderr
        return result.returncode

    def run_dirs(self):
        return sorted(os.path.join(self.logs, name) for name in os.listdir(self.logs)
                      if name.startswith("b1-"))

    def report(self):
        dirs = self.run_dirs()
        self.assertEqual(len(dirs), 1, dirs)
        with open(os.path.join(dirs[0], "report.json")) as f:
            self.run_dir = dirs[0]
            return json.load(f)

    def step(self, report, name):
        found = [item for item in report["steps"] if item["step"] == name]
        self.assertEqual(len(found), 1, f"{name}: {[i['step'] for i in report['steps']]}")
        return found[0]

    def summary(self):
        with open(os.path.join(self.run_dirs()[0], "summary.txt")) as f:
            return f.read()

    def recorded(self):
        with open(self.record) as f:
            return json.load(f)

    def assert_postflight_ran(self, report):
        post = self.step(report, "postflight")
        self.assertIn(post["exit_code"], (0, 1))
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "postflight.txt")))
        return post

    def assert_no_local_path(self, text):
        for path in (self.private, self.home, self.w, self.repo):
            self.assertNotIn(path, text)


class PrepareTest(Fixture):
    def test_prepare_passes_and_writes_nothing(self):
        before = snapshot(self.w, skip=(self.records,))
        self.assertEqual(self.tool("prepare"), 0, self.output)
        self.assertIn("outcome: no finding", self.output)
        self.assertIn("mount_points_watched 2", self.output)
        self.assertIn("mount_points_not_folders 1", self.output)
        self.assertEqual(snapshot(self.w, skip=(self.records,)), before)
        self.assertEqual(self.run_dirs(), [])
        self.assert_no_local_path(self.output)

    def test_absent_image_is_refused(self):
        os.chmod(os.path.dirname(self.iso), 0o700)
        os.unlink(self.iso)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: disc image absent", self.output)

    def test_writable_image_is_refused(self):
        os.chmod(self.iso, 0o644)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: writable disc image", self.output)

    def test_image_link_is_refused(self):
        outside = os.path.join(self.w, "elsewhere.iso")
        os.rename(self.iso, outside)
        os.symlink(outside, self.iso)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: the disc image is a symbolic link", self.output)

    def test_non_empty_game_folder_is_refused_and_left_alone(self):
        old = os.path.join(self.game, ".left-over")
        with open(old, "w") as f:
            f.write("kept\n")
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: game/ is not empty", self.output)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("nothing was started", self.output)
        self.assertEqual(self.run_dirs(), [])
        self.assertFalse(os.path.exists(self.record))
        with open(old) as f:
            self.assertEqual(f.read(), "kept\n")

    def test_game_or_logs_link_is_refused(self):
        for name in ("game", "logs"):
            with self.subTest(name=name):
                path = os.path.join(self.private, name)
                outside = os.path.join(self.w, f"outside-{name}")
                os.rename(path, outside)
                os.symlink(outside, path)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding: symbolic link where a folder is expected", self.output)
                self.assertEqual(os.listdir(outside), [])
                os.unlink(path)
                os.rename(outside, path)

    def test_dirty_repository_is_refused(self):
        with open(os.path.join(self.repo, "untracked"), "w") as f:
            f.write("x\n")
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: the repository is not clean", self.output)

    def test_sdk_outside_the_store_or_not_built_is_refused(self):
        other = os.path.join(self.w, "fake-rexglue-sdk-0.11.0")
        shutil.copytree(self.sdk, other)
        self.sdk, sdk = other, self.sdk
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: the SDK is not a store path", self.output)
        self.sdk = os.path.join(self.store, "missing-rexglue-sdk-0.11.0")
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: the SDK is not built", self.output)
        self.sdk = os.path.join(self.store, "fake-rexglue-sdk-0.10.0")
        shutil.copytree(sdk, self.sdk)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: the SDK is not ReXGlue 0.11.0", self.output)

    def test_private_folder_open_to_others_is_refused(self):
        os.chmod(self.private, 0o755)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding: the private folder has mode 0755", self.output)
        self.assertFalse(os.path.exists(self.record))

    def test_findmnt_failure_stops_everything(self):
        self.extra_env["B1_FAKE_FINDMNT_STATUS"] = "1"
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding: cannot list the mount points", self.output)
        self.assertEqual(self.run_dirs(), [])
        self.assertFalse(os.path.exists(self.record))

    def test_absent_or_unreadable_mount_point_is_found_by_prepare(self):
        locked = os.path.join(self.home, "locked")
        os.mkdir(locked, 0o000)
        self.set_mounts([self.persist, locked, os.path.join(self.home, "gone")])
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding: watched place not readable (x1)", self.output)
        self.assertIn("finding: watched place absent or not a folder (x1)", self.output)


class RunTest(Fixture):
    def test_run_success(self):
        self.plan["stdout_lines"] = 500
        self.assertEqual(self.tool("run"), 0, self.output)
        report = self.report()
        self.assertEqual([i["status"] for i in report["steps"]
                          if i["status"] not in ("ok",)], [], report)
        record = self.recorded()
        self.assertEqual(record["argv"], ["vfs", "dump", self.iso, self.game])
        self.assertEqual(record["cwd"], self.private)
        self.assertEqual(record["umask"], 0o077)
        self.assertEqual(record["core"], [0, 0])
        env = record["env"]
        self.assertNotIn("REX_LOG_LEVEL", env)
        self.assertNotIn("REX_LOG_FILE", env)
        self.assertEqual(env["REX_APP_ROOT"], os.path.join(self.private, "app"))
        self.assertEqual(env["REX_APP_LOG_ROOT"], self.run_dir)
        self.assertEqual(env["TMPDIR"], os.path.join(self.private, "tmp"))
        for name, folder in (("XDG_CONFIG_HOME", "xdg/config"), ("XDG_DATA_HOME", "xdg/data"),
                             ("XDG_CACHE_HOME", "xdg/cache")):
            self.assertEqual(env[name], os.path.join(self.private, folder))
        self.assertEqual(env["HOME"], self.home)
        # The output of rexglue stays in the run folder; the console shows the summary only.
        self.assertNotIn("spam line", self.output)
        with open(os.path.join(self.run_dir, "vfs-dump.stdout")) as f:
            self.assertEqual(len(f.read().splitlines()), 500)
        self.assertLess(len(self.output.splitlines()), 60)
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "rexglue_001.log")))
        for name in os.listdir(self.run_dir):
            mode = stat.S_IMODE(os.lstat(os.path.join(self.run_dir, name)).st_mode)
            self.assertEqual(mode & 0o077, 0, name)
        summary = self.summary()
        self.assertIn("files: expected 5, found 5: match", summary)
        self.assertIn("directories (root not counted): expected 2, found 2: match", summary)
        self.assertIn(f"default.xex sha256: expected {sha256(self.tree['default.xex'])}",
                      summary)
        self.assertIn("ReXGlue nodes = files + directories + root: expected 8, found 8: match",
                      summary)
        self.assertIn("image unchanged (sha256 and identity, before and after)", summary)
        self.assertIn("names starting with a dot: 1 (counted)", summary)
        self.assertIn("this tool does not declare PB-1", summary)
        self.assertNotIn("DIFFERS", summary)
        cp3 = self.step(report, "cp3-before")
        self.assertEqual(cp3["facts"], {"matches": 1, "known_entry_listed": True,
                                        "other_matches": 0})
        mounts = self.step(report, "mounts-before")["facts"]
        self.assertEqual(mounts["mount_points_watched"], 2)
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        self.assertEqual(self.step(report, "preflight")["exit_code"], 0)
        self.assert_no_local_path(summary)
        self.assert_no_local_path(self.output)

    def test_preflight_declares_every_destination(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        self.report()
        # Every path written during the step is in a declared destination.
        declared = [os.path.join(self.private, name) for name in b1.DESTINATIONS]
        marker = os.path.join(self.run_dir, "b1.marker")
        since = os.stat(marker).st_mtime_ns
        written = [path for path in snapshot(self.private)
                   if os.lstat(path).st_mtime_ns > since]
        self.assertTrue(written)
        for path in written:
            self.assertTrue(any(path == d or b1.strictly_under(path, d) for d in declared),
                            path)

    def test_failed_dump_runs_postflight_and_deletes_nothing(self):
        self.plan["exit"] = 1
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        dump = self.step(report, "vfs-dump")
        self.assertEqual(dump["exit_code"], 1)
        self.assertIn("rexglue vfs dump exited with status 1", dump["findings"])
        self.assertEqual(self.assert_postflight_ran(report)["exit_code"], 0)
        self.assertTrue(os.path.exists(os.path.join(self.game, "media", "sub", "b.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "b1.marker")))
        self.assertIn("STOP: a finding stops B1", self.summary())

    def test_crash_runs_postflight(self):
        self.plan["signal"] = "KILL"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        dump = self.step(report, "vfs-dump")
        self.assertEqual(dump["exit_code"], -9)
        self.assertEqual(dump["facts"]["signal"], 9)
        self.assertIn("finding: rexglue vfs dump crashed (x1)", self.summary())
        self.assert_postflight_ran(report)
        self.step(report, "core-dumps")

    def test_time_out_runs_postflight(self):
        self.plan["sleep"] = 60
        self.assertEqual(self.tool("run", "--timeout", "1"), 1)
        report = self.report()
        self.assertIn("timed out", " ".join(self.step(report, "vfs-dump")["findings"]))
        self.assert_postflight_ran(report)

    def test_preflight_finding_stops_before_the_extraction(self):
        settings = os.path.join(self.private, "xdg", "config", "rexglue")
        os.makedirs(settings)
        with open(os.path.join(settings, "rexglue.toml"), "w") as f:
            f.write("# synthetic settings file\n")
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "preflight")["exit_code"], 1)
        self.assertEqual(self.step(report, "postflight")["status"], "skipped")
        self.assertFalse(os.path.exists(self.record))
        self.assertEqual(os.listdir(self.game), [])

    def test_guard_errors_are_findings(self):
        fake = os.path.join(self.records, "guard.py")
        with open(fake, "w") as f:
            f.write(FAKE_GUARD.format(real=GUARD))
        self.guard = fake
        self.extra_env["B1_FAKE_GUARD_PREFLIGHT"] = "3"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        pre = self.step(report, "preflight")
        self.assertEqual(pre["exit_code"], 3)
        self.assertIn("private_guard preflight exited with status 3", pre["findings"])
        self.assertFalse(os.path.exists(self.record))

        shutil.rmtree(self.run_dir)
        del self.extra_env["B1_FAKE_GUARD_PREFLIGHT"]
        self.extra_env["B1_FAKE_GUARD_POSTFLIGHT"] = "2"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        post = self.step(report, "postflight")
        self.assertEqual(post["exit_code"], 2)
        self.assertIn("private_guard postflight exited with status 2", post["findings"])
        self.assertTrue(os.path.exists(self.record))

    def test_nix_store_verify_failure_is_a_finding(self):
        self.extra_env["B1_FAKE_NIX_STATUS"] = "1"
        self.assertEqual(self.tool("run"), 1)
        post = self.step(self.report(), "postflight")
        self.assertIn("the SDK store path was modified", " ".join(post["findings"]))

    def test_writes_outside_the_private_folder_are_found(self):
        self.plan["write_outside"] = [
            os.path.join(self.home, ".config", "rexglue", "rexglue_001.log"),
            os.path.join(self.tmp, "stray"),
            os.path.join(self.persist_space, "stray"),
            os.path.join(self.repo, "stray")]
        self.assertEqual(self.tool("run"), 1)
        post = self.step(self.report(), "postflight")
        found = [text for text in post["findings"]
                 if text.startswith("file written outside the private folder: ")]
        # Local paths are named, in the local report only.
        self.assertEqual(sorted(found), sorted(
            "file written outside the private folder: " + path for path in (
                "$HOME/.config/rexglue/rexglue_001.log", os.path.join(self.tmp, "stray"),
                "$HOME/.local/share/persist b/stray", "$REPO/stray")))
        summary = self.summary()
        self.assertIn("finding: file written outside the private folder (x4)", summary)
        self.assertIn("finding: repository changed (x1)", summary)
        self.assert_no_local_path(summary)
        self.assertNotIn("stray", summary)

    def test_unreadable_mount_point_stops_with_a_finding(self):
        locked = os.path.join(self.home, "locked")
        os.mkdir(locked, 0o700)
        self.set_mounts([self.persist, locked])
        # Readable when prepare looks at it; unreadable when postflight searches it.
        self.plan["lock"] = [locked]
        self.assertEqual(self.tool("run"), 1)
        post = self.step(self.report(), "postflight")
        self.assertIn("incomplete check", " ".join(post["findings"]))
        self.assertIn("finding: incomplete check", self.summary())

    def test_new_mount_point_during_the_step_is_a_finding(self):
        extra = os.path.join(self.home, "late")
        os.mkdir(extra, 0o700)
        self.plan["add_mount"] = extra
        self.assertEqual(self.tool("run"), 1)
        mounts = self.step(self.report(), "mounts-after")
        self.assertEqual(mounts["facts"]["added"], 1)
        self.assertIn("finding: new mount point during the step (x1)", self.summary())

    def test_new_store_match_is_a_finding_and_the_known_entry_is_untouched(self):
        known_before = os.lstat(self.known)
        leak = os.path.join(self.store, "leak-source", "game", "default.xex")
        self.plan["write_outside"] = [leak]
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        after = self.step(report, "cp3-after")
        self.assertEqual(after["facts"]["new_matches"], 1)
        self.assertIn(f"CP-3 new match in the store: {leak}", after["findings"])
        self.assertTrue(after["facts"]["known_entry_listed"])
        known_after = os.lstat(self.known)
        self.assertEqual((known_before.st_size, known_before.st_mtime_ns, known_before.st_ino),
                         (known_after.st_size, known_after.st_mtime_ns, known_after.st_ino))

    def test_store_search_error_stops_before_preflight(self):
        locked = os.path.join(self.store, "locked")
        os.mkdir(locked, 0o000)
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "cp3-before")["exit_code"], 1)
        self.assertEqual([i["step"] for i in report["steps"] if i["step"] == "preflight"], [])
        self.assertFalse(os.path.exists(self.record))

    def test_recorded_core_dump_is_a_finding(self):
        self.extra_env["B1_FAKE_COREDUMPS"] = "Thu 2026-11-26 10:00:00 UTC 4242 1000 1000 SIGSEGV none /x 0"
        self.assertEqual(self.tool("run"), 1)
        step = self.step(self.report(), "core-dumps")
        self.assertEqual(step["facts"]["core_dumps_since_start"], 1)
        with open(self.trap) as f:
            calls = [line for line in f if line.startswith("coredumpctl")]
        self.assertEqual(len(calls), 1)

    def test_image_changed_during_the_step_is_a_finding(self):
        self.plan["modify_image"] = True
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertIn("the disc image changed during the step",
                      self.step(report, "image-after")["findings"])
        self.assertIn("image unchanged (sha256 and identity, before and after)", self.summary())
        self.assertIn("DIFFERS", self.summary())

    def test_count_and_hash_differences_are_findings(self):
        reference = reference_for(self.tree)
        reference["files"] = 49
        reference["directories"] = 8
        reference["modules"]["fifadllzf.xex"] = sha256("another module\n")
        self.write_reference(reference)
        self.assertEqual(self.tool("run"), 1)
        summary = self.summary()
        self.assertIn("files: expected 49, found 5: DIFFERS", summary)
        self.assertIn("directories (root not counted): expected 8, found 2: DIFFERS", summary)
        self.assertRegex(summary, r"fifadllzf\.xex sha256: expected [0-9a-f]{64}, found "
                                  r"[0-9a-f]{64}: DIFFERS")
        self.assertIn("default.xex sha256", summary)

    def test_absent_module_is_a_finding(self):
        del self.tree["fifadllzf.xex"]
        self.plan["tree"] = self.tree
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("found absent: DIFFERS", self.summary())

    def test_tree_anomalies_are_not_counted(self):
        self.plan["links"] = [["link-out", self.home], ["media/link-in", "a.txt"]]
        self.plan["fifos"] = ["media/pipe"]
        self.plan["hardlinks"] = [["media/a.txt", "media/a-again.txt"]]
        self.assertEqual(self.tool("run"), 1)
        pb1 = self.step(self.report(), "pb1-figures")
        self.assertEqual(pb1["facts"]["anomaly_kinds"],
                         {"symbolic link": 2, "special file": 1, "hard link": 2})
        self.assertEqual(pb1["facts"]["files"], 4)
        summary = self.summary()
        self.assertIn("anomaly: symbolic link (x2, not counted)", summary)
        self.assertNotIn("link-out", summary)

    def test_nodes_or_type_mismatch_is_a_finding(self):
        self.plan["nodes"] = 7
        self.plan["type"] = "STFS"
        self.assertEqual(self.tool("run"), 1)
        summary = self.summary()
        self.assertIn("ReXGlue nodes = files + directories + root: expected 8, found 7: "
                      "DIFFERS", summary)
        self.assertIn("ReXGlue container type: expected GDFX, found STFS: DIFFERS", summary)

    def test_missing_summary_block_is_a_finding(self):
        self.plan["block"] = False
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("found not found: DIFFERS", self.summary())

    def test_local_j0_report(self):
        with open(self.iso, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        j0 = os.path.join(self.logs, "j0-identification.json")
        with open(j0, "w") as f:
            json.dump({"source": {"kind": "image", "sha256": digest}}, f)
        self.assertEqual(self.tool("run", "--j0-report", j0), 0, self.output)
        self.assertIn("image sha256 = local J0 report", self.summary())
        for name in self.run_dirs():
            shutil.rmtree(name)
        for name in os.listdir(self.game):
            path = os.path.join(self.game, name)
            shutil.rmtree(path) if os.path.isdir(path) else os.unlink(path)
        with open(j0, "w") as f:
            json.dump({"source": {"kind": "image", "sha256": sha256("other image")}}, f)
        self.assertEqual(self.tool("run", "--j0-report", j0), 1)
        self.assertIn("PB-1 figure differs", self.summary())

    def test_second_run_is_refused(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        first = self.run_dirs()
        before = snapshot(self.game)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding: game/ is not empty", self.output)
        self.assertEqual(self.run_dirs(), first)
        self.assertEqual(snapshot(self.game), before)

    def test_rehearse_runs_the_controls_without_extraction(self):
        self.assertEqual(self.tool("rehearse"), 0, self.output)
        report = self.report()
        self.assertEqual(self.step(report, "vfs-dump")["status"], "skipped")
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        names = [item["step"] for item in report["steps"]]
        for absent in ("image-before", "image-after", "pb1-figures"):
            self.assertNotIn(absent, names)
        self.assertFalse(os.path.exists(self.record))
        self.assertEqual(os.listdir(self.game), [])

    def test_verify_reads_only(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        before = snapshot(self.w, skip=(self.records,))
        self.assertEqual(self.tool("verify"), 0, self.output)
        self.assertIn("files: expected 5, found 5: match", self.output)
        self.assertEqual(snapshot(self.w, skip=(self.records,)), before)
        self.assert_no_local_path(self.output)

    def test_nothing_is_sent_anywhere(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        with open(self.trap) as f:
            calls = f.read().splitlines()
        self.assertEqual([c for c in calls if c.startswith("UPLOAD")], [])
        git = [c.split() for c in calls if c.startswith("git ")]
        self.assertTrue(git)
        for call in git:
            words = call[1:]
            while words and words[0] in ("-C",):
                words = words[2:]
            self.assertIn(words[0], ("status", "rev-parse"), call)
        nix = [c for c in calls if c.startswith("nix ")]
        self.assertEqual(nix, [f"nix store verify {self.sdk}"])


class RootTest(unittest.TestCase):
    def test_root_is_refused_before_anything(self):
        with tempfile.TemporaryDirectory() as w, \
                mock.patch.object(b1.os, "geteuid", return_value=0), \
                mock.patch.object(b1, "Context") as context, \
                mock.patch("sys.stdout") as out:
            self.assertEqual(b1.main(["--private-dir", w, "run"]), 1)
            context.assert_not_called()
            text = "".join(call.args[0] for call in out.write.call_args_list)
            self.assertIn("running as root", text)
            self.assertEqual(os.listdir(w), [])


class UnitTest(unittest.TestCase):
    def test_reference_is_the_j0_report(self):
        with open(os.path.join(ROOT, "docs", "reports", "J0_IDENTIFICATION.md"),
                  encoding="utf-8") as f:
            text = f.read()
        self.assertIn(f"| Arborescence | {b1.J0_REFERENCE['files']} fichiers, "
                      f"{b1.J0_REFERENCE['directories']} dossiers |", text)
        line = next(l for l in text.splitlines() if l.startswith("| SHA-256 |"))
        hashes = re.findall(r"`([0-9a-f]{64})`", line)
        self.assertEqual(hashes, [b1.J0_REFERENCE["modules"]["default.xex"],
                                  b1.J0_REFERENCE["modules"]["fifadllzf.xex"]])

    def test_only_local_modules_are_imported(self):
        with open(TOOL, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module)
        self.assertEqual(names, {"argparse", "datetime", "hashlib", "importlib.util", "json",
                                 "os", "re", "resource", "stat", "subprocess", "sys", "time"})

    def test_findmnt_escapes(self):
        self.assertEqual(b1.unescape_mount(b"/home/u/My\\x20Files"), "/home/u/My Files")
        self.assertEqual(b1.unescape_mount(b"/a\\x5cb\\x0ac"), "/a\\b\nc")
        self.assertEqual(b1.unescape_mount(b"/caf\\xc3\\xa9"), "/café")

    def test_redactor_and_finding_kinds(self):
        redact = b1.Redactor("/home/u/private", "/home/u/dev/repo", "/home/u")
        self.assertEqual(redact("x /home/u/private/game y /home/u/dev/repo/a /home/u/.cache"),
                         "x $WC2010_PRIVATE_DIR/game y $REPO/a $HOME/.cache")
        self.assertEqual(b1.finding_kind("file written outside the private folder: $HOME/x"),
                         "file written outside the private folder")
        self.assertEqual(b1.finding_kind("the disc image changed during the step"),
                         "the disc image changed during the step")

    def test_survey_counts_below_the_root_with_hidden_names(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "a", ".b"))
            for rel in ("default.xex", "a/x", "a/.b/.y"):
                with open(os.path.join(root, rel), "w") as f:
                    f.write(rel)
            figures = b1.survey_tree(root, {"default.xex": "", "fifadllzf.xex": ""})
            self.assertEqual((figures["files"], figures["directories"],
                              figures["hidden_names"]), (3, 2, 2))
            self.assertEqual(figures["modules"]["fifadllzf.xex"], {"status": "absent"})
            self.assertEqual(figures["modules"]["default.xex"]["sha256"], sha256("default.xex"))

    def test_survey_two_names_for_one_module_is_an_anomaly(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("default.xex", "DEFAULT.XEX"):
                with open(os.path.join(root, name), "w") as f:
                    f.write(name)
            figures = b1.survey_tree(root, {"default.xex": ""})
            self.assertEqual(figures["modules"]["default.xex"]["status"], "ambiguous")
            self.assertIn(["several names for one module", "default.xex"],
                          figures["anomalies"])

    def test_survey_other_file_system_is_an_anomaly(self):
        """A real mount needs root: the device number of one folder is changed instead."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "mnt"))
            with open(os.path.join(root, "mnt", "x"), "w") as f:
                f.write("x")
            real_stat = os.stat

            def fake_stat(path, *args, **kwargs):
                st = real_stat(path, *args, **kwargs)
                if path == "mnt":
                    values = list(st)
                    values[stat.ST_DEV] = st.st_dev + 1
                    return os.stat_result(values)
                return st
            with mock.patch.object(b1.os, "stat", fake_stat):
                figures = b1.survey_tree(root, {})
            self.assertEqual(figures["anomalies"], [["other file system", "mnt"]])
            self.assertEqual((figures["files"], figures["directories"]), (0, 0))

    def test_game_mount_point_is_refused(self):
        """Same simulation for prepare: game/ on another file system than the private
        folder."""
        with tempfile.TemporaryDirectory() as private:
            os.mkdir(os.path.join(private, "game"))
            ctx = mock.Mock(private=private)
            real_lstat = os.lstat

            def fake_lstat(path):
                st = real_lstat(path)
                if path.endswith("/game"):
                    values = list(st)
                    values[stat.ST_DEV] = st.st_dev + 1
                    return os.stat_result(values)
                return st
            findings = []
            with mock.patch.object(b1.os, "lstat", fake_lstat):
                b1.check_real_folder(ctx, "game", findings, {})
            self.assertEqual(findings, ["mount point where a dedicated folder is expected: "
                                        "game/"])

    def test_watch_plan(self):
        with tempfile.TemporaryDirectory() as w:
            home = os.path.join(w, "home")
            private = os.path.join(home, "private")
            os.makedirs(os.path.join(private, "game"))
            os.makedirs(os.path.join(home, "p1", "p2"))
            with open(os.path.join(home, "f"), "w") as f:
                f.write("x")
            ctx = mock.Mock(private=private, guard=b1.load_guard(GUARD))
            ctx.tops.return_value = [home, os.path.join(w, "tmp")]
            targets = ["/", home, os.path.join(home, "p1"), os.path.join(home, "p1", "p2"),
                       os.path.join(home, "f"), os.path.join(private, "game"),
                       os.path.join(home, "absent"), os.path.join(w, "tmp", "t"),
                       w + "home-like"]
            relevant, watch, facts = b1.watch_plan(ctx, targets)
            self.assertEqual(watch, [os.path.join(home, "p1"), os.path.join(home, "p1", "p2"),
                                     os.path.join(home, "absent"),
                                     os.path.join(w, "tmp", "t")])
            self.assertEqual(facts, {"mount_points_watched": 4, "mount_points_not_folders": 1,
                                     "mount_points_in_private_folder": 1})
            self.assertEqual(len(relevant), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)

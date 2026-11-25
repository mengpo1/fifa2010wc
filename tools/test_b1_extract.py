#!/usr/bin/env python3
"""Tests of tools/b1_extract.py (J2 step B1, ticket #32, review of PR #33), on synthetic
folders only.

No disc image, no module and no game file is used. The "image" is a few lines of text.
`rexglue`, `findmnt`, `coredumpctl`, `nix` and, for most tests, `bwrap` are replaced by
small Python scripts that record how they are called. private_guard, find and git are the
real ones. The tool runs as a subprocess, as on the user's machine.

The fake bwrap checks the sandbox options and runs the command without confinement. It
answers the confinement probe and the synthetic crash with planned results, so that the
orchestration is tested everywhere. RealSandboxTest runs the real bubblewrap, when the
machine allows unprivileged user namespaces: the probe and a fake rexglue that tries to
write outside its destinations, in the real sandbox. Where it cannot start, the test checks
that the tool refuses to extract, and says which case ran.

The tool refuses root, so the tests that start it need an unprivileged user, as in the Nix
build sandbox. Not covered, because they need root or the user's machine: a real mount
point (device numbers and mount tables are synthetic here), a real systemd-coredump record,
a SIGSEGV of the real rexglue. docs/J2_B1_EXTRACTION.md section 8 lists these gaps.

Run: python3 -I tools/test_b1_extract.py, with TMPDIR outside /tmp for RealSandboxTest.
"""

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "b1_extract.py")
GUARD = os.path.join(HERE, "private_guard.py")
SUBFOLDERS = ("iso", "game", "xex", "generated", "cache", "saves", "logs")
SENTINEL = "SENTINEL"
PIPE = "|/nix/store/x-systemd/lib/systemd/systemd-coredump %P %u %g %s %t %c %h"
PROOF_DIR = "b1-rehearse-20000101T000000Z"


def load_tool():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("b1_extract", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b1 = load_tool()

# The fake rexglue. It records its arguments, working folder, umask, core size limit,
# environment and what it tried, into the run folder (REX_APP_LOG_ROOT), the only place it
# may write besides its destinations. Then it follows the plan of the test.
FAKE_REXGLUE = r'''
import errno, json, os, resource, signal, socket, sys, time
plan = json.loads(os.environ["B1_FAKE_PLAN_JSON"]) if "B1_FAKE_PLAN_JSON" in os.environ \
    else json.load(open(os.environ["B1_FAKE_PLAN"]))
mask = os.umask(0o077)
os.umask(mask)
keep = ("REX_", "TMPDIR", "XDG_", "NO_COLOR", "HOME", "WC2010_PRIVATE_DIR")
record = {"argv": sys.argv[1:], "cwd": os.getcwd(), "umask": mask,
          "core": list(resource.getrlimit(resource.RLIMIT_CORE)),
          "env": {k: v for k, v in os.environ.items() if k.startswith(keep)},
          "attempts": {}}
run_dir = os.environ["REX_APP_LOG_ROOT"]
def save():
    with open(os.path.join(run_dir, "fake-record.json"), "w") as f:
        json.dump(record, f)
save()
dest = sys.argv[-1]
files = dirs = 0
def write(folder, tree):
    global files, dirs
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
    sys.stderr.write("Extracting container:\n  Source: %s\n  Type:   %s\n  Nodes:  %s\n"
                     "  Bytes:  1\n\n" % (sys.argv[-2], plan.get("type", "GDFX"),
                                          plan.get("nodes", files + dirs + 1)))
with open(os.path.join(run_dir, "rexglue_001.log"), "w") as f:
    f.write("fake log\n")
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
if plan.get("modify_image"):
    image = sys.argv[-2]
    def action():
        os.chmod(image, 0o600)
        with open(image, "a") as f:
            f.write("changed\n")
        os.chmod(image, 0o400)
    attempt("image", action)
for path in plan.get("lock", []):
    attempt("lock", lambda: os.chmod(path, 0))
for path in plan.get("connect_sockets", []):
    def action(path=path):
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(path)
    attempt("socket " + path, action)
save()
if plan.get("sleep"):
    time.sleep(plan["sleep"])
if plan.get("signal"):
    os.kill(os.getpid(), getattr(signal, "SIG" + plan["signal"]))
sys.exit(plan.get("exit", 0))
'''

# The fake findmnt: the JSON table of the plan, another one from a given call on.
FAKE_FINDMNT = r'''
import json, os, sys
if sys.argv[1:] != ["--list", "--json", "--output", COLUMNS]:
    sys.exit(64)
plan = json.load(open(os.environ["B1_FAKE_PLAN"]))
counter = os.environ["B1_FAKE_MOUNT_CALLS"]
calls = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
open(counter, "w").write(str(calls))
if plan.get("findmnt_status"):
    sys.exit(plan["findmnt_status"])
if plan.get("findmnt_garbage"):
    print("{not json")
    sys.exit(0)
mounts = plan["mounts"]
if "mounts_after" in plan and calls >= plan.get("switch_at", 3):
    mounts = plan["mounts_after"]
print(json.dumps({"filesystems": mounts}))
'''

FAKE_COREDUMPCTL = r'''
import json, os, re, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("coredumpctl " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1:4] != ["--no-pager", "--json=short", "list"] or len(sys.argv) != 5 or \
        not re.fullmatch(r"--since=@[0-9]+", sys.argv[4]):
    sys.exit(64)
plan = json.load(open(os.environ["B1_FAKE_PLAN"]))
if plan.get("coredumpctl_status"):
    print("broken", file=sys.stderr)
    sys.exit(plan["coredumpctl_status"])
since = int(sys.argv[4].split("@")[1]) * 1000000
entries = list(plan.get("coredumps", []))
journal = os.environ["B1_FAKE_JOURNAL"]
if os.path.exists(journal):
    for line in open(journal):
        entry = json.loads(line)
        if entry["time"] >= since:
            entries.append(entry)
if entries:
    print(json.dumps(entries))
    sys.exit(0)
print("No coredumps found.", file=sys.stderr)
sys.exit(1)
'''

FAKE_NIX = r'''
import json, os, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("nix " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1:3] != ["store", "verify"] or len(sys.argv) != 4:
    sys.exit(64)
plan = json.load(open(os.environ["B1_FAKE_PLAN"]))
leak = plan.get("store_leak")
if leak:
    os.makedirs(os.path.dirname(leak), exist_ok=True)
    open(leak, "w").write("synthetic leak\n")
sys.exit(int(plan.get("nix_status", 0)))
'''

# The fake bwrap: the sandbox options must be the expected ones. The probe and the crash
# get planned answers; any other command runs as the child of this process, unconfined.
FAKE_BWRAP = r'''
import json, os, sys
args = sys.argv[1:]
# The synthetic crash runs with an empty environment: the records are found from here.
records = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0]))),
                       "records")
os.environ.setdefault("B1_FAKE_PLAN", os.path.join(records, "plan.json"))
os.environ.setdefault("B1_FAKE_BWRAP_LOG", os.path.join(records, "bwrap.log"))
os.environ.setdefault("B1_FAKE_JOURNAL", os.path.join(records, "journal.jsonl"))
plan = json.load(open(os.environ["B1_FAKE_PLAN"]))
with open(os.environ["B1_FAKE_BWRAP_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
if args == ["--version"]:
    print(plan.get("bwrap_version", "bubblewrap 0.12.0"))
    sys.exit(0)
if plan.get("bwrap_broken"):
    print("bwrap: setting up uid map: Permission denied", file=sys.stderr)
    sys.exit(1)
sep = args.index("--")
opts, cmd = args[:sep], args[sep + 1:]
head = ["--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent",
        "--new-session", "--tmpfs", "/"]
if opts[:len(head)] != head:
    sys.exit(64)
fd = int(opts[opts.index("--json-status-fd") + 1])
def status(doc):
    # The tool may be gone (a test kills it): the fake sandbox outlives it all the same.
    try:
        os.write(fd, (json.dumps(doc) + "\n").encode())
    except OSError:
        pass
if "_probe" in cmd:
    status({"child-pid": os.getpid()})
    print(json.dumps(plan["probe_results"]))
    status({"exit-code": 0})
    sys.exit(0)
if "_crash" in cmd:
    # The fake handler: a crash "reaches" it only with a core limit of 0, as the kernel
    # does with a pipe. The plan can break the handler, the kernel, the identification of
    # the program, the journal or the settings.
    import resource, time
    status({"child-pid": os.getpid()})
    soft = resource.getrlimit(resource.RLIMIT_CORE)[0]
    reaches = (soft == 0 and not plan.get("handler_silent")) or \
        (soft == 1 and plan.get("limit_one_ignored"))
    journal = os.environ["B1_FAKE_JOURNAL"]
    def entry(pid):
        return {"time": int(time.time() * 1000000), "pid": pid, "uid": os.getuid(),
                "sig": 11, "corefile": "none", "exe": os.path.realpath(sys.executable)}
    def record(item, delay=0):
        if delay and os.fork() == 0:
            time.sleep(delay)
        elif delay:
            return
        with open(journal, "a") as f:
            f.write(json.dumps(item) + "\n")
        if delay:
            os._exit(0)
    if plan.get("change_pattern") and soft == 1:
        with open(os.path.join(records, "core_pattern"), "a") as f:
            f.write(" changed\n")
    count = 0 if plan.get("crash_no_child") else 2 if plan.get("crash_two_children") else 1
    children = []
    for i in range(count):
        pid = os.fork()
        if pid == 0:
            if i == 0:
                sys.stdin.buffer.read(1)
            else:
                time.sleep(2)
            os._exit(0)
        children.append(pid)
    if not children:
        sys.stdin.buffer.read(1)
    for pid in children:
        os.waitpid(pid, 0)
    target = children[0] if children else os.getpid()
    if reaches:
        record(entry(target), plan.get("limit_one_delay", 0) if soft == 1
               else plan.get("journal_delay", 0))
    if plan.get("foreign_entry"):
        record(entry(target + 100000))
    status({"exit-code": 139})
    sys.exit(139)
os.chdir(opts[opts.index("--chdir") + 1])
pid = os.fork()
if pid == 0:
    os.execv(cmd[0], cmd)
status({"child-pid": os.getpid()})
_, st = os.waitpid(pid, 0)
code = os.waitstatus_to_exitcode(st)
code = 128 - code if code < 0 else code
status({"exit-code": code})
sys.exit(code)
'''

TRAP = r'''
import os, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("UPLOAD " + os.path.basename(sys.argv[0]) + " " + " ".join(sys.argv[1:]) + "\n")
sys.exit(1)
'''

FAKE_GIT = r'''
import os, sys
with open(os.environ["B1_FAKE_TRAP"], "a") as f:
    f.write("git " + " ".join(sys.argv[1:]) + "\n")
os.execv(REAL_GIT, [REAL_GIT] + sys.argv[1:])
'''

# A private_guard whose preflight or postflight misbehaves as planned; every other use is
# the real guard, also as a module.
FAKE_GUARD = r'''
import json, os, runpy, sys
REAL = {real!r}
if __name__ == "__main__":
    plan = json.load(open(os.environ["B1_FAKE_PLAN"]))
    for name in ("preflight", "postflight"):
        mode = plan.get("guard_" + name)
        if name in sys.argv and mode:
            if mode == "marker-and-finding":
                marker = sys.argv[sys.argv.index("--marker") + 1]
                open(marker, "w").write("marker\n")
                print("FINDING: settings file read before the environment: {sentinel}")
                sys.exit(1)
            if mode == "ok-without-marker":
                print("OK: ready")
                sys.exit(0)
            if mode == "sentinel":
                print("FINDING: file written outside the private folder: /{sentinel}/x")
                sys.exit(1)
            if mode in ("collide-cp3", "lock-image"):
                marker = sys.argv[sys.argv.index("--marker") + 1]
                if mode == "collide-cp3":
                    open(os.path.join(os.path.dirname(marker), "cp3-after.txt"), "w").close()
                else:
                    os.chmod(os.path.join(os.environ["WC2010_PRIVATE_DIR"], "iso",
                                          "fifa2010wc.iso"), 0)
                break
            if mode.startswith("slow-"):
                open(os.environ["B1_FAKE_TRAP"] + ".slow", "w").write("started")
                import time
                time.sleep(float(mode[5:]))
                break
            sys.exit(int(mode))
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
    return {"files": files, "directories": dirs,
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


def mount(id_, target, parent=1, majmin="0:30", fsroot="/", fstype="btrfs"):
    return {"id": id_, "uniq-id": None, "parent": parent, "maj:min": majmin,
            "fsroot": fsroot, "target": target, "fstype": fstype, "source": "/dev/fake",
            "vfs-options": "rw,relatime", "fs-options": "rw", "propagation": "shared"}


@unittest.skipIf(os.geteuid() == 0, "the tool refuses root: run the tests as an "
                                    "unprivileged user, as in the Nix build sandbox")
class Fixture(unittest.TestCase):
    """A synthetic machine: a home folder holding the private folder and the repository,
    a /tmp, a /dev/shm, a store with the SDK and the entry CP-3 already knows, the local J0
    report, and the fake commands. Every path holds the word SENTINEL, which must never
    reach a summary."""

    def setUp(self):
        self.w = tempfile.mkdtemp(prefix=f"b1-{SENTINEL}-")
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
        self.trap = os.path.join(self.records, "trap.log")
        self.bwrap_log = os.path.join(self.records, "bwrap.log")
        self.core_pattern = os.path.join(self.records, "core_pattern")
        self.suid = os.path.join(self.records, "suid_dumpable")
        self.set_core_pattern(PIPE)
        with open(self.suid, "w") as f:
            f.write("2\n")
        self.persist = os.path.join(self.home, "persist")
        self.persist_space = os.path.join(self.home, ".local", "share", "persist b")
        os.makedirs(self.persist)
        os.makedirs(self.persist_space)
        self.bound_file = os.path.join(self.home, ".bash_history")
        with open(self.bound_file, "w") as f:
            f.write("bound file\n")
        write_script(os.path.join(self.bin, "findmnt"), FAKE_FINDMNT,
                     COLUMNS=b1.MOUNT_COLUMNS)
        write_script(os.path.join(self.bin, "coredumpctl"), FAKE_COREDUMPCTL)
        write_script(os.path.join(self.bin, "nix"), FAKE_NIX)
        write_script(os.path.join(self.bin, "bwrap"), FAKE_BWRAP)
        write_script(os.path.join(self.bin, "git"), FAKE_GIT, REAL_GIT=git)
        for name in ("curl", "wget", "ssh", "scp", "rsync", "nc", "gh", "nix-store",
                     "nix-copy-closure"):
            write_script(os.path.join(self.bin, name), TRAP)
        self.guard = GUARD
        self.bwrap = os.path.join(self.bin, "bwrap")
        self.tree = dict(DEFAULT_TREE)
        self.plan = {"tree": self.tree, "mounts": self.default_mounts(),
                     "probe_results": [{"name": n, "ok": True, "detail": ""}
                                       for n in b1.PROBE_CHECKS]}
        self.reference = os.path.join(self.records, "reference.json")
        self.write_reference(reference_for(self.tree))
        self.write_j0_report()
        self.write_proof()
        self.extra_env = {}

    def cleanup(self):
        for root, dirs, files in os.walk(self.w):
            for name in dirs:
                try:
                    os.chmod(os.path.join(root, name), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.w, ignore_errors=True)

    def default_mounts(self):
        return [mount(1, "/", parent=0), mount(2, "/nix/store"), mount(3, "/proc",
                                                                        fstype="proc"),
                mount(10, self.home), mount(11, self.persist, parent=10),
                mount(12, self.persist_space, parent=10, fsroot="/@persist b"),
                mount(13, self.bound_file, parent=10)]

    def write_proof(self, state_changes=None, proved_at=None, **changes):
        """A completed rehearsal holding the proof of option B, as the tool writes it, for
        this boot, kernel, settings, tool, bubblewrap and Python; `changes` alter the
        identity it holds, `state_changes` its state."""
        folder = os.path.join(self.logs, PROOF_DIR)
        os.makedirs(folder, exist_ok=True)
        ctx = types.SimpleNamespace(args=types.SimpleNamespace(
            core_pattern_file=self.core_pattern, suid_dumpable_file=self.suid,
            bwrap=self.bwrap))
        identity = b1.proof_identity(ctx)
        identity.update(changes)
        state = {"tool_version": b1.TOOL_VERSION, "command": "rehearse",
                 "phase": "complete", "controls_clean": True, "evidence_incomplete": [],
                 "core_proof": dict(identity, result="validated",
                                    proved_at=time.time() if proved_at is None
                                    else proved_at)}
        state.update(state_changes or {})
        b1.write_state(folder, state)

    def remove_proof(self):
        shutil.rmtree(os.path.join(self.logs, PROOF_DIR), ignore_errors=True)

    def set_core_pattern(self, text):
        with open(self.core_pattern, "w") as f:
            f.write(text + "\n")

    def write_text(self, path, text):
        with open(path, "w") as f:
            f.write(text)

    def write_reference(self, reference):
        with open(self.reference, "w") as f:
            json.dump(reference, f)

    def write_j0_report(self, image_sha256=None, **changes):
        with open(self.iso, "rb") as f:
            data = f.read()
        reference = reference_for(self.tree)
        report = {"source": {"kind": "image", "size": len(data),
                             "sha256": image_sha256 or hashlib.sha256(data).hexdigest()},
                  "disc": {"files": reference["files"],
                           "directories": reference["directories"]},
                  "modules": [{"path": name, "sha256": value}
                              for name, value in reference["modules"].items()]}
        report.update(changes)
        self.j0 = os.path.join(self.logs, "j0-identification.json")
        if os.path.exists(self.j0):
            os.unlink(self.j0)
        with open(self.j0, "w") as f:
            json.dump(report, f)

    def env(self):
        env = {"PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
               "HOME": self.home, "WC2010_PRIVATE_DIR": self.private,
               "B1_FAKE_PLAN": os.path.join(self.records, "plan.json"),
               "B1_FAKE_TRAP": self.trap, "B1_FAKE_BWRAP_LOG": self.bwrap_log,
               "B1_FAKE_MOUNT_CALLS": os.path.join(self.records, "mount-calls"),
               "B1_FAKE_JOURNAL": os.path.join(self.records, "journal.jsonl"),
               "B1_FAKE_PLAN_JSON": json.dumps(self.plan),
               # Inherited ReXGlue settings that the tool must drop.
               "REX_LOG_LEVEL": "trace", "REX_LOG_FILE": "true"}
        env.update(self.extra_env)
        return env

    def argv(self, command, *extra):
        with open(os.path.join(self.records, "plan.json"), "w") as f:
            json.dump(self.plan, f)
        return [sys.executable, "-I", TOOL, "--repo", self.repo, "--sdk", self.sdk,
                "--guard", self.guard, "--store-dir", self.store, "--tmp-watch", self.tmp,
                "--shm-dir", self.shm, "--nix", os.path.join(self.bin, "nix"),
                "--findmnt", os.path.join(self.bin, "findmnt"),
                "--coredumpctl", os.path.join(self.bin, "coredumpctl"),
                "--bwrap", self.bwrap, "--reference", self.reference,
                "--core-pattern-file", self.core_pattern,
                "--suid-dumpable-file", self.suid, *extra, command]

    def tool(self, command, *extra, timeout=300):
        result = subprocess.run(self.argv(command, *extra), capture_output=True, text=True,
                                env=self.env(), cwd=self.w, timeout=timeout)
        self.output = result.stdout + result.stderr
        return result.returncode

    def start(self, command, *extra):
        return subprocess.Popen(self.argv(command, *extra), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=self.env(),
                                cwd=self.w)

    def run_dirs(self):
        return sorted(os.path.join(self.logs, name) for name in os.listdir(self.logs)
                      if name.startswith("b1-") and name != PROOF_DIR)

    def report(self, name="report.json"):
        dirs = self.run_dirs()
        self.assertEqual(len(dirs), 1, dirs)
        self.run_dir = dirs[0]
        with open(os.path.join(dirs[0], name)) as f:
            return json.load(f)

    def step(self, report, name):
        found = [item for item in report["steps"] if item["step"] == name]
        self.assertTrue(found, f"{name}: {[i['step'] for i in report['steps']]}")
        return found[-1]

    def codes(self, report):
        return [f["code"] for item in report["steps"] for f in item["findings"]]

    def summary(self, name="summary.txt"):
        with open(os.path.join(self.run_dirs()[0], name)) as f:
            return f.read()

    def recorded(self):
        for run_dir in self.run_dirs():
            path = os.path.join(run_dir, "fake-record.json")
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        return None

    def assert_shareable(self, text):
        """Nothing local in a summary or on the console: no path, no sentinel, no 64 digit
        hash."""
        self.assertNotIn(SENTINEL, text)
        for path in (self.private, self.home, self.w, self.repo):
            self.assertNotIn(path, text)
        self.assertIsNone(re.search(r"[0-9a-f]{64}", text), text)

    def use_fake_guard(self):
        fake = os.path.join(self.records, "guard.py")
        with open(fake, "w") as f:
            f.write(FAKE_GUARD.format(real=GUARD, sentinel=SENTINEL))
        self.guard = fake

    def clear_game(self):
        for name in os.listdir(self.game):
            path = os.path.join(self.game, name)
            shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) \
                else os.unlink(path)


class PrepareTest(Fixture):
    def test_prepare_passes_and_writes_nothing(self):
        before = snapshot(self.w, skip=(self.records,))
        self.assertEqual(self.tool("prepare"), 0, self.output)
        self.assertIn("outcome: no finding", self.output)
        self.assertIn("mount_points_watched 2", self.output)
        self.assertIn("mount_points_not_folders 1", self.output)
        self.assertEqual(snapshot(self.w, skip=(self.records,)), before)
        self.assertEqual(self.run_dirs(), [])
        self.assert_shareable(self.output)

    def test_image_problems(self):
        cases = (("writable", lambda: os.chmod(self.iso, 0o644), "image-writable"),
                 ("link", None, "image-invalid"), ("absent", None, "image-absent"))
        for name, change, code in cases:
            with self.subTest(name=name):
                if name == "link":
                    outside = os.path.join(self.w, "elsewhere.iso")
                    os.rename(self.iso, outside)
                    os.symlink(outside, self.iso)
                elif name == "absent":
                    os.unlink(self.iso)
                else:
                    change()
                self.assertEqual(self.tool("prepare"), 1)
                self.assertIn(f"finding {code} (x1)", self.output)

    def test_non_empty_game_folder_is_refused_and_left_alone(self):
        old = os.path.join(self.game, ".left-over")
        with open(old, "w") as f:
            f.write("kept\n")
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding game-not-empty", self.output)
        self.assertIn("nothing was started", self.output)
        self.assertEqual(self.run_dirs(), [])
        with open(old) as f:
            self.assertEqual(f.read(), "kept\n")

    def test_folder_links_and_xdg_components_are_refused(self):
        """R07: every component of the private folder, the XDG folders included."""
        for rel in ("game", "logs", "xdg/config", "app"):
            with self.subTest(rel=rel):
                path = os.path.join(self.private, rel)
                outside = os.path.join(self.w, "outside-" + rel.replace("/", "-"))
                os.makedirs(outside)
                if os.path.isdir(path):
                    os.rename(path, outside + "-old")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                os.symlink(outside, path)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding folder-invalid", self.output)
                self.assertEqual(os.listdir(outside), [])
                os.unlink(path)
                if os.path.isdir(outside + "-old"):
                    os.rename(outside + "-old", path)

    def test_socket_or_fifo_in_the_private_folder_is_refused(self):
        """Review v3 R02: the sandbox shows the private folder, so no socket or FIFO may
        lie in it."""
        os.mkfifo(os.path.join(self.private, "cache", "pipe"))
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding private-ipc (x1)", self.output)
        os.unlink(os.path.join(self.private, "cache", "pipe"))
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(os.path.join(self.private, "saves", "s.sock"))
            self.assertEqual(self.tool("run"), 1)
            self.assertIn("finding private-ipc (x1)", self.output)
            self.assertIsNone(self.recorded())

    def test_unsafe_parent_folder_is_refused(self):
        """R07: a parent of the private folder that others can change."""
        os.chmod(self.w, 0o777)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding ancestor-unsafe", self.output)

    def test_mount_point_inside_the_private_folder_is_refused(self):
        """R07: a bind mount on the same file system has the same device number; the mount
        table shows it."""
        self.plan["mounts"].append(mount(20, os.path.join(self.private, "xdg"), parent=10))
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding private-mount", self.output)
        self.assertEqual(self.run_dirs(), [])

    def test_dirty_repository_and_wrong_sdk_are_refused(self):
        with open(os.path.join(self.repo, "untracked"), "w") as f:
            f.write("x\n")
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding repo-invalid", self.output)
        os.unlink(os.path.join(self.repo, "untracked"))
        for sdk in (os.path.join(self.w, "fake-rexglue-sdk-0.11.0"),
                    os.path.join(self.store, "missing-rexglue-sdk-0.11.0"),
                    os.path.join(self.store, "fake-rexglue-sdk-0.10.0")):
            with self.subTest(sdk=sdk):
                self.sdk, keep = sdk, self.sdk
                self.assertEqual(self.tool("prepare"), 1)
                self.assertIn("finding sdk-invalid", self.output)
                self.sdk = keep

    def test_mount_table_errors_stop_everything(self):
        """R01: findmnt failing or giving garbage is a finding, and nothing starts."""
        for key in ("findmnt_status", "findmnt_garbage"):
            with self.subTest(key=key):
                self.plan[key] = 1
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding mounts-unavailable", self.output)
                self.assertEqual(self.run_dirs(), [])
                del self.plan[key]

    def test_absent_or_unreadable_mount_point_is_found(self):
        locked = os.path.join(self.home, "locked")
        os.mkdir(locked, 0o000)
        self.plan["mounts"] += [mount(30, locked, parent=10),
                                mount(31, os.path.join(self.home, "gone"), parent=10)]
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding watch-unusable (x2)", self.output)

    def test_core_settings_and_modes(self):
        """R03 option B: unreadable settings are a finding; a socket and a file are refused
        modes; a pipe needs the local proof of this boot."""
        os.unlink(self.suid)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding core-settings-unreadable", self.output)
        with open(self.suid, "w") as f:
            f.write("2\n")
        for pattern in ("@/run/systemd/coredump.socket", "core", "/var/crash/core.%p"):
            with self.subTest(pattern=pattern):
                self.set_core_pattern(pattern)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding core-mode-refused", self.output)
                self.assertEqual(self.run_dirs(), [])
                self.assertIsNone(self.recorded())
        self.set_core_pattern(PIPE)
        self.assertEqual(self.tool("prepare"), 0, self.output)
        self.assertIn("proof_found True", self.output)

    def test_run_needs_a_proof_of_this_boot_kernel_and_setting(self):
        """R03 option B and review v3 R03-B: no proof, or a proof of another boot, kernel,
        setting, suid_dumpable, protocol, tool version or file, bubblewrap or Python, a
        stale one, or one from a rehearsal that had findings, was interrupted or killed,
        was resumed or lacks evidence: run refuses and rexglue never starts."""
        cases = [("none", None, None), ("boot", {"boot_id": "another-boot"}, None),
                 ("kernel", {"kernel_release": "0.0.0"}, None),
                 ("pattern", {"core_pattern_sha256": "0" * 64}, None),
                 ("suid", {"suid_dumpable": "0"}, None),
                 ("protocol", {"protocol": b1.PROOF_PROTOCOL - 1}, None),
                 ("tool version", {"tool_version": b1.TOOL_VERSION - 1}, None),
                 ("tool file", {"tool_sha256": "1" * 64}, None),
                 ("bwrap", {"bwrap_sha256": "2" * 64}, None),
                 ("python", {"python": "/nix/store/other-python/bin/python3"}, None),
                 ("findings", {}, {"controls_clean": False}),
                 ("interrupted", {}, {"controls_clean": False}),
                 ("killed", {}, {"phase": "postflight"}),
                 ("resumed", {}, {"resumed": True, "resumes": 1}),
                 ("incomplete", {}, {"phase": "evidence-incomplete"}),
                 ("older tool", {}, {"tool_version": b1.TOOL_VERSION - 1})]
        for name, changes, state_changes in cases:
            with self.subTest(name=name):
                self.remove_proof()
                if changes is not None:
                    self.write_proof(state_changes=state_changes, **changes)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding core-proof-missing", self.output)
                self.assertIsNone(self.recorded())
                self.assertEqual([d for d in self.run_dirs()
                                  if "b1-run-" in d], [])
        with self.subTest(name="stale"):
            self.remove_proof()
            self.write_proof(proved_at=time.time() - b1.PROOF_MAX_AGE - 60)
            self.assertEqual(self.tool("run"), 1)
            self.assertIn("finding core-proof-missing", self.output)
        with self.subTest(name="setting changed after the proof"):
            self.remove_proof()
            self.write_proof()
            self.set_core_pattern(PIPE + " changed")
            self.assertEqual(self.tool("run"), 1)
            self.assertIn("finding core-proof-missing", self.output)

    def test_j0_report_gates(self):
        """R06: no report, an unreadable one, or one that differs from J0: no extraction."""
        cases = (("absent", lambda: os.unlink(self.j0), "j0-report-absent"),
                 ("garbage", lambda: self.write_text(self.j0, "{"), "j0-report-invalid"),
                 ("not an image", lambda: self.write_j0_report(
                     source={"kind": "folder"}), "j0-report-invalid"),
                 ("other counts", lambda: self.write_j0_report(
                     disc={"files": 48, "directories": 8}), "j0-report-mismatch"))
        for name, change, code in cases:
            with self.subTest(name=name):
                change()
                self.assertEqual(self.tool("run"), 1)
                self.assertIn(f"finding {code}", self.output)
                self.assertIsNone(self.recorded())
                self.assertEqual(self.run_dirs(), [])
                self.write_j0_report()


class RunTest(Fixture):
    def test_run_success(self):
        self.plan["stdout_lines"] = 500
        self.assertEqual(self.tool("run"), 0, self.output)
        report = self.report()
        self.assertEqual(self.codes(report), [], report)
        record = self.recorded()
        self.assertEqual(record["argv"], ["vfs", "dump", self.iso, self.game])
        self.assertEqual(record["cwd"], self.private)
        self.assertEqual(record["umask"], 0o077)
        self.assertEqual(record["core"], [1, 1])  # option B, the sandboxed process only
        env = record["env"]
        self.assertNotIn("REX_LOG_LEVEL", env)
        self.assertNotIn("REX_LOG_FILE", env)
        self.assertEqual(env["REX_APP_ROOT"], os.path.join(self.private, "app"))
        self.assertEqual(env["REX_APP_LOG_ROOT"], self.run_dir)
        self.assertEqual(env["TMPDIR"], os.path.join(self.private, "tmp"))
        with open(os.path.join(self.run_dir, "vfs-dump.stdout")) as f:
            self.assertEqual(len(f.read().splitlines()), 500)
        self.assertNotIn("spam line", self.output)
        self.assertLess(len(self.output.splitlines()), 70)
        summary = self.summary()
        for line in ("files: expected 5, found 5: match",
                     "directories (root not counted): expected 2, found 2: match",
                     "default.xex sha256 = reference: match",
                     "image unchanged (sha256 and identity, before and after): match",
                     "image sha256 = local J0 report, before and after: match",
                     "ReXGlue nodes = files + directories + root: expected 8, found 8: match",
                     "ReXGlue container type is GDFX: match",
                     "names starting with a dot: 1 (counted)",
                     "this tool does not declare PB-1"):
            self.assertIn(line, summary)
        self.assertNotIn("DIFFERS", summary)
        self.assert_shareable(summary)
        self.assert_shareable(self.output)
        state = b1.read_state(self.run_dir)
        self.assertEqual(state["phase"], "complete")
        # The extraction ran in the sandbox, with the expected options and binds.
        with open(self.bwrap_log) as f:
            calls = [json.loads(line) for line in f]
        dump = [c for c in calls if "vfs" in c][0]
        self.assertIn(["--ro-bind", self.private, self.private],
                      [dump[i:i + 3] for i in range(len(dump))])
        binds = {dump[i + 1] for i, a in enumerate(dump) if a == "--bind"}
        self.assertEqual(binds, {self.run_dir, self.game, os.path.join(self.private, "app"),
                                 os.path.join(self.private, "tmp")})

    def test_preflight_declares_the_destinations(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        self.report()
        with open(os.path.join(self.run_dir, "preflight.txt")) as f:
            self.assertIn("OK: ready", f.read())
        declared = [self.run_dir] + [os.path.join(self.private, n)
                                     for n in b1.SANDBOX_WRITABLE]
        since = os.stat(os.path.join(self.run_dir, "b1.marker")).st_mtime_ns
        written = [path for path in snapshot(self.private)
                   if os.lstat(path).st_mtime_ns > since]
        self.assertTrue(written)
        for path in written:
            self.assertTrue(any(b1.under_or_self(path, d) for d in declared), path)

    def test_failed_dump_runs_postflight_and_deletes_nothing(self):
        self.plan["exit"] = 1
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "vfs-dump")["exit_code"], 1)
        self.assertIn("dump-failed", self.codes(report))
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        self.assertTrue(os.path.exists(os.path.join(self.game, "media", "sub", "b.txt")))
        self.assertIn("STOP: a finding stops B1", self.summary())

    def test_crash_and_time_out_run_postflight(self):
        for key, value, code in (("signal", "KILL", "dump-crashed"),
                                 ("sleep", 60, "dump-timeout")):
            with self.subTest(key=key):
                self.plan[key] = value
                self.assertEqual(self.tool("run", "--timeout", "1"), 1)
                report = self.report()
                self.assertIn(code, self.codes(report))
                self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
                del self.plan[key]
                shutil.rmtree(self.run_dir)
                self.clear_game()

    def test_preflight_finding_stops_before_the_extraction(self):
        settings = os.path.join(self.private, "xdg", "config", "rexglue")
        os.makedirs(settings)
        with open(os.path.join(settings, "rexglue.toml"), "w") as f:
            f.write("# synthetic settings file\n")
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "preflight")["exit_code"], 1)
        self.assertEqual(self.step(report, "postflight")["status"], "skipped")
        self.assertIsNone(self.recorded())

    def test_marker_rules(self):
        """R05: no marker after a passing preflight is a finding; a marker always brings
        postflight, even after a finding."""
        self.use_fake_guard()
        self.plan["guard_preflight"] = "ok-without-marker"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertIn("preflight-no-marker", self.codes(report))
        self.assertIsNone(self.recorded())
        shutil.rmtree(self.run_dir)
        self.plan["guard_preflight"] = "marker-and-finding"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        self.assertEqual(self.step(report, "vfs-dump")["status"], "skipped")
        self.assertIsNone(self.recorded())

    def test_guard_errors_are_findings(self):
        self.use_fake_guard()
        self.plan["guard_preflight"] = "3"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "preflight")["exit_code"], 3)
        self.assertIn("guard-error", self.codes(report))
        shutil.rmtree(self.run_dir)
        del self.plan["guard_preflight"]
        self.plan["guard_postflight"] = "2"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertEqual(self.step(report, "postflight")["exit_code"], 2)
        self.assertIn("guard-error", self.codes(report))

    def test_writes_outside_the_private_folder_are_found(self):
        """With the fake bwrap nothing is confined: postflight must find every write."""
        self.plan["write_outside"] = [
            os.path.join(self.home, ".config", "rexglue", "rexglue_001.log"),
            os.path.join(self.tmp, "stray"), os.path.join(self.persist_space, "stray"),
            os.path.join(self.repo, "stray")]
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        codes = self.codes(report)
        self.assertEqual(codes.count("guard-written-outside"), 4)
        self.assertIn("guard-repository", codes)
        self.assert_shareable(self.summary())

    def test_unreadable_mount_point_stops_with_a_finding(self):
        locked = os.path.join(self.home, "locked")
        os.mkdir(locked, 0o700)
        self.plan["mounts"].append(mount(30, locked, parent=10))
        self.plan["lock"] = [locked]
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("guard-incomplete", self.codes(self.report()))

    def test_mount_identity_changes_are_findings(self):
        """R01: a mount replaced at the same path, a remount, a bind, a new and a vanished
        mount point are all findings, by identity and attributes, not only by path."""
        cases = {
            "replaced": lambda m: m.update({"id": 99}) if m["target"] == self.persist else 0,
            "remount": lambda m: m.update({"vfs-options": "ro"})
            if m["target"] == self.persist else 0,
            "bind": lambda m: m.update({"fsroot": "/other"})
            if m["target"] == self.persist else 0,
            "home parent": lambda m: m.update({"maj:min": "0:99"}) if m["target"] == "/"
            else 0,
        }
        for name, change in cases.items():
            with self.subTest(name=name):
                after = [dict(m) for m in self.default_mounts()]
                for m in after:
                    change(m)
                self.plan["mounts_after"] = after
                if os.path.exists(os.path.join(self.records, "mount-calls")):
                    os.unlink(os.path.join(self.records, "mount-calls"))
                self.assertEqual(self.tool("run"), 1)
                report = self.report()
                facts = self.step(report, "mounts-after")["facts"]
                self.assertEqual(facts["changed"], 1, facts)
                self.assertIn("mount-changed", self.codes(report))
                shutil.rmtree(self.run_dir)
                self.clear_game()
        after = self.default_mounts() + [mount(40, os.path.join(self.home, "late"),
                                               parent=10)]
        after = [m for m in after if m["target"] != self.persist]
        self.plan["mounts_after"] = after
        os.unlink(os.path.join(self.records, "mount-calls"))
        self.assertEqual(self.tool("run"), 1)
        facts = self.step(self.report(), "mounts-after")["facts"]
        self.assertEqual((facts["added"], facts["removed"]), (1, 1))

    def test_new_store_match_is_a_finding_and_the_known_entry_is_untouched(self):
        known_before = os.lstat(self.known)
        leak = os.path.join(self.store, "leak-source", "game", "default.xex")
        self.plan["store_leak"] = leak
        self.assertEqual(self.tool("run"), 1)
        after = self.step(self.report(), "cp3-after")
        self.assertEqual(after["facts"]["new_matches"], 1)
        self.assertTrue(after["facts"]["known_entry_listed"])
        known_after = os.lstat(self.known)
        self.assertEqual((known_before.st_size, known_before.st_mtime_ns,
                          known_before.st_ino),
                         (known_after.st_size, known_after.st_mtime_ns, known_after.st_ino))

    def test_store_search_error_stops_before_preflight(self):
        os.mkdir(os.path.join(self.store, "locked"), 0o000)
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertIn("cp3-search-failed", self.codes(report))
        self.assertFalse(any(i["step"] == "preflight" for i in report["steps"]))
        self.assertIsNone(self.recorded())

    def test_core_dumps_and_coredumpctl_errors(self):
        """R03: a recorded core dump and a coredumpctl failure are both findings."""
        self.plan["coredumps"] = [{"pid": 4242, "sig": 11, "corefile": "none",
                                   "exe": "/x"}]
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("core-dump-recorded", self.codes(self.report()))
        shutil.rmtree(self.run_dir)
        self.clear_game()
        del self.plan["coredumps"]
        self.plan["coredumpctl_status"] = 2
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("coredumpctl-failed", self.codes(self.report()))

    def test_image_changed_during_the_step_is_a_finding(self):
        self.plan["modify_image"] = True
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertIn("image-changed", self.codes(report))
        self.assertIn("j0-image-mismatch", self.codes(report))
        self.assertIn("image unchanged (sha256 and identity, before and after): DIFFERS",
                      self.summary())

    def test_image_hash_mismatch_with_the_j0_report_stops_before_rexglue(self):
        """R06: the report matches J0 but not this image: rexglue is never started."""
        self.write_j0_report(image_sha256=sha256("another image"))
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        self.assertIn("j0-image-mismatch", self.codes(report))
        self.assertFalse(any(i["step"] == "preflight" for i in report["steps"]))
        self.assertIsNone(self.recorded())
        self.assertNotIn(sha256("another image"), self.summary())

    def test_count_and_hash_differences_are_findings(self):
        reference = reference_for(self.tree)
        reference.update(files=49, directories=8)
        reference["modules"]["fifadllzf.xex"] = sha256("another module\n")
        self.write_reference(reference)
        self.write_j0_report(disc={"files": 49, "directories": 8},
                             modules=[{"path": k, "sha256": v}
                                      for k, v in reference["modules"].items()])
        self.assertEqual(self.tool("run"), 1)
        summary = self.summary()
        self.assertIn("files: expected 49, found 5: DIFFERS", summary)
        self.assertIn("directories (root not counted): expected 8, found 2: DIFFERS", summary)
        self.assertIn("fifadllzf.xex sha256 = reference: DIFFERS", summary)
        self.assert_shareable(summary)

    def test_tree_anomalies_are_not_counted(self):
        self.plan["links"] = [["link-out", self.home], ["media/link-in", "a.txt"]]
        self.plan["fifos"] = ["media/pipe"]
        self.plan["hardlinks"] = [["media/a.txt", "media/a-again.txt"]]
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        pb1 = self.step(report, "pb1-figures")
        self.assertEqual(pb1["facts"]["files"], 4)
        self.assertEqual(self.codes(report).count("tree-anomaly"), 5)
        self.assertNotIn("link-out", self.summary())

    def test_nodes_or_type_mismatch_is_a_finding(self):
        self.plan.update(nodes=7, type="STFS")
        self.assertEqual(self.tool("run"), 1)
        summary = self.summary()
        self.assertIn("ReXGlue nodes = files + directories + root: expected 8, found 7: "
                      "DIFFERS", summary)
        self.assertIn("ReXGlue container type is GDFX: DIFFERS", summary)

    def test_second_run_is_refused(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        first = self.run_dirs()
        before = snapshot(self.game)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding game-not-empty", self.output)
        self.assertEqual(self.run_dirs(), first)
        self.assertEqual(snapshot(self.game), before)

    def test_rehearse_runs_the_controls_without_extraction(self):
        self.assertEqual(self.tool("rehearse"), 0, self.output)
        report = self.report()
        self.assertEqual(self.step(report, "vfs-dump")["status"], "skipped")
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        self.assertEqual(self.step(report, "sandbox")["facts"]["probe_checks_passed"],
                         len(b1.PROBE_CHECKS))
        names = [item["step"] for item in report["steps"]]
        for absent in ("image-before", "image-after", "pb1-figures"):
            self.assertNotIn(absent, names)
        self.assertIsNone(self.recorded())
        self.assertEqual(os.listdir(self.game), [])

    def test_rehearse_acquires_the_proof_then_run_passes(self):
        """R03 option B, the local protocol: a control crash at limit 0 reaches the handler,
        the same crash at limit 1 does not; rehearse records the proof, and run accepts
        it. Neither synthetic crash counts as a core dump of the step."""
        self.remove_proof()
        self.assertEqual(self.tool("rehearse"), 1, self.output)
        report = self.report()
        probe = self.step(report, "core-probe")
        self.assertEqual(probe["facts"], {"control_signal": 11, "control_identified": True,
                                          "control_entry_found": True,
                                          "control_corefile": "none", "limit_one_signal": 11,
                                          "limit_one_identified": True,
                                          "limit_one_entry_found": False,
                                          "foreign_entries": 0, "settings_stable": True,
                                          "proof_acquired": True})
        self.assertEqual(self.codes(report), ["core-proof-missing"])
        self.assertEqual(self.step(report, "core-dumps")["facts"]["core_dumps_since_start"], 0)
        state = b1.read_state(self.run_dir)
        self.assertEqual(state["core_proof"]["result"], "validated")
        self.assertTrue(state["controls_clean"])
        self.assertIn("proof_acquired True", self.summary())
        rehearsal = self.run_dir
        time.sleep(1.1)
        self.assertEqual(self.tool("prepare"), 0, self.output)
        self.assertEqual(self.tool("run"), 0, self.output)
        runs = [d for d in self.run_dirs() if d != rehearsal]
        self.assertEqual(len(runs), 1)

    def test_proof_fails_when_the_handler_or_the_kernel_misbehaves(self):
        """R03 option B, negative cases, and review v3 R03-A and R03-B: no entry for the
        control crash, an entry for the crash at limit 1 (also late), coredumpctl failing,
        a program that cannot be identified (no pid, two pids), only a foreign entry, or
        settings changed during the probe: no proof, and run stays blocked."""
        cases = (("silent handler", {"handler_silent": True}),
                 ("limit 1 ignored", {"limit_one_ignored": True}),
                 ("limit 1 ignored, late entry", {"limit_one_ignored": True,
                                                  "journal_delay": 3}),
                 ("coredumpctl", {"coredumpctl_status": 2}),
                 ("no pid", {"crash_no_child": True}),
                 ("two pids", {"crash_two_children": True}),
                 ("foreign entry only", {"handler_silent": True, "foreign_entry": True}),
                 ("settings changed", {"change_pattern": True}))
        for name, plan in cases:
            with self.subTest(name=name):
                self.remove_proof()
                self.set_core_pattern(PIPE)
                saved = dict(self.plan)
                self.plan.update(plan)
                self.assertEqual(self.tool("rehearse"), 1)
                report = self.report()
                self.assertIn("core-probe-failed", self.codes(report))
                self.assertNotIn("core_proof", b1.read_state(self.run_dir))
                self.plan = saved
                shutil.rmtree(self.run_dir)
                self.set_core_pattern(PIPE)
                self.assertEqual(self.tool("run"), 1)
                self.assertIn("finding core-proof-missing", self.output)
                if os.path.exists(os.path.join(self.records, "journal.jsonl")):
                    os.unlink(os.path.join(self.records, "journal.jsonl"))

    def test_a_late_control_entry_is_still_found(self):
        """R03-A: a control entry that the journal writes late is found within the wait."""
        self.remove_proof()
        self.plan["journal_delay"] = 2
        self.assertEqual(self.tool("rehearse"), 1, self.output)
        self.assertEqual(self.codes(self.report()), ["core-proof-missing"])
        probe = self.step(self.report(), "core-probe")
        self.assertTrue(probe["facts"]["proof_acquired"])
        self.assertEqual(probe["facts"]["foreign_entries"], 0)
        self.assertIn("core_proof", b1.read_state(self.run_dir))

    def test_an_entry_at_limit_one_after_the_window_is_still_a_finding(self):
        """R03-A: the absence of an entry is only an observation over a window. An entry for
        the crash at limit 1 that comes after it is not left out by the after-check: the
        rehearsal has a finding, and its proof is not usable."""
        self.remove_proof()
        self.use_fake_guard()
        self.plan.update(limit_one_ignored=True, limit_one_delay=6.5,
                         guard_postflight="slow-4")
        self.assertEqual(self.tool("rehearse"), 1)
        report = self.report()
        self.assertFalse(self.step(report, "core-probe")["facts"]["limit_one_entry_found"])
        self.assertEqual(self.step(report, "core-dumps")["facts"],
                         {"core_dumps_since_start": 1})
        self.assertEqual(sorted(set(self.codes(report))),
                         ["core-dump-recorded", "core-proof-missing"])
        self.assertFalse(b1.read_state(self.run_dir)["controls_clean"])
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding core-proof-missing", self.output)
        self.assertIsNone(self.recorded())

    def test_a_foreign_entry_is_never_ours_and_still_stops_the_rehearsal(self):
        """R03-A: an entry of another process (same user and program, other pid) is not
        taken for the control; the probe holds, but the after-check counts it as a crash
        during B1, so the rehearsal has a finding and its proof is not usable."""
        self.remove_proof()
        self.plan["foreign_entry"] = True
        self.assertEqual(self.tool("rehearse"), 1)
        report = self.report()
        probe = self.step(report, "core-probe")
        self.assertTrue(probe["facts"]["proof_acquired"])
        self.assertGreaterEqual(probe["facts"]["foreign_entries"], 1)
        self.assertEqual(sorted(set(self.codes(report))),
                         ["core-dump-recorded", "core-proof-missing"])
        shutil.rmtree(os.path.join(self.logs, PROOF_DIR), ignore_errors=True)
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding core-proof-missing", self.output)
        self.assertIsNone(self.recorded())

    def test_sandbox_failures_stop_before_the_image_is_read(self):
        """R02: no bubblewrap, a too old one, one that cannot start, or a probe check that
        fails: no extraction, and the image is not read."""
        cases = (("version", {"bwrap_version": "bubblewrap 0.7.0"}, "sandbox-unavailable"),
                 ("broken", {"bwrap_broken": True}, "sandbox-unavailable"),
                 ("leak", {"probe_results": [{"name": n, "ok": n != "write-denied-home",
                                              "detail": ""} for n in b1.PROBE_CHECKS]},
                  "sandbox-probe-failed"))
        for name, plan, code in cases:
            with self.subTest(name=name):
                saved = dict(self.plan)
                self.plan.update(plan)
                self.assertEqual(self.tool("run"), 1)
                report = self.report()
                self.assertIn(code, self.codes(report))
                self.assertFalse(any(i["step"] == "image-before" for i in report["steps"]))
                self.assertIsNone(self.recorded())
                self.plan = saved
                shutil.rmtree(self.run_dir)
        # No bubblewrap: the proof is bound to it (R03-B), so run stops at the gate, and
        # rehearse cannot start the sandbox.
        self.bwrap = os.path.join(self.w, "no-such-bwrap")
        self.assertEqual(self.tool("run"), 1)
        self.assertIn("finding core-proof-missing", self.output)
        self.assertIsNone(self.recorded())
        self.assertEqual(self.tool("rehearse"), 1)
        self.assertIn("sandbox-unavailable", self.codes(self.report()))
        self.assertIsNone(self.recorded())

    def test_verify_reads_only(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        before = snapshot(self.w, skip=(self.records,))
        self.assertEqual(self.tool("verify"), 0, self.output)
        self.assertIn("files: expected 5, found 5: match", self.output)
        self.assertEqual(snapshot(self.w, skip=(self.records,)), before)
        self.assert_shareable(self.output)

    def test_nothing_is_sent_anywhere(self):
        self.assertEqual(self.tool("run"), 0, self.output)
        with open(self.trap) as f:
            calls = f.read().splitlines()
        self.assertEqual([c for c in calls if c.startswith("UPLOAD")], [])
        for call in (c.split() for c in calls if c.startswith("git ")):
            words = call[1:]
            while words and words[0] == "-C":
                words = words[2:]
            self.assertIn(words[0], ("status", "rev-parse"), call)
        self.assertEqual([c for c in calls if c.startswith("nix ")],
                         [f"nix store verify {self.sdk}"])

    def test_summary_holds_no_free_text(self):
        """R04: sentinels in every path, in a guard finding, in the summary block of rexglue
        and in mount targets: none reaches the summary or the console."""
        self.use_fake_guard()
        self.plan["guard_postflight"] = "sentinel"
        self.plan["type"] = SENTINEL
        self.plan["mounts"].append(mount(50, os.path.join(self.home, SENTINEL + " mnt"),
                                         parent=10))
        os.mkdir(os.path.join(self.home, SENTINEL + " mnt"))
        self.assertEqual(self.tool("run"), 1)
        summary = self.summary()
        self.assert_shareable(summary)
        self.assert_shareable(self.output)
        self.assertIn("finding guard-written-outside (x1)", summary)
        allowed = set(b1.FINDING_CODES)
        for code in re.findall(r"finding ([a-z0-9-]+) \(x", summary):
            self.assertIn(code, allowed)


class EvidenceTest(Fixture):
    def test_an_error_in_one_control_lets_the_others_run_and_resume_finishes(self):
        """Review v3 R05-A: a write error in cp3-after is a finding, the following controls
        still run, the state says evidence-incomplete, every command sees an incomplete run,
        and resume completes the evidence."""
        self.use_fake_guard()
        self.plan["guard_postflight"] = "collide-cp3"
        self.assertEqual(self.tool("run"), 1)
        report = self.report()
        steps = [item["step"] for item in report["steps"]]
        for name in ("private-tree-after", "image-after", "pb1-figures"):
            self.assertIn(name, steps)
        self.assertIn("evidence-incomplete", self.codes(report))
        state = b1.read_state(self.run_dir)
        self.assertEqual(state["phase"], "evidence-incomplete")
        self.assertEqual(state["evidence_incomplete"], ["cp3-after"])
        self.assertIn("finished", state)
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding incomplete-run", self.output)
        del self.plan["guard_postflight"]
        self.assertEqual(self.tool("resume", "--run-folder", os.path.basename(self.run_dir)), 1)
        state = b1.read_state(self.run_dir)
        self.assertEqual(state["phase"], "complete", state.get("evidence_incomplete"))
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "cp3-after-resume.txt")))
        self.tool("prepare")
        self.assertNotIn("finding incomplete-run", self.output)

    def test_an_unreadable_image_after_the_step_is_incomplete_evidence(self):
        """Review v3 R05-A: a read error is incomplete evidence, not a complete run; two
        resumes get their own files."""
        self.use_fake_guard()
        self.plan["guard_postflight"] = "lock-image"
        self.assertEqual(self.tool("run"), 1)
        state = b1.read_state(self.report() and self.run_dir)
        self.assertEqual(state["evidence_incomplete"], ["image-after"])
        name = os.path.basename(self.run_dir)
        self.assertEqual(self.tool("resume", "--run-folder", name), 1)
        self.assertEqual(b1.read_state(self.run_dir)["phase"], "evidence-incomplete")
        os.chmod(self.iso, 0o444)
        del self.plan["guard_postflight"]
        self.tool("resume", "--run-folder", name)
        self.assertEqual(b1.read_state(self.run_dir)["phase"], "complete")
        for suffix in ("-resume", "-resume-2"):
            self.assertTrue(os.path.exists(os.path.join(self.run_dir,
                                                        f"report{suffix}.json")))


class InterruptTest(Fixture):
    def wait_for_phase(self, phase, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            dirs = self.run_dirs()
            state = b1.read_state(dirs[0]) if dirs else None
            if state and state.get("phase") == phase:
                return state
            time.sleep(0.1)
        self.fail(f"phase {phase} not reached")

    def test_sigterm_and_repeated_signals_finish_the_controls(self):
        """R05: SIGTERM stops the extraction; a second signal does not stop the
        controls."""
        self.use_fake_guard()
        self.plan["guard_postflight"] = "slow-3"
        self.plan["sleep"] = 60
        proc = self.start("run")
        self.wait_for_phase("extracting")
        proc.send_signal(signal.SIGTERM)
        slow = self.trap + ".slow"
        deadline = time.monotonic() + 60
        while not os.path.exists(slow) and time.monotonic() < deadline:
            time.sleep(0.05)
        proc.send_signal(signal.SIGINT)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=120)
        self.assertEqual(proc.returncode, 1, out)
        report = self.report()
        self.assertIn("interrupted", self.codes(report))
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        self.assertEqual(self.step(report, "interrupted")["facts"]["signals"], 3)
        self.assertEqual(b1.read_state(self.run_dir)["phase"], "complete")

    def test_killed_supervisor_leaves_a_detectable_state_and_resume_finishes(self):
        """R05: after a SIGKILL of the tool, state.json shows the phase; prepare and run
        refuse; resume waits for the extraction to end, then runs the controls without
        starting it again and without deleting anything."""
        self.plan["sleep"] = 300
        proc = self.start("run")
        state = self.wait_for_phase("extracting")
        record_file = os.path.join(self.run_dirs()[0], "fake-record.json")
        for _ in range(100):  # the fake rexglue has started: the sandbox is up
            if os.path.exists(record_file):
                break
            time.sleep(0.05)
        proc.kill()
        proc.communicate()
        name = os.path.basename(self.run_dirs()[0])
        self.assertEqual(self.tool("prepare"), 1)
        self.assertIn("finding incomplete-run", self.output)
        self.assertEqual(self.tool("run"), 1)
        self.assertEqual(len(self.run_dirs()), 1)
        self.assertEqual(self.tool("resume", "--run-folder", name), 1)
        self.assertIn("finding still-running", self.output)
        os.kill(state["bwrap_pid"], signal.SIGKILL)
        for _ in range(100):
            if b1.process_start(state["bwrap_pid"]) is None:
                break
            time.sleep(0.05)
        record = self.recorded()
        for pid in self.fake_rexglue_pids():
            os.kill(pid, signal.SIGKILL)
        tree = snapshot(self.game)
        self.assertEqual(self.tool("resume", "--run-folder", name), 1, self.output)
        report = self.report("report-resume.json")
        self.assertIn("interrupted", self.codes(report))
        self.assertEqual(self.step(report, "postflight")["exit_code"], 0)
        self.assertEqual(self.recorded(), record)
        self.assertEqual(snapshot(self.game), tree)
        self.assertEqual(b1.read_state(self.run_dir)["phase"], "complete")
        self.assert_shareable(self.summary("summary-resume.txt"))
        self.tool("prepare")
        self.assertNotIn("finding incomplete-run", self.output)

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


def real_bwrap():
    """The real bubblewrap, and whether it can start a sandbox here."""
    path = os.environ.get("B1_REAL_BWRAP") or shutil.which("bwrap")
    if not path:
        return None, "bwrap not found"
    result = subprocess.run([path, "--unshare-all", "--unshare-user", "--die-with-parent",
                             "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                             "--", sys.executable, "-c", "pass"], capture_output=True,
                            text=True)
    if result.returncode != 0:
        return path, result.stderr.strip()[:200] or f"status {result.returncode}"
    return path, None


def say_mode(text):
    """Which case of RealSandboxTest ran: into B1_SANDBOX_MODE_FILE, else on stderr."""
    path = os.environ.get("B1_SANDBOX_MODE_FILE")
    if path:
        with open(path, "a") as f:
            f.write(text + "\n")
    else:
        print(text, file=sys.stderr)


class RealSandboxTest(Fixture):
    def setUp(self):
        super().setUp()
        self.real, self.reason = real_bwrap()
        # The sandbox shows an empty /tmp and runs only programs of the store.
        self.assertFalse(b1.under_or_self(self.w, "/tmp"),
                         "set TMPDIR outside /tmp for this test")
        self.assertTrue(os.path.realpath(sys.executable).startswith(b1.SANDBOX_STORE + "/"),
                        "run this test with a Python of /nix/store")

    def test_real_sandbox_confines_the_extraction(self):
        """R02 with the real bubblewrap: the probe passes, and a fake rexglue that writes
        outside its destinations, into the home folder, the private folder and the image, is
        refused by the sandbox. Where the sandbox cannot start, the tool must refuse."""
        if self.real is None:
            self.fail("bubblewrap is required for this test (B1_REAL_BWRAP or PATH)")
        self.bwrap = self.real
        if self.reason:
            say_mode(f"REAL SANDBOX: unavailable ({self.reason})")
            self.assertEqual(self.tool("rehearse"), 1)
            self.assertIn("sandbox-unavailable", self.codes(self.report()))
            self.assertIsNone(self.recorded())
            return
        say_mode("REAL SANDBOX: available")
        # No real crash here: a file mode is refused, so rehearse runs only the probe.
        self.set_core_pattern("core")
        self.assertEqual(self.tool("rehearse"), 1, self.output)
        report = self.report()
        self.assertEqual(self.codes(report), ["core-mode-refused"])
        sandbox = self.step(report, "sandbox")
        self.assertEqual(sandbox["facts"]["probe_failed_checks"], [], sandbox)
        self.assertEqual(sandbox["facts"]["probe_checks_passed"], len(b1.PROBE_CHECKS))
        shutil.rmtree(self.run_dir)
        self.set_core_pattern(PIPE)
        self.remove_proof()
        self.write_proof()
        targets = [os.path.join(self.home, "leak"), os.path.join(self.private, "leak"),
                   os.path.join(self.private, "iso", "leak"), os.path.join(self.repo, "leak")]
        self.plan["write_outside"] = targets
        self.plan["modify_image"] = True
        # Sockets of the machine the sandbox must not reach: one under the home folder, one
        # elsewhere, outside every folder of its positive list.
        outside = os.path.join(self.w, "outside")
        os.mkdir(outside)
        sockets = [os.path.join(self.home, "agent.sock"), os.path.join(outside, "srv.sock")]
        servers = []
        for path in sockets:
            server = socket.socket(socket.AF_UNIX)
            server.bind(path)
            server.listen(1)
            servers.append(server)
            self.addCleanup(server.close)
        self.plan["connect_sockets"] = sockets
        self.assertEqual(self.tool("run"), 0, self.output)
        record = self.recorded()
        for path in sockets:
            self.assertEqual(record["attempts"]["socket " + path], "ENOENT")
        for target in targets:
            self.assertEqual(record["attempts"][target], "EROFS")
            self.assertFalse(os.path.exists(target))
        self.assertIn(record["attempts"]["image"], ("EROFS", "EPERM", "EACCES"))
        self.assertEqual(record["core"], [1, 1])
        self.assertEqual(record["cwd"], self.private)
        self.assertIn("files: expected 5, found 5: match", self.summary())


class RootTest(unittest.TestCase):
    def test_root_is_refused_before_anything(self):
        with tempfile.TemporaryDirectory() as w, \
                mock.patch.object(b1.os, "geteuid", return_value=0), \
                mock.patch.object(b1, "Context") as context, \
                mock.patch("sys.stdout") as out:
            self.assertEqual(b1.main(["--private-dir", w, "run"]), 1)
            context.assert_not_called()
            text = "".join(call.args[0] for call in out.write.call_args_list)
            self.assertIn("never runs as root", text)
            self.assertEqual(os.listdir(w), [])


class UnitTest(unittest.TestCase):
    def test_reference_is_the_j0_report(self):
        with open(os.path.join(ROOT, "docs", "reports", "J0_IDENTIFICATION.md"),
                  encoding="utf-8") as f:
            text = f.read()
        self.assertIn(f"| Arborescence | {b1.J0_REFERENCE['files']} fichiers, "
                      f"{b1.J0_REFERENCE['directories']} dossiers |", text)
        line = next(line for line in text.splitlines() if line.startswith("| SHA-256 |"))
        self.assertEqual(re.findall(r"`([0-9a-f]{64})`", line),
                         [b1.J0_REFERENCE["modules"]["default.xex"],
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
        # socket serves only the confinement probe and its two local listeners.
        self.assertEqual(names, {"argparse", "datetime", "errno", "hashlib",
                                 "importlib.util", "json", "os", "re", "resource", "select",
                                 "shutil", "signal", "socket", "stat", "subprocess", "sys",
                                 "time"})

    def test_summary_codes_and_steps_are_fixed(self):
        for code in b1.FINDING_CODES:
            self.assertRegex(code, r"^[a-z0-9-]+$")
        for step in b1.SUMMARY_FACTS:
            self.assertIn(step, b1.STEP_NAMES)

    def test_summary_validators_reject_free_text(self):
        steps = b1.Steps(lambda text: text)
        steps.add("vfs-dump", "ok", facts={"type": SENTINEL, "nodes": "8", "signal": 99})
        steps.add("repository", "ok", facts={"repository_commit": SENTINEL})
        steps.add("image-before", "ok", facts={"sha256": "a" * 64})
        steps.add("sandbox", "ok", facts={"probe_failed_checks": [SENTINEL]})
        ctx = mock.Mock(reference=b1.J0_REFERENCE)
        text = b1.summary_text(ctx, steps, "run", 0)
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn("a" * 64, text)
        self.assertIn("type invalid", text)
        self.assertIn("probe_failed_checks invalid", text)

    def test_unknown_codes_become_internal_errors(self):
        steps = b1.Steps(lambda text: text)
        item = steps.add("check-dir", "ok", findings=[(SENTINEL, "x")])
        self.assertEqual(item["findings"][0]["code"], "internal-error")

    def test_compare_mounts(self):
        a = [mount(1, "/"), mount(10, "/home/u"), mount(11, "/home/u/p", parent=10)]
        self.assertEqual(b1.compare_mounts(a, a)[0], {"added": 0, "removed": 0, "changed": 0})
        stacked = a + [mount(12, "/home/u/p", parent=11)]
        self.assertEqual(b1.compare_mounts(a, stacked)[0]["changed"], 1)
        replaced = [dict(m) for m in a]
        replaced[2]["id"] = 77
        facts, findings = b1.compare_mounts(a, replaced)
        self.assertEqual(facts["changed"], 1)
        self.assertEqual(findings[0][0], "mount-changed")

    def test_mount_scope_and_plan(self):
        with tempfile.TemporaryDirectory() as w:
            home = os.path.join(w, "home")
            private = os.path.join(home, "private")
            os.makedirs(os.path.join(private, "game"))
            os.makedirs(os.path.join(home, "p1", "p2"))
            with open(os.path.join(home, "f"), "w") as f:
                f.write("x")
            ctx = mock.Mock(private=private, guard=b1.load_guard(GUARD))
            ctx.tops.return_value = [home, os.path.join(w, "tmp")]
            mounts = [mount(1, "/"), mount(2, w), mount(3, home), mount(4, home + "/p1"),
                      mount(5, home + "/p1/p2"), mount(6, home + "/f"),
                      mount(7, private), mount(8, private + "/game"),
                      mount(9, home + "/absent"), mount(10, w + "/tmp/t"),
                      mount(11, w + "home-like"), mount(12, "/proc")]
            relevant, watch, facts, findings = b1.mount_plan(ctx, mounts)
            self.assertEqual(watch, [home + "/absent", home + "/p1", home + "/p1/p2",
                                     w + "/tmp/t"])
            self.assertEqual(facts, {"mounts_in_scope": 10, "mount_points_watched": 4,
                                     "mount_points_not_folders": 1,
                                     "private_folder_is_mount": True})
            self.assertEqual([code for code, _ in findings], ["private-mount"])
            self.assertNotIn("/proc", [m["target"] for m in relevant])

    def test_mount_events(self):
        events = b1.MountEvents("/proc/self/mountinfo")
        self.assertIsNotNone(events.fd)
        self.assertFalse(events.changed())
        fake = mock.Mock()
        fake.poll.return_value = [(events.fd, b1.select.POLLPRI)]
        with mock.patch.object(b1.select, "poll", return_value=fake):
            self.assertTrue(events.changed())
        self.assertIsNone(b1.MountEvents("/nonexistent/mountinfo").changed())

    def test_redactor(self):
        redact = b1.Redactor("/home/u/private", "/home/u/dev/repo", "/home/u")
        self.assertEqual(redact("x /home/u/private/game y /home/u/dev/repo/a /home/u/.cache"),
                         "x $WC2010_PRIVATE_DIR/game y $REPO/a $HOME/.cache")

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

    def test_survey_other_file_system_is_an_anomaly(self):
        """A real mount needs root: the device number of one folder is changed instead."""
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "mnt"))
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

    def test_component_on_another_device_is_refused(self):
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
                b1.check_component(ctx, "game", findings)
            self.assertEqual([code for code, _ in findings], ["folder-mount"])

    def test_sandbox_options(self):
        """Review v3 R02: a positive list. An empty root, the store and the private folder
        read-only, the destinations writable, then the root read-only."""
        with tempfile.TemporaryDirectory() as private:
            ctx = mock.Mock(private=private, home=os.path.dirname(private), store=private)
            ctx.args.bwrap = "bwrap"
            argv = b1.sandbox_argv(ctx, private + "/logs/r", ["cmd"], 9)
            self.assertEqual(argv[:8], ["bwrap", "--unshare-all", "--unshare-user",
                                        "--disable-userns", "--die-with-parent",
                                        "--new-session", "--tmpfs", "/"])
            self.assertNotIn("--share-net", argv)
            self.assertNotIn("/", [argv[i + 1] for i, a in enumerate(argv)
                                   if a in ("--bind", "--ro-bind")])
            self.assertIn(["--ro-bind", "/nix/store", "/nix/store"],
                          [argv[i:i + 3] for i in range(len(argv))])
            binds = [argv[i + 1] for i, a in enumerate(argv) if a == "--bind"]
            self.assertEqual(binds, [private + "/logs/r"] +
                             [os.path.join(private, n) for n in b1.SANDBOX_WRITABLE])
            self.assertEqual(argv[argv.index("--remount-ro") + 1], "/")
            self.assertGreater(argv.index("--remount-ro"),
                               max(i for i, a in enumerate(argv) if a == "--bind"))
            self.assertEqual(argv[-3:], ["9", "--", "cmd"])

    def test_sandbox_blockers(self):
        """Python and the SDK must be in the store, the only programs of the positive list."""
        ctx = mock.Mock(store="/nix/store", sdk="/nix/store/x-rexglue-sdk-0.11.0")
        in_store = os.path.realpath(sys.executable).startswith("/nix/store/")
        self.assertEqual(b1.sandbox_blockers(ctx) == [], in_store)
        ctx.sdk = "/opt/rexglue-sdk-0.11.0"
        self.assertIn("sandbox-unavailable", [code for code, _ in b1.sandbox_blockers(ctx)])

    def test_core_limits(self):
        self.assertEqual(b1.EXTRACTION_CORE_LIMIT, (1, 1))
        self.assertEqual(b1.SUPERVISOR_CORE_LIMIT[0], 0)
        self.assertEqual(b1.SUPERVISOR_CORE_LIMIT[1], 1)

    def test_root_uids(self):
        uids = b1.root_uids()
        self.assertIn(0, uids)


if __name__ == "__main__":
    unittest.main(verbosity=2)

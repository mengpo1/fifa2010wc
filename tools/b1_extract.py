#!/usr/bin/env python3
"""Step B1 of the J2 plan (docs/J2_PLAN.md section 4.1, ticket #32): extract the disc tree
with `rexglue vfs dump` into the private folder, confined by bubblewrap, between the CP-3
and CP-4 controls, then compare the result with the J0 references for PB-1
(docs/J2_B1_EXTRACTION.md).

It is run by hand on the user's machine, after PB-0 (D-017). It never decodes a module, and
it never deletes, moves or overwrites anything. It never declares PB-1: the orchestrator
decides from the summary.

Commands:
  prepare   No extraction: writes nothing and does not read the disc image.
  rehearse  The controls of `run`, the confinement probe and, with a core_pattern pipe,
            the local proof of option B (D-018): a control crash at RLIMIT_CORE 0 reaches
            the handler, the same crash at 1 does not. No extraction; the image is not read.
  run       B1. Every gate must pass first, the proof of option B included, and the
            extraction runs in the sandbox with RLIMIT_CORE 1.
  verify    The PB-1 figures of the extracted tree, read only. Writes nothing.
  resume    The controls after the extraction, for a run whose supervisor stopped before
            the end (power loss, SIGKILL). It never starts the extraction again.

Every step gets a status and, for a command, its exit status. A check that cannot run is a
finding. A finding stops the step; it never deletes anything. rehearse and run write only
in a new folder, $WC2010_PRIVATE_DIR/logs/b1-<command>-<UTC time>:
- state.json: the phase reached, kept up to date, so that a stopped run is detectable;
- report.json: every step and finding, for local use only;
- summary.txt: only allowlisted fields and finding codes (no path, no free text, no hash
  of the image). Review it before sharing anything (CP-5);
- the outputs of private_guard, find, findmnt, coredumpctl, the probes and rexglue, and the
  ReXGlue log.
The console shows the summary only.

Exit status: 0 when every step passes (and, for run and verify, the PB-1 figures match),
1 on a finding, 2 on usage error. Only the Python standard library is used. Run it with
`python3 -I`.
"""

import argparse
import datetime
import errno
import hashlib
import importlib.util
import json
import os
import re
import resource
import select
import signal
import socket
import stat
import subprocess
import sys
import time

TOOL_VERSION = 3
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GUARD = os.path.join(HERE, "private_guard.py")
ISO_NAME = "fifa2010wc.iso"
SDK_SUFFIX = "-rexglue-sdk-0.11.0"
SDK_NAME_RE = re.compile(r"[0-9a-z]{32}-rexglue-sdk-0\.11\.0")
# PB-1 references (docs/reports/J0_IDENTIFICATION.md section 2). The J0 tool counts the
# entries below the root of the disc: the root folder is not one of the 8 folders.
J0_REFERENCE = {
    "source": "J0 report",
    "files": 49,
    "directories": 8,
    "modules": {
        "default.xex": "dce08ce39dd11a6f45c74064d8f6c181326de1999b86bbd4ddcaf0feaa6de287",
        "fifadllzf.xex": "788474d3ee970d1777bbaf2f2ef950e937dd56ac7fc57a5a9e5c0d2874736485",
    },
}
# The local J0 report, where docs/J0_ISO_IDENTIFICATION.md writes it.
DEFAULT_J0_REPORT = os.path.join("logs", "j0-identification.json")
# The folders of the step's environment (docs/J2_PHASE_B_CONTROLS.md section 2).
ENV_FOLDERS = (("TMPDIR", "tmp"), ("XDG_CONFIG_HOME", "xdg/config"),
               ("XDG_DATA_HOME", "xdg/data"), ("XDG_CACHE_HOME", "xdg/cache"),
               ("REX_APP_ROOT", "app"))
# Folders of the private folder checked component by component (R07).
PRIVATE_COMPONENTS = ("iso", "game", "logs", "tmp", "app", "xdg", "xdg/config",
                      "xdg/data", "xdg/cache")
# Folders the extraction may write, besides the run folder: bound writable in the sandbox
# and declared to preflight.
SANDBOX_WRITABLE = ("game", "app", "tmp")
# Host folders replaced by an empty tmpfs in the sandbox, when they exist: they hold the
# sockets of system services (D-Bus, journal, the Nix daemon) and shared temporary files.
SANDBOX_HIDDEN = ("/tmp", "/run", "/var/tmp", "/nix/var/nix/daemon-socket")
SANDBOX_TMPFS_BYTES = 16 << 20
HOME_TMPFS_BYTES = 1 << 20
BWRAP_MIN_VERSION = (0, 8, 0)
# Core dump limits (D-018, option B of docs/J2_B1_EXTRACTION.md section 6): the sandboxed
# extraction and the confinement probe run with exactly 1, which makes the kernel drop a
# crash before it starts the program of a core_pattern pipe; the supervisor keeps a soft
# limit of 0, which private_guard checks, and a hard limit of 1 so that it can give 1 to the
# sandbox; the control crash of the proof runs with 0.
EXTRACTION_CORE_LIMIT = (1, 1)
SUPERVISOR_CORE_LIMIT = (0, 1)
CONTROL_CORE_LIMIT = (0, 0)
PROOF_MIN_WAIT = 5
BOOT_ID_FILE = "/proc/sys/kernel/random/boot_id"
# The store entry already found by CP-3 before PB-0: never opened, never deleted.
KNOWN_STORE_ENTRY = "nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude"
DUMP_TIMEOUT = 7200
STOP_GRACE = 30
MOUNT_COLUMNS = ("ID,UNIQ-ID,PARENT,MAJ:MIN,FSROOT,TARGET,FSTYPE,SOURCE,VFS-OPTIONS,"
                 "FS-OPTIONS,PROPAGATION")
MOUNT_KEYS = ("id", "uniq-id", "parent", "maj:min", "fsroot", "target", "fstype", "source",
              "vfs-options", "fs-options", "propagation")
RUN_DIR_RE = re.compile(r"b1-(run|rehearse)-[0-9]{8}T[0-9]{6}Z")
STATE_FILE = "state.json"
# The summary block that `rexglue vfs dump` writes on stderr
# (src/rexglue/command/vfs_command.cpp). Nodes counts the root of the container too. The
# Source row names the image path, so it is never read here.
BLOCK_RE = re.compile(r"^\s+(Type|Nodes):\s+(\S+)\s*$", re.MULTILINE)

# Finding codes. Only these codes, and their counts, reach the summary; the detail of a
# finding, which can name a local path, stays in report.json.
FINDING_CODES = {
    "root": "the tool was started as root",
    "usage": "a required input is missing",
    "guard-check-dir": "private_guard check-dir found something (CP-1)",
    "guard-preflight": "private_guard preflight found something (CP-4)",
    "guard-postflight": "private_guard postflight found something (CP-4)",
    "guard-written-outside": "postflight: a file written outside the private folder",
    "guard-incomplete": "postflight: a place could not be searched in full",
    "guard-shm": "a guest memory object is left in /dev/shm",
    "guard-store-verify": "nix store verify of the SDK failed or did not run",
    "guard-repository": "the repository changed or git status failed",
    "guard-error": "private_guard did not run or exited with an unexpected status",
    "image-absent": "the disc image is absent",
    "image-invalid": "the disc image is a link, not a regular file or not canonical",
    "image-writable": "the disc image can be written",
    "image-unreadable": "the disc image cannot be read",
    "image-empty": "the disc image is empty",
    "image-changed": "the disc image changed during the step",
    "folder-missing": "a folder of the private folder is missing",
    "folder-invalid": "a folder of the private folder is a link or not a folder",
    "folder-owner": "a folder of the private folder belongs to another user",
    "folder-mount": "a folder of the private folder is a mount point",
    "folder-replaced": "a folder of the private folder was replaced during the step",
    "ancestor-unsafe": "a parent folder of the private folder can be changed by others",
    "game-not-empty": "game/ is not empty",
    "sdk-invalid": "the SDK is missing, outside the store or not ReXGlue 0.11.0",
    "sdk-changed": "the SDK changed after the controls started",
    "repo-invalid": "the repository is missing, not clean or git failed",
    "mounts-unavailable": "the mount table could not be read",
    "private-mount": "a mount point lies inside the private folder",
    "watch-unusable": "a watched place is absent or not readable",
    "mount-changed": "a mount in scope appeared, disappeared or changed",
    "mount-events": "the mount table changed during the step",
    "core-settings-unreadable": "the core dump settings could not be read",
    "core-mode-refused": "core dumps go to a socket or a file: not a mode validated by D-018",
    "core-proof-missing": "no local proof, for this boot, kernel and setting, that a crash at "
                          "limit 1 reaches no handler (run rehearse)",
    "core-changed": "the core dump setting or the kernel changed since the proof",
    "core-dump-recorded": "a core dump was recorded since the start",
    "coredumpctl-failed": "coredumpctl failed or gave an unreadable answer",
    "core-probe-failed": "the synthetic crashes did not prove that limit 1 reaches no "
                         "handler",
    "sandbox-unavailable": "bubblewrap is missing, too old or cannot start",
    "sandbox-probe-failed": "the confinement probe found a check that failed",
    "j0-report-absent": "no local J0 report: B1 requires it (D-018)",
    "j0-report-invalid": "the local J0 report is unreadable or not an image report",
    "j0-report-mismatch": "the local J0 report differs from the J0 references",
    "j0-image-mismatch": "the image hash differs from the local J0 report",
    "incomplete-run": "an earlier run or rehearsal did not finish its controls",
    "still-running": "the extraction of the run to resume may still be running",
    "cp3-search-failed": "a CP-3 search did not run in full",
    "cp3-new-match": "CP-3 found a new match in the store",
    "preflight-no-marker": "preflight passed but wrote no marker",
    "dump-failed": "rexglue vfs dump exited with a non-zero status",
    "dump-crashed": "rexglue vfs dump was killed by a signal",
    "dump-timeout": "rexglue vfs dump timed out and was stopped",
    "dump-not-started": "the sandboxed extraction did not start",
    "interrupted": "the step was interrupted",
    "internal-error": "an unexpected error in the tool",
    "pb1-differs": "a PB-1 figure differs from the reference",
    "tree-anomaly": "an entry of the extracted tree is a link, special or elsewhere",
}
# Findings that forbid only the extraction: rehearse records them and goes on.
EXTRACTION_GATES = {"core-mode-refused", "core-proof-missing", "j0-report-absent",
                    "j0-report-invalid", "j0-report-mismatch"}
# private_guard finding lines, mapped to codes by their first words.
GUARD_PREFIXES = (
    ("file written outside the private folder", "guard-written-outside"),
    ("incomplete check", "guard-incomplete"),
    ("guest memory object left", "guard-shm"),
    ("the SDK store path was modified", "guard-store-verify"),
    ("cannot run nix store verify", "guard-store-verify"),
    ("cannot run", "guard-error"),
    ("repository changed", "guard-repository"),
    ("git status failed", "guard-repository"),
)
# Checks of the confinement probe, in order. Their names are the only probe output that
# reaches the summary.
PROBE_CHECKS = (
    "write-denied-home", "write-denied-private-root", "write-denied-iso",
    "write-denied-store", "write-denied-repo", "write-allowed-run-folder",
    "writable-game", "writable-app", "writable-tmp", "image-read-only",
    "tmp-private-empty", "run-hidden", "nix-daemon-socket-hidden", "home-hidden",
    "net-loopback-only",
    "net-tcp-host-unreachable", "net-tcp-remote-unreachable", "net-udp-unreachable",
    "net-abstract-unix-isolated", "userns-disabled", "core-limit-one", "no-capabilities",
    "pid-isolated",
)
STEP_NAMES = (
    "check-dir", "incomplete-runs", "image", "folders", "private-tree", "sdk",
    "repository", "mounts", "watched-places", "core-settings", "j0-report", "sandbox",
    "core-probe", "mounts-before", "image-before", "cp3-before", "preflight",
    "before-extraction", "vfs-dump", "postflight", "mounts-after", "core-dumps",
    "cp3-after", "image-after", "private-tree-after", "pb1-figures", "interrupted",
    "internal-error", "resume",
)


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10 ** 15


def _bool(value):
    return isinstance(value, bool)


def _pattern(regex):
    compiled = re.compile(regex)
    return lambda value: isinstance(value, str) and compiled.fullmatch(value) is not None


def _enum(*values):
    return lambda value: value in values


def _names(allowed):
    return lambda value: isinstance(value, list) and all(v in allowed for v in value)


MODE = _pattern(r"0[0-7]{3}")
STAMP = _pattern(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
COMMIT = _pattern(r"[0-9a-f]{40}")
SIGNAL_NUMBER = lambda value: _int(value) and 1 <= value <= 64  # noqa: E731
COREFILE = _enum("none", "present", "missing", "journal", "truncated", "inaccessible",
                 "error", "unknown")
# The only facts printed in the summary: step, fact, validator. Anything else, or a value
# that fails its validator, stays in report.json.
SUMMARY_FACTS = {
    "incomplete-runs": {"incomplete_runs": _int},
    "image": {"image_size": _int, "image_mode": MODE, "image_hard_links": _int},
    "folders": {"game_entries": _int},
    "private-tree": {"ancestors_checked": _int, "components_checked": _int},
    "sdk": {"sdk_is_0_11_0": _bool, "sdk_registered": STAMP},
    "repository": {"repository_changes": _int, "repository_commit": COMMIT},
    "mounts": {"mounts_in_scope": _int, "mount_points_watched": _int,
               "mount_points_not_folders": _int, "private_folder_is_mount": _bool},
    "watched-places": {"places_checked": _int},
    "core-settings": {"core_pattern_kind": _enum("file", "pipe", "socket"),
                      "core_handler": _enum("systemd-coredump", "other", "none"),
                      "suid_dumpable": _enum("0", "1", "2"), "proof_found": _bool},
    "j0-report": {"report_present": _bool, "report_matches_j0": _bool},
    "sandbox": {"bwrap_version_ok": _bool, "probe_checks": _int,
                "probe_checks_passed": _int, "probe_failed_checks": _names(PROBE_CHECKS)},
    "core-probe": {"control_signal": SIGNAL_NUMBER, "control_entry_found": _bool,
                   "control_corefile": COREFILE, "limit_one_signal": SIGNAL_NUMBER,
                   "limit_one_entry_found": _bool, "proof_acquired": _bool},
    "mounts-before": {"mounts_in_scope": _int, "mount_points_watched": _int},
    "image-before": {"image_matches_j0_report": _bool},
    "cp3-before": {"matches": _int, "known_entry_listed": _bool, "other_matches": _int},
    "vfs-dump": {"signal": SIGNAL_NUMBER, "type": _enum("GDFX", "STFS", "SVOD"),
                 "nodes": _int},
    "postflight": {"excluded_systemd_folders": _int},
    "mounts-after": {"added": _int, "removed": _int, "changed": _int,
                     "mount_events": _bool},
    "core-dumps": {"core_dumps_since_start": _int},
    "cp3-after": {"matches": _int, "known_entry_listed": _bool, "other_matches": _int,
                  "new_matches": _int, "gone_matches": _int},
    "image-after": {"image_unchanged": _bool, "image_matches_j0_report": _bool},
    "private-tree-after": {"replaced": _int},
    "pb1-figures": {"files": _int, "directories": _int, "hidden_names": _int,
                    "anomalies": _int},
    "interrupted": {"signals": _int},
}
STATUSES = ("ok", "finding", "skipped")


class UsageError(Exception):
    pass


class Interrupted(Exception):
    pass


def load_guard(guard_path):
    """private_guard as a module, for its path helpers. No bytecode is written next to it."""
    sys.dont_write_bytecode = True
    if not os.path.isfile(guard_path):
        raise UsageError("cannot load private_guard (--guard)")
    spec = importlib.util.spec_from_file_location("private_guard", guard_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc_stamp(seconds=None):
    moment = datetime.datetime.fromtimestamp(time.time() if seconds is None else seconds,
                                             datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def strictly_under(path, top):
    try:
        return path != top and os.path.commonpath([path, top]) == top
    except ValueError:
        return False


def under_or_self(path, top):
    return path == top or strictly_under(path, top)


class Redactor:
    """Replaces the private folder, the repository and the home folder by their names in
    the details of report.json, for a readable local report."""

    def __init__(self, private, repo, home):
        pairs = []
        for value, name in ((private, "$WC2010_PRIVATE_DIR"), (repo, "$REPO"),
                            (home, "$HOME")):
            if value:
                for form in {value, os.path.realpath(value)}:
                    form = form.rstrip("/")
                    if form:
                        pairs.append((form, name))
        self.pairs = sorted(pairs, key=lambda pair: -len(pair[0]))

    def __call__(self, text):
        for value, name in self.pairs:
            text = text.replace(value, name)
        return text


def write_new(path, data):
    """Creates `path` with mode 0600; never overwrites and never follows a link."""
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogateescape")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600)
    with open(fd, "wb") as f:
        f.write(data)


def write_state(run_dir, state):
    """state.json, replaced atomically: the only file of the run folder that changes."""
    tmp = os.path.join(run_dir, STATE_FILE + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(run_dir, STATE_FILE))


def read_state(run_dir):
    try:
        with open(os.path.join(run_dir, STATE_FILE), encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else None
    except (OSError, ValueError):
        return None


def run_capture(argv, env=None, cwd=None, timeout=600, stdin=None):
    """Runs argv in its own session and returns (exit_code, stdout, stderr, error).
    exit_code is None, with an error text, when the command could not run or timed out."""
    try:
        result = subprocess.run(argv, capture_output=True, env=env, cwd=cwd,
                                timeout=timeout,
                                stdin=subprocess.DEVNULL if stdin is None else stdin,
                                start_new_session=True)
    except FileNotFoundError:
        return None, b"", b"", f"command not found: {os.path.basename(argv[0])}"
    except subprocess.TimeoutExpired:
        return None, b"", b"", f"timed out after {timeout} s: {os.path.basename(argv[0])}"
    except OSError as exc:
        return None, b"", b"", f"cannot run {os.path.basename(argv[0])} ({exc.strerror})"
    return result.returncode, result.stdout, result.stderr, None


def process_start(pid):
    """The start time of a process, from /proc/<pid>/stat, or None if it does not exist."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


# --- steps and findings ------------------------------------------------------------------

class Steps:
    def __init__(self, redact):
        self.items = []
        self.redact = redact

    def add(self, name, status, exit_code=None, facts=None, findings=(), notes=(),
            output=None, duration=None):
        """`findings` holds (code, detail) pairs. A step with a finding is a finding."""
        assert name in STEP_NAMES, name
        item = {"step": name, "status": status}
        if exit_code is not None:
            item["exit_code"] = exit_code
        if duration is not None:
            item["seconds"] = round(duration, 1)
        item["facts"] = dict(facts or {})
        item["findings"] = []
        for code, detail in findings:
            if code not in FINDING_CODES:
                detail, code = f"unknown code {code}: {detail}", "internal-error"
            item["findings"].append({"code": code, "detail": self.redact(str(detail))})
        item["notes"] = [self.redact(str(text)) for text in notes]
        if output:
            item["output"] = output
        if item["findings"] and status == "ok":
            item["status"] = "finding"
        self.items.append(item)
        return item

    def codes(self):
        return [f["code"] for item in self.items for f in item["findings"]]

    def blocking(self, extract=True):
        """True when a finding stops the step. For a rehearsal, the gates that only forbid
        the extraction do not stop it."""
        return any(code not in EXTRACTION_GATES or extract for code in self.codes())

    def has_findings(self):
        return bool(self.codes())

    def get(self, name):
        for item in self.items:
            if item["step"] == name:
                return item
        return None


class Context:
    def __init__(self, args):
        self.args = args
        if not args.private_dir:
            raise UsageError("WC2010_PRIVATE_DIR is not set (or give --private-dir)")
        if not os.path.isabs(args.private_dir):
            raise UsageError("the private folder must be an absolute path")
        self.private = os.path.realpath(args.private_dir)
        self.home = os.path.realpath(os.path.expanduser("~"))
        self.repo = os.path.realpath(args.repo) if args.repo else None
        self.guard_path = args.guard
        self.guard = load_guard(args.guard)
        self.sdk = os.path.normpath(args.sdk) if args.sdk else None
        self.store = os.path.normpath(args.store_dir)
        self.tmp_watch = os.path.normpath(args.tmp_watch)
        self.redact = Redactor(self.private, self.repo, self.home)
        self.iso = os.path.join(self.private, "iso", ISO_NAME)
        self.game = os.path.join(self.private, "game")
        self.logs = os.path.join(self.private, "logs")
        self.j0_report = (os.path.abspath(args.j0_report) if args.j0_report
                          else os.path.join(self.private, DEFAULT_J0_REPORT))
        self.reference = J0_REFERENCE
        if args.reference:
            # Test references only. The summary says so, whatever the file claims.
            try:
                with open(args.reference, encoding="utf-8") as f:
                    reference = json.load(f)
                self.reference = {"files": int(reference["files"]),
                                  "directories": int(reference["directories"]),
                                  "modules": {str(k): str(v) for k, v in
                                              dict(reference["modules"]).items()},
                                  "source": "--reference file, not the J0 report"}
            except (OSError, ValueError, KeyError, TypeError):
                raise UsageError("unreadable --reference file")

    def guard_cmd(self, *rest):
        cmd = [sys.executable, "-I", self.guard_path, "--private-dir", self.private]
        if self.repo:
            cmd += ["--repo", self.repo]
        cmd += ["--git", self.args.git]
        return cmd + list(rest)

    def tops(self):
        """The places postflight searches: the home folder, /tmp and the repository."""
        tops = [self.home, self.tmp_watch]
        if self.repo:
            tops.append(self.repo)
        return tops


# --- interruptions -----------------------------------------------------------------------

class Signals:
    """SIGINT, SIGTERM and SIGHUP. Before the marker and during the extraction, the first
    one interrupts the step. Once the controls after the marker run, signals are only
    counted: the controls finish. A SIGKILL of this process cannot be handled; state.json
    then shows an incomplete run, and `resume` finishes its controls."""

    def __init__(self):
        self.count = 0
        self.defer = False
        self.previous = {}

    def install(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            self.previous[sig] = signal.signal(sig, self._handle)

    def _handle(self, signum, frame):
        self.count += 1
        if not self.defer and self.count == 1:
            raise Interrupted()


SIGNALS = Signals()


# --- prepare: the private folder ----------------------------------------------------------

def check_component(ctx, rel, findings, required=True):
    """A folder of the private folder: a real folder, not a link or a mount point (by
    device and by the mount table), owned by the user. Returns its (device, inode)."""
    path = os.path.join(ctx.private, rel)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        if required:
            findings.append(("folder-missing", f"missing folder: {rel}/"))
        return None
    except OSError as exc:
        findings.append(("folder-invalid", f"cannot read the metadata of {rel}/ "
                                           f"({exc.strerror})"))
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        findings.append(("folder-invalid", f"not a real folder: {rel}/"))
        return None
    if st.st_dev != os.lstat(ctx.private).st_dev:
        findings.append(("folder-mount", f"another file system: {rel}/"))
    if st.st_uid != os.geteuid():
        findings.append(("folder-owner", f"folder of another user: {rel}/"))
    return [st.st_dev, st.st_ino]


def root_uids():
    """uid 0, and the overflow uid when uid 0 is not mapped in this user namespace: there,
    as in the Nix build sandbox, files of root appear as owned by the overflow uid. In the
    initial namespace of the user's machine, uid 0 is mapped and only 0 counts."""
    uids = {0}
    try:
        with open("/proc/self/uid_map", encoding="utf-8") as f:
            ranges = [tuple(int(x) for x in line.split()) for line in f if line.strip()]
        if not any(inside <= 0 < inside + count for inside, _, count in ranges):
            with open("/proc/sys/kernel/overflowuid", encoding="utf-8") as f:
                uids.add(int(f.read().strip()))
    except (OSError, ValueError):
        pass
    return uids


def check_ancestors(ctx, findings):
    """Every parent folder of the private folder belongs to root or to the user, and only
    they can change it, unless it is a sticky folder of root, such as /tmp."""
    roots = root_uids()
    count = 0
    path = ctx.private
    while True:
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
        count += 1
        try:
            st = os.lstat(path)
        except OSError as exc:
            findings.append(("ancestor-unsafe", f"cannot read {path} ({exc.strerror})"))
            continue
        if st.st_uid not in roots | {os.geteuid()}:
            findings.append(("ancestor-unsafe", f"parent folder of another user: {path}"))
        sticky_root = st.st_mode & stat.S_ISVTX and st.st_uid in roots
        if st.st_mode & 0o022 and not sticky_root:
            findings.append(("ancestor-unsafe", f"parent folder writable by others: {path}"))
    return count


def private_identities(ctx, run_dir=None):
    """(device, inode) of the private folder, its components and the run folder."""
    found = {}
    for rel in ("",) + PRIVATE_COMPONENTS:
        try:
            st = os.lstat(os.path.join(ctx.private, rel) if rel else ctx.private)
            found[rel or "."] = [st.st_dev, st.st_ino]
        except OSError:
            found[rel or "."] = None
    if run_dir:
        try:
            st = os.lstat(run_dir)
            found["run-folder"] = [st.st_dev, st.st_ino]
        except OSError:
            found["run-folder"] = None
    return found


def compare_identities(before, after):
    return [("folder-replaced", f"replaced during the step: {name}")
            for name, ident in before.items() if after.get(name) != ident]


def check_image(ctx, findings, notes, facts):
    rel = f"iso/{ISO_NAME}"
    try:
        st = os.lstat(ctx.iso)
    except FileNotFoundError:
        findings.append(("image-absent", f"disc image absent: {rel}"))
        return
    except OSError as exc:
        findings.append(("image-unreadable", f"cannot read the metadata of {rel} "
                                             f"({exc.strerror})"))
        return
    if not stat.S_ISREG(st.st_mode) or os.path.realpath(ctx.iso) != ctx.iso:
        findings.append(("image-invalid", f"not a regular file at its canonical path: {rel}"))
        return
    if st.st_mode & 0o222 or os.access(ctx.iso, os.W_OK):
        findings.append(("image-writable", f"the disc image can be written: {rel}"))
    if not os.access(ctx.iso, os.R_OK):
        findings.append(("image-unreadable", f"the disc image cannot be read: {rel}"))
    if st.st_size == 0:
        findings.append(("image-empty", f"empty disc image: {rel}"))
    if st.st_nlink > 1:
        notes.append(f"the disc image has {st.st_nlink} hard links")
    facts.update({"image_size": st.st_size, "image_mode": f"{stat.S_IMODE(st.st_mode):04o}",
                  "image_hard_links": st.st_nlink})


def check_game_empty(ctx, findings, facts):
    try:
        names = os.listdir(ctx.game)
    except OSError as exc:
        findings.append(("folder-invalid", f"cannot list game/ ({exc.strerror})"))
        return
    facts["game_entries"] = len(names)
    if names:
        findings.append(("game-not-empty", f"game/ holds {len(names)} entries: B1 extracts "
                                           "into an empty folder only"))


def check_sdk(ctx, findings, facts):
    if not ctx.sdk:
        findings.append(("sdk-invalid", "no SDK given (--sdk)"))
        return
    name = os.path.basename(ctx.sdk)
    facts["sdk_is_0_11_0"] = (os.path.dirname(ctx.sdk) == ctx.store
                              and name.endswith(SDK_SUFFIX))
    if not facts["sdk_is_0_11_0"]:
        findings.append(("sdk-invalid", f"not the ReXGlue 0.11.0 store path: {ctx.sdk}"))
        return
    try:
        st = os.lstat(ctx.sdk)
        rex = os.lstat(os.path.join(ctx.sdk, "bin", "rexglue"))
    except OSError as exc:
        findings.append(("sdk-invalid", f"the SDK is not built: {ctx.sdk} ({exc.strerror})"))
        return
    if not stat.S_ISDIR(st.st_mode) or not stat.S_ISREG(rex.st_mode) or \
            not rex.st_mode & 0o111:
        findings.append(("sdk-invalid", "bin/rexglue of the SDK is not an executable file"))
    facts["sdk_registered"] = utc_stamp(max(st.st_ctime, rex.st_ctime))


def check_repo(ctx, findings, facts):
    if not ctx.repo:
        findings.append(("repo-invalid", "no repository given (--repo)"))
        return
    code, out, _, error = run_capture([ctx.args.git, "-C", ctx.repo, "status", "--porcelain",
                                       "--untracked-files=all"], timeout=120)
    if error or code != 0:
        findings.append(("repo-invalid", f"git status failed ({error or code})"))
    else:
        lines = [line for line in os.fsdecode(out).splitlines() if line.strip()]
        facts["repository_changes"] = len(lines)
        if lines:
            findings.append(("repo-invalid", f"the repository is not clean: {len(lines)} "
                                             "entries"))
    code, out, _, error = run_capture([ctx.args.git, "-C", ctx.repo, "rev-parse", "HEAD"],
                                      timeout=60)
    if code == 0:
        facts["repository_commit"] = os.fsdecode(out).strip()


def incomplete_runs(ctx):
    """Run folders whose state.json does not say `complete`."""
    found = []
    try:
        names = sorted(os.listdir(ctx.logs))
    except OSError:
        return found
    for name in names:
        if RUN_DIR_RE.fullmatch(name):
            state = read_state(os.path.join(ctx.logs, name))
            if not state or state.get("phase") != "complete":
                found.append(name)
    return found


# --- mounts (R01, R07) --------------------------------------------------------------------

def read_mounts(ctx):
    """The mount table from `findmnt --list --json`, with the identity and the attributes
    of each mount. Returns (mounts, raw output, error)."""
    argv = [ctx.args.findmnt, "--list", "--json", "--output", MOUNT_COLUMNS]
    code, out, err, error = run_capture(argv, timeout=60)
    if error:
        return None, b"", error
    if code != 0:
        return None, out + err, f"findmnt exited with status {code}"
    try:
        data = json.loads(out.decode("utf-8", "surrogateescape"))
        mounts = []
        for entry in data["filesystems"]:
            mount = {key: entry.get(key) for key in MOUNT_KEYS}
            if not isinstance(mount["target"], str) or not os.path.isabs(mount["target"]):
                raise ValueError("a mount without an absolute target")
            mount["target"] = os.path.normpath(mount["target"])
            mounts.append(mount)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, out, f"unreadable findmnt output ({type(exc).__name__})"
    return mounts, out, None


def mount_scope(ctx):
    """The watched places and the private folder. A mount is in scope when its target is
    one of them, under one of them, or a parent of one of them."""
    return [os.path.realpath(top) for top in ctx.tops()] + [ctx.private]


def in_scope(target, scope):
    return any(under_or_self(target, place) or strictly_under(place, target)
               for place in scope)


def mount_plan(ctx, mounts):
    """Returns (relevant mounts, folders to watch, facts, findings)."""
    scope = mount_scope(ctx)
    tops = [os.path.realpath(top) for top in ctx.tops()]
    relevant = [m for m in mounts if in_scope(m["target"], scope)]
    watch, findings = [], []
    files = 0
    private_is_mount = False
    for target in sorted({m["target"] for m in relevant}):
        if target == ctx.private:
            private_is_mount = True
            continue
        if strictly_under(target, ctx.private):
            findings.append(("private-mount", f"mount point inside the private folder: "
                                              f"{target}"))
            continue
        if not any(strictly_under(target, top) for top in tops):
            continue  # a parent of a watched place: compared, not searched on its own
        try:
            st = os.lstat(target)
        except OSError:
            watch.append(target)  # postflight reports a watched place that is absent
            continue
        if stat.S_ISDIR(st.st_mode):
            watch.append(target)
        else:
            files += 1  # a bound file: searched as an entry of its parent folder
    facts = {"mounts_in_scope": len(relevant), "mount_points_watched": len(watch),
             "mount_points_not_folders": files, "private_folder_is_mount": private_is_mount}
    return relevant, watch, facts, findings


def mount_key(mount):
    return json.dumps([mount.get(key) for key in MOUNT_KEYS], sort_keys=True)


def compare_mounts(before, after):
    """Mounts in scope that appeared, disappeared or changed (same target, another
    identity or other attributes: a replacement, a remount or a bind)."""
    def by_target(mounts):
        table = {}
        for mount in mounts:
            table.setdefault(mount["target"], []).append(mount_key(mount))
        return {target: sorted(keys) for target, keys in table.items()}
    old, new = by_target(before), by_target(after)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(t for t in set(old) & set(new) if old[t] != new[t])
    findings = [("mount-changed", f"new mount point: {t}") for t in added]
    findings += [("mount-changed", f"mount point gone: {t}") for t in removed]
    findings += [("mount-changed", f"mount replaced or changed: {t}") for t in changed]
    return {"added": len(added), "removed": len(removed), "changed": len(changed)}, findings


class MountEvents:
    """/proc/self/mountinfo, polled for POLLPRI: the kernel signals every mount or unmount
    in this mount namespace after the file was opened, even one undone since."""

    def __init__(self, path):
        self.fd = None
        self.error = None
        try:
            self.fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as exc:
            self.error = exc.strerror

    def changed(self):
        if self.fd is None:
            return None
        poller = select.poll()
        poller.register(self.fd, select.POLLPRI | select.POLLERR)
        return any(event & (select.POLLPRI | select.POLLERR)
                   for _, event in poller.poll(0))


def check_watch_places(ctx, watch, findings):
    places = [ctx.home, ctx.tmp_watch] + list(watch)
    for place in places:
        if not os.path.isdir(place):
            findings.append(("watch-unusable", f"absent or not a folder: {place}"))
        elif not os.access(place, os.R_OK | os.X_OK):
            findings.append(("watch-unusable", f"not readable: {place}"))
    return len(places)


# --- core dumps (R03) ---------------------------------------------------------------------

def core_identity(pattern_file, suid_file, boot_file=BOOT_ID_FILE):
    """What a proof of option B holds for: this boot, this kernel, this core_pattern and
    this suid_dumpable. Returns None if one of them cannot be read."""
    try:
        with open(pattern_file, "rb") as f:
            pattern = f.read()
        with open(suid_file, encoding="utf-8") as f:
            suid = f.read().strip()
        with open(boot_file, encoding="utf-8") as f:
            boot = f.read().strip()
    except OSError:
        return None
    uname = os.uname()
    return {"boot_id": boot, "kernel_release": uname.release, "kernel_version": uname.version,
            "core_pattern_sha256": hashlib.sha256(pattern.strip()).hexdigest(),
            "suid_dumpable": suid}


def find_core_proof(ctx, identity):
    """The newest complete rehearsal whose proof holds for `identity`, or None."""
    if not identity:
        return None
    try:
        names = sorted(os.listdir(ctx.logs), reverse=True)
    except OSError:
        return None
    for name in names:
        if RUN_DIR_RE.fullmatch(name) and name.startswith("b1-rehearse-"):
            state = read_state(os.path.join(ctx.logs, name))
            if state and state.get("phase") == "complete" and \
                    state.get("controls_clean") is True and \
                    state.get("core_proof") == dict(identity, result="validated"):
                return name
    return None


def core_settings(ctx, findings):
    """How the kernel handles a core dump. Only a program (|) is accepted (D-018): the
    kernel drops the crash of a process with RLIMIT_CORE 1 before it starts the program
    (fs/coredump.c). A socket (@) ignores the limit, and a file is not a validated mode:
    both are refused. A pipe needs a local proof, made by rehearse."""
    facts = {}
    try:
        with open(ctx.args.core_pattern_file, encoding="utf-8", errors="replace") as f:
            pattern = f.read().strip()
        with open(ctx.args.suid_dumpable_file, encoding="utf-8") as f:
            facts["suid_dumpable"] = f.read().strip()
    except OSError as exc:
        findings.append(("core-settings-unreadable", f"cannot read the core dump settings "
                                                     f"({exc.strerror})"))
        return facts
    if pattern.startswith("|"):
        facts["core_pattern_kind"] = "pipe"
        words = pattern[1:].split()
        handler = os.path.basename(words[0]) if words else ""
        facts["core_handler"] = "systemd-coredump" if handler == "systemd-coredump" \
            else "other"
        identity = core_identity(ctx.args.core_pattern_file, ctx.args.suid_dumpable_file)
        proof = find_core_proof(ctx, identity)
        facts["proof_found"] = proof is not None
        if identity is None:
            findings.append(("core-settings-unreadable", "cannot read the boot id"))
        elif proof is None:
            findings.append(("core-proof-missing", "no rehearsal of this boot proves that a "
                                                   "crash at limit 1 reaches no handler"))
    elif pattern.startswith("@"):
        facts["core_pattern_kind"] = "socket"
        facts["core_handler"] = "other"
        findings.append(("core-mode-refused", "a core dump socket ignores RLIMIT_CORE"))
    else:
        facts["core_pattern_kind"] = "file"
        facts["core_handler"] = "none"
        findings.append(("core-mode-refused", "core dumps to a file: not a mode validated by "
                                              "D-018"))
    return facts


def coredumps_since(ctx, since):
    """Core dumps recorded since `since`, from `coredumpctl --json=short list`. Returns
    (entries, raw output, error)."""
    argv = [ctx.args.coredumpctl, "--no-pager", "--json=short", "list",
            f"--since=@{int(since)}"]
    code, out, err, error = run_capture(argv, timeout=120)
    raw = out + err
    if error:
        return None, raw, error
    if code == 1 and b"No coredumps found" in err:
        return [], raw, None
    if code != 0:
        return None, raw, f"coredumpctl exited with status {code}"
    try:
        entries = json.loads(out.decode("utf-8", "replace"))
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError("not a list of entries")
    except ValueError as exc:
        return None, raw, f"unreadable coredumpctl output ({type(exc).__name__})"
    return entries, raw, None


# --- the local J0 report (R06) ------------------------------------------------------------

def check_j0_report(ctx, findings, facts, notes):
    """The local J0 report must exist in the private folder, describe a disc image, and
    match the J0 references. Returns the image hash it holds, or None."""
    facts["report_present"] = False
    path = ctx.j0_report
    if not under_or_self(os.path.realpath(path), ctx.private):
        findings.append(("j0-report-invalid", "the local J0 report is outside the private "
                                              "folder"))
        return None
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        findings.append(("j0-report-absent", "no local J0 report: whether B1 may run "
                                             "without it is for the owner to decide"))
        return None
    except OSError as exc:
        findings.append(("j0-report-invalid", f"cannot read the local J0 report "
                                              f"({exc.strerror})"))
        return None
    facts["report_present"] = True
    if not stat.S_ISREG(st.st_mode) or st.st_size > 16 << 20:
        findings.append(("j0-report-invalid", "the local J0 report is not a regular file of "
                                              "at most 16 MiB"))
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with open(fd, encoding="utf-8") as f:
            report = json.load(f)
        source = report["source"]
        image_sha256 = source["sha256"]
        if source.get("kind") != "image" or not re.fullmatch(r"[0-9a-f]{64}", image_sha256):
            raise ValueError("not an image report")
        size = int(source["size"])
        disc = report["disc"]
        modules = {m["path"].lower(): m.get("sha256") for m in report["modules"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        findings.append(("j0-report-invalid", f"unreadable local J0 report "
                                              f"({type(exc).__name__})"))
        return None
    reference = ctx.reference
    differences = []
    if disc.get("files") != reference["files"]:
        differences.append("files")
    if disc.get("directories") != reference["directories"]:
        differences.append("directories")
    for name, expected in reference["modules"].items():
        if modules.get(name.lower()) != expected:
            differences.append(name)
    try:
        if os.lstat(ctx.iso).st_size != size:
            differences.append("image size")
    except OSError:
        differences.append("image size")
    facts["report_matches_j0"] = not differences
    if differences:
        findings.append(("j0-report-mismatch", "the local J0 report differs from the "
                                               f"references: {', '.join(differences)}"))
        return None
    return image_sha256


# --- the sandbox (R02) --------------------------------------------------------------------

def bwrap_version(ctx):
    code, out, err, error = run_capture([ctx.args.bwrap, "--version"], timeout=30)
    if error or code != 0:
        return None
    match = re.search(rb"(\d+)\.(\d+)\.(\d+)", out + err)
    return tuple(int(x) for x in match.groups()) if match else None


def sandbox_blockers(ctx):
    """The sandbox hides the home folder: what it needs must lie elsewhere."""
    needed = [os.path.realpath(sys.executable), os.path.realpath(__file__)]
    if ctx.sdk:
        needed.append(os.path.realpath(ctx.sdk))
    return [("sandbox-unavailable", f"needed by the sandbox, but inside the home folder, "
                                    f"which it hides: {path} (use the packaged command)")
            for path in needed if under_or_self(path, ctx.home)]


def sandbox_argv(ctx, run_dir, command, status_fd, chdir=None):
    """bubblewrap around one command: every namespace unshared (no network: only a
    loopback of its own), no further user namespace, killed with this process, the whole
    file system read-only, an empty tmpfs over the folders of system sockets and shared
    temporary files, an empty read-only tmpfs over the home folder (its sockets and files
    are out of reach), the private folder read-only, and only the run folder, game/, app/
    and tmp/ writable."""
    argv = [ctx.args.bwrap, "--unshare-all", "--unshare-user", "--disable-userns",
            "--die-with-parent", "--new-session",
            "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
    for path in SANDBOX_HIDDEN:
        if os.path.isdir(path) and not os.path.islink(path):
            argv += ["--size", str(SANDBOX_TMPFS_BYTES), "--tmpfs", path]
    argv += ["--size", str(HOME_TMPFS_BYTES), "--tmpfs", ctx.home]
    argv += ["--ro-bind", ctx.private, ctx.private, "--bind", run_dir, run_dir]
    for name in SANDBOX_WRITABLE:
        path = os.path.join(ctx.private, name)
        argv += ["--bind", path, path]
    argv += ["--remount-ro", ctx.home]
    argv += ["--chdir", chdir or ctx.private, "--json-status-fd", str(status_fd), "--"]
    return argv + list(command)


class Sandbox:
    """One sandboxed command, with its bubblewrap status (child pid, exit code)."""

    def __init__(self, ctx, run_dir, command, env, stdout, stderr, stdin=None,
                 core_limit=EXTRACTION_CORE_LIMIT, chdir=None):
        self.read_fd, write_fd = os.pipe()
        os.set_blocking(self.read_fd, False)
        self.status = b""
        self.closed = False
        argv = sandbox_argv(ctx, run_dir, command, write_fd, chdir=chdir)
        try:
            self.proc = subprocess.Popen(
                argv, stdin=stdin if stdin is not None else subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, env=env, cwd=ctx.private, pass_fds=(write_fd,),
                start_new_session=True,
                preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, core_limit))
        except OSError:
            os.close(self.read_fd)
            raise
        finally:
            os.close(write_fd)

    def documents(self):
        try:
            while not self.closed:
                chunk = os.read(self.read_fd, 65536)
                if not chunk:
                    break
                self.status += chunk
        except BlockingIOError:
            pass
        found = []
        decoder = json.JSONDecoder()
        text = self.status.decode("utf-8", "replace")
        position = 0
        while True:
            while position < len(text) and text[position].isspace():
                position += 1
            if position >= len(text):
                break
            try:
                document, position = decoder.raw_decode(text, position)
            except ValueError:
                break
            found.append(document)
        return found

    def child_pid(self):
        for document in self.documents():
            if isinstance(document, dict) and isinstance(document.get("child-pid"), int):
                return document["child-pid"]
        return None

    def command_pids(self):
        """Host pids of the sandboxed command: the children of bubblewrap's init."""
        init = self.child_pid()
        if init is None:
            return []
        try:
            with open(f"/proc/{init}/task/{init}/children", encoding="utf-8") as f:
                return [int(pid) for pid in f.read().split()]
        except (OSError, ValueError):
            return []

    def stop(self):
        """SIGTERM to the sandboxed command, then SIGKILL to bubblewrap, whose sandbox dies
        with it (--die-with-parent)."""
        for pid in self.command_pids():
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        try:
            return self.proc.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return self.proc.wait()

    def close(self):
        if not self.closed:
            self.documents()
            self.closed = True
            os.close(self.read_fd)


def probe_spec(ctx, run_dir, tcp_port, abstract):
    return {"home": ctx.home, "private": ctx.private, "iso_dir": os.path.dirname(ctx.iso),
            "store": ctx.store, "repo": ctx.repo, "run_dir": run_dir,
            "game": ctx.game, "app": os.path.join(ctx.private, "app"),
            "tmp": os.path.join(ctx.private, "tmp"), "image": ctx.iso,
            "tcp_port": tcp_port, "abstract": abstract,
            "hidden": [path for path in SANDBOX_HIDDEN
                       if os.path.isdir(path) and not os.path.islink(path)]}


def run_probe(ctx, steps, run_dir, env):
    """The confinement probe: a synthetic program, started in the same sandbox as the
    extraction, tries what the sandbox must forbid. A TCP listener on the host loopback and
    an abstract socket of the host are the targets it must not reach."""
    findings, facts = [], {}
    version = bwrap_version(ctx)
    facts["bwrap_version_ok"] = bool(version and version >= BWRAP_MIN_VERSION)
    findings += sandbox_blockers(ctx)
    if not facts["bwrap_version_ok"]:
        findings.append(("sandbox-unavailable", "bubblewrap is missing or older than "
                                                "0.8.0"))
    if findings:
        return steps.add("sandbox", "ok", facts=facts, findings=findings)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    abstract = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    name = f"fifa2010wc-b1-probe-{os.getpid()}-{time.monotonic_ns()}"
    out_path = os.path.join(run_dir, "probe.json")
    started = time.monotonic()
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        abstract.bind("\0" + name)
        abstract.listen(1)
        spec = probe_spec(ctx, run_dir, listener.getsockname()[1], name)
        command = [sys.executable, "-I", os.path.abspath(__file__), "_probe",
                   json.dumps(spec)]
        with open(out_path, "xb") as out, open(os.path.join(run_dir, "probe.stderr"),
                                               "xb") as err:
            try:
                box = Sandbox(ctx, run_dir, command, env, out, err)
            except OSError as exc:
                findings.append(("sandbox-unavailable", f"bubblewrap did not start "
                                                        f"({exc.strerror})"))
                return steps.add("sandbox", "ok", facts=facts, findings=findings)
            try:
                code = box.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                code = box.stop()
            box.close()
    finally:
        listener.close()
        abstract.close()
    try:
        with open(out_path, encoding="utf-8") as f:
            results = json.load(f)
        checks = {r["name"]: bool(r["ok"]) for r in results}
    except (OSError, ValueError, KeyError, TypeError):
        findings.append(("sandbox-unavailable", f"the sandbox did not run the probe "
                                                f"(bubblewrap status {code})"))
        return steps.add("sandbox", "ok", exit_code=code, facts=facts, findings=findings,
                         output="probe.json, probe.stderr",
                         duration=time.monotonic() - started)
    failed = [name for name in PROBE_CHECKS if not checks.get(name, False)]
    facts.update({"probe_checks": len(PROBE_CHECKS),
                  "probe_checks_passed": len(PROBE_CHECKS) - len(failed),
                  "probe_failed_checks": failed})
    if code != 0 or failed:
        findings.append(("sandbox-probe-failed", f"confinement checks that failed: "
                                                 f"{', '.join(failed) or 'none'}; "
                                                 f"bubblewrap status {code}"))
    return steps.add("sandbox", "ok", exit_code=code, facts=facts, findings=findings,
                     output="probe.json, probe.stderr", duration=time.monotonic() - started)


def probe_main(argv):
    """Inside the sandbox (hidden command `_probe`). Prints one JSON list of checks."""
    spec = json.loads(argv[0])
    results = []

    def check(name, ok, detail=""):
        results.append({"name": name, "ok": bool(ok), "detail": detail})

    def write_denied(name, folder):
        if not folder:
            return check(name, True, "not given")
        path = os.path.join(folder, f".b1-probe-{os.getpid()}")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            return check(name, True, errno.errorcode.get(exc.errno, str(exc.errno)))
        os.close(fd)
        check(name, False, "written")

    def fails(name, action, accepted=None):
        try:
            action()
        except OSError as exc:
            code = errno.errorcode.get(exc.errno, str(exc.errno)) if exc.errno else "timeout"
            return check(name, accepted is None or code in accepted, code)
        check(name, False, "succeeded")

    write_denied("write-denied-home", spec["home"])
    write_denied("write-denied-private-root", spec["private"])
    write_denied("write-denied-iso", spec["iso_dir"])
    write_denied("write-denied-store", spec["store"])
    write_denied("write-denied-repo", spec["repo"])
    try:
        fd = os.open(os.path.join(spec["run_dir"], "probe-write-check.txt"),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.write(fd, b"synthetic probe file\n")
        os.close(fd)
        check("write-allowed-run-folder", True)
    except OSError as exc:
        check("write-allowed-run-folder", False, errno.errorcode.get(exc.errno, ""))
    for name in ("game", "app", "tmp"):
        check(f"writable-{name}", os.access(spec[name], os.W_OK))
    check("image-read-only", os.access(spec["image"], os.R_OK)
          and not os.access(spec["image"], os.W_OK))
    hidden = set(spec["hidden"])
    check("tmp-private-empty", "/tmp" not in hidden or os.listdir("/tmp") == [])
    check("run-hidden", "/run" not in hidden or os.listdir("/run") == [])
    check("nix-daemon-socket-hidden",
          not os.path.lexists("/nix/var/nix/daemon-socket/socket"))
    rel = os.path.relpath(spec["private"], spec["home"])
    allowed = set() if rel.startswith("..") else {rel.split(os.sep)[0]}
    try:
        visible = set(os.listdir(spec["home"]))
        check("home-hidden", visible <= allowed, str(len(visible)))
    except OSError as exc:
        check("home-hidden", False, errno.errorcode.get(exc.errno, ""))
    names = [name for _, name in socket.if_nameindex()]
    check("net-loopback-only", names == ["lo"], ",".join(names))

    def connect(family, address, timeout=2):
        def action():
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(address)
        return action

    def udp():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(b"synthetic", ("192.0.2.1", 9))

    unreachable = {"ENETUNREACH", "EHOSTUNREACH", "EADDRNOTAVAIL"}
    fails("net-tcp-host-unreachable", connect(socket.AF_INET, ("127.0.0.1",
                                                               spec["tcp_port"])))
    fails("net-tcp-remote-unreachable", connect(socket.AF_INET, ("192.0.2.1", 9)),
          unreachable)
    fails("net-udp-unreachable", udp, unreachable)
    fails("net-abstract-unix-isolated", connect(socket.AF_UNIX, "\0" + spec["abstract"]))
    fails("userns-disabled", lambda: os.unshare(os.CLONE_NEWUSER))
    check("core-limit-one", resource.getrlimit(resource.RLIMIT_CORE) == (1, 1))
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            cap = [line.split()[1] for line in f if line.startswith("CapEff:")][0]
        check("no-capabilities", int(cap, 16) == 0, cap)
    except (OSError, IndexError, ValueError):
        check("no-capabilities", False, "unreadable")
    pids = [d for d in os.listdir("/proc") if d.isdigit()]
    check("pid-isolated", len(pids) <= 4, str(len(pids)))
    print(json.dumps(results))
    return 0


def crash_main(argv):
    """Inside the sandbox (hidden command `_crash`): holds a synthetic sentinel, waits for
    one byte on stdin, then crashes with SIGSEGV."""
    sentinel = ("fifa2010wc synthetic crash sentinel " * 64).encode()
    sys.stdin.buffer.read(1)
    os.kill(os.getpid(), signal.SIGSEGV)
    return len(sentinel)


def synthetic_crash(ctx, run_dir, name, core_limit):
    """One synthetic crash in the sandbox, from / and with an empty environment, so that
    the journal entry of a handler names no private path. Returns (signal, pids)."""
    command = [sys.executable, "-I", os.path.abspath(__file__), "_crash"]
    read_end, write_end = os.pipe()
    with open(os.path.join(run_dir, f"{name}.stdout"), "xb") as out, \
            open(os.path.join(run_dir, f"{name}.stderr"), "xb") as err:
        try:
            box = Sandbox(ctx, run_dir, command, {}, out, err, stdin=read_end,
                          core_limit=core_limit, chdir="/")
        except OSError:
            os.close(read_end)
            os.close(write_end)
            return None, []
        os.close(read_end)
        pids = []
        for _ in range(100):
            pids = box.command_pids()
            if pids:
                break
            time.sleep(0.05)
        try:
            os.write(write_end, b"x")
        except OSError:
            pass  # the program ended before reading: the status below says how
        os.close(write_end)
        try:
            code = box.proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            code = box.stop()
        box.close()
    return (code - 128 if isinstance(code, int) and code > 128 else None), pids


def crash_entries(ctx, since, pids, lines):
    entries, raw, error = coredumps_since(ctx, since)
    lines.append(raw.decode("utf-8", "replace"))
    if error:
        return None, error
    return [e for e in entries if e.get("pid") in pids or
            (not pids and e.get("exe") == sys.executable)], None


def run_core_probe(ctx, steps, run_dir, state):
    """The local proof of option B (D-018), with synthetic programs only, in the sandbox of
    the extraction. A control crash with RLIMIT_CORE 0 must reach the handler: coredumpctl
    lists it, which shows that the handler and coredumpctl work. The same crash with
    RLIMIT_CORE 1 must reach nothing: no entry, after waiting at least PROOF_MIN_WAIT
    seconds and three times the delay of the control. The proof holds for this boot, this
    kernel, this core_pattern and this suid_dumpable only."""
    findings, facts, lines = [], {}, []
    identity = core_identity(ctx.args.core_pattern_file, ctx.args.suid_dumpable_file)
    started = time.monotonic()
    since = int(time.time()) - 1
    signal_0, pids_0 = synthetic_crash(ctx, run_dir, "core-control", CONTROL_CORE_LIMIT)
    crashed = time.monotonic()
    facts["control_signal"] = signal_0
    control = None
    for _ in range(30):
        matching, error = crash_entries(ctx, since, pids_0, lines)
        if error:
            findings.append(("coredumpctl-failed", error))
            break
        if matching:
            control = matching[0]
            break
        time.sleep(0.5)
    latency = time.monotonic() - crashed
    facts["control_entry_found"] = control is not None
    facts["control_corefile"] = control.get("corefile", "unknown") if control else "unknown"
    probe_pids = set(pids_0) | ({control["pid"]} if control and
                                isinstance(control.get("pid"), int) else set())
    since_1 = int(time.time()) + 1
    while time.time() < since_1:
        time.sleep(0.05)
    signal_1, pids_1 = synthetic_crash(ctx, run_dir, "core-limit-one", EXTRACTION_CORE_LIMIT)
    facts["limit_one_signal"] = signal_1
    deadline = time.monotonic() + max(PROOF_MIN_WAIT, 3 * latency)
    reached = None
    while time.monotonic() < deadline and reached is None and not findings:
        matching, error = crash_entries(ctx, since_1, pids_1, lines)
        if error:
            findings.append(("coredumpctl-failed", error))
        elif matching:
            reached = matching[0]
        else:
            time.sleep(0.5)
    facts["limit_one_entry_found"] = reached is not None
    if reached and isinstance(reached.get("pid"), int):
        probe_pids.add(reached["pid"])
    write_new(os.path.join(run_dir, "core-probe-coredumpctl.txt"), "\n".join(lines))
    acquired = (identity is not None and signal_0 == signal.SIGSEGV and control is not None
                and signal_1 == signal.SIGSEGV and reached is None and not findings)
    facts["proof_acquired"] = acquired
    if acquired:
        state["core_proof"] = dict(identity, result="validated")
    else:
        findings.append(("core-probe-failed", "control crash with an entry, then a crash at "
                                              "limit 1 without one, were not both observed"))
    state["core_probe_pids"] = sorted(probe_pids)
    return steps.add("core-probe", "ok", facts=facts, findings=findings,
                     output="core-probe-coredumpctl.txt",
                     duration=time.monotonic() - started)


# --- the step -----------------------------------------------------------------------------

def step_env(ctx, run_dir):
    """The environment of docs/J2_PHASE_B_CONTROLS.md section 2 for every command of the
    step. ReXGlue settings inherited from the shell (REX_*) are dropped: only the ones set
    here apply."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("REX_")}
    for name, folder in ENV_FOLDERS:
        env[name] = os.path.join(ctx.private, folder)
    env["REX_APP_LOG_ROOT"] = run_dir
    env["WC2010_PRIVATE_DIR"] = ctx.private
    env["NO_COLOR"] = "1"
    return env


def make_env_folders(ctx):
    for _, folder in ENV_FOLDERS:
        os.makedirs(os.path.join(ctx.private, folder), mode=0o700, exist_ok=True)


def store_survey(ctx, run_dir, name):
    """CP-3 (docs/J0_ISO_IDENTIFICATION.md section 6): the two limited searches of the
    store. find only reads names and sizes; no store file is opened."""
    commands = [
        [ctx.args.find, ctx.store, "-maxdepth", "1", "-type", "f", "-size", "+100M"],
        [ctx.args.find, ctx.store, "-maxdepth", "3", "-type", "f", "(", "-iname", "*.xex",
         "-o", "(", "-iname", "*.iso", "-size", "+100M", ")", ")"],
    ]
    matches, findings, codes, lines = set(), [], [], []
    started = time.monotonic()
    for argv in commands:
        code, out, err, error = run_capture(argv, timeout=7200)
        codes.append(code)
        found = [os.fsdecode(line) for line in out.split(b"\n") if line]
        matches.update(found)
        lines.append("$ " + " ".join(argv))
        lines.extend(found)
        lines.extend("stderr: " + os.fsdecode(line) for line in err.split(b"\n") if line)
        lines.append(f"exit status: {code if error is None else error}")
        if error or code != 0:
            findings.append(("cp3-search-failed", f"a CP-3 search ended with "
                                                  f"{error or f'status {code}'}"))
    write_new(os.path.join(run_dir, f"{name}.txt"), "\n".join(lines) + "\n")
    known = any(os.path.basename(path) == KNOWN_STORE_ENTRY for path in matches)
    facts = {"matches": len(matches), "known_entry_listed": known,
             "other_matches": sum(1 for path in matches
                                  if os.path.basename(path) != KNOWN_STORE_ENTRY)}
    exit_code = max((code for code in codes if code is not None), default=None)
    return matches, exit_code, findings, facts, time.monotonic() - started


def image_state(path):
    """SHA-256 and identity of the disc image, read in place; the image is never written."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    digest = hashlib.sha256()
    with open(fd, "rb", buffering=0) as f:
        st = os.fstat(f.fileno())
        buffer = bytearray(1 << 20)
        view = memoryview(buffer)
        while True:
            count = f.readinto(buffer)
            if not count:
                break
            digest.update(view[:count])
    identity = {key: getattr(st, key) for key in (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns")}
    return {"sha256": digest.hexdigest(), "identity": identity}


def survey_tree(root, modules):
    """The PB-1 figures of an extracted tree. Every entry below `root` is counted, the root
    itself is not, as the J0 tool counts the disc. Names that start with a dot are counted
    too, and reported. Folders are opened with O_NOFOLLOW from the descriptor of their
    parent, so a link is never followed. A link, a special file, a hard link, an entry on
    another file system or an unreadable entry is an anomaly, and is not counted. The
    modules named in `modules` are looked for at the root, by name in any case, and
    hashed."""
    figures = {"files": 0, "directories": 0, "bytes": 0, "hidden_names": 0,
               "anomalies": [], "modules": {}}
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    anomalies = figures["anomalies"]
    try:
        root_fd = os.open(root, flags)
    except OSError as exc:
        anomalies.append(["unreadable folder", f". ({exc.strerror})"])
        return figures
    root_st = os.fstat(root_fd)
    at_root = {}
    stack = [(root_fd, "")]
    try:
        while stack:
            fd, rel = stack.pop()
            try:
                with os.scandir(fd) as entries:
                    names = sorted(entry.name for entry in entries)
            except OSError as exc:
                anomalies.append(["unreadable folder", f"{rel or '.'} ({exc.strerror})"])
                names = []
            for name in names:
                path = f"{rel}/{name}" if rel else name
                if name.startswith("."):
                    figures["hidden_names"] += 1
                try:
                    st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except OSError as exc:
                    anomalies.append(["unreadable entry", f"{path} ({exc.strerror})"])
                    continue
                if stat.S_ISLNK(st.st_mode):
                    anomalies.append(["symbolic link", path])
                elif st.st_dev != root_st.st_dev:
                    anomalies.append(["other file system", path])
                elif stat.S_ISDIR(st.st_mode):
                    try:
                        child = os.open(name, flags, dir_fd=fd)
                    except OSError as exc:
                        anomalies.append(["unreadable folder", f"{path} ({exc.strerror})"])
                        continue
                    child_st = os.fstat(child)
                    if (child_st.st_dev, child_st.st_ino) != (st.st_dev, st.st_ino):
                        os.close(child)
                        anomalies.append(["changed while counted", path])
                        continue
                    figures["directories"] += 1
                    stack.append((child, path))
                elif stat.S_ISREG(st.st_mode):
                    if st.st_nlink != 1:
                        anomalies.append(["hard link", path])
                        continue
                    figures["files"] += 1
                    figures["bytes"] += st.st_size
                    if not rel:
                        at_root.setdefault(name.lower(), []).append((name, st))
                else:
                    anomalies.append(["special file", path])
            if fd != root_fd:
                os.close(fd)
        for key in modules:
            found = at_root.get(key.lower(), [])
            if not found:
                figures["modules"][key] = {"status": "absent"}
            elif len(found) > 1:
                figures["modules"][key] = {"status": "ambiguous", "names": len(found)}
                anomalies.append(["several names for one module", key])
            else:
                name, st = found[0]
                figures["modules"][key] = hash_module(root_fd, name, st)
    finally:
        for fd, _ in stack:
            if fd != root_fd:
                os.close(fd)
        os.close(root_fd)
    return figures


def hash_module(dir_fd, name, listed):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError as exc:
        return {"status": "unreadable", "detail": exc.strerror}
    digest = hashlib.sha256()
    with open(fd, "rb", buffering=0) as f:
        st = os.fstat(f.fileno())
        if (st.st_dev, st.st_ino) != (listed.st_dev, listed.st_ino):
            return {"status": "changed while counted"}
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return {"status": "hashed", "sha256": digest.hexdigest(), "size": st.st_size}


def dump_block(run_dir):
    """Type and Nodes from the summary block of `rexglue vfs dump`."""
    block = {}
    for name in ("vfs-dump.stderr", "vfs-dump.stdout"):
        try:
            with open(os.path.join(run_dir, name), encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        for key, value in BLOCK_RE.findall(text):
            block.setdefault(key.lower(), value)
    return block


def guard_step(ctx, steps, name, argv, run_dir=None, env=None, cwd=None, output=None):
    """Runs one private_guard command. 0 passes; 1 is a finding; any other status or a
    failure to run is a finding too."""
    started = time.monotonic()
    code, out, err, error = run_capture(argv, env=env, cwd=cwd, timeout=7200)
    text = os.fsdecode(out) + os.fsdecode(err)
    if run_dir:
        output = output or f"{name}.txt"
        write_new(os.path.join(run_dir, output), text)
    findings = []
    lines = text.splitlines()
    for line in lines:
        if line.startswith("FINDING: "):
            detail = line[len("FINDING: "):]
            code_name = next((c for prefix, c in GUARD_PREFIXES if detail.startswith(prefix)),
                             f"guard-{name}")
            findings.append((code_name, detail))
    notes = [line[len("note: "):] for line in lines if line.startswith("note: ")]
    if error:
        findings.append(("guard-error", f"private_guard {name} did not run: {error}"))
    elif code == 1 and not findings:
        findings.append(("guard-error", f"private_guard {name} exited with status 1 "
                                        "without a finding line"))
    elif code not in (0, 1):
        findings.append(("guard-error", f"private_guard {name} exited with status {code}"))
    facts = {}
    if name == "postflight":
        facts["excluded_systemd_folders"] = sum(
            1 for note in notes if note.startswith(ctx.guard.EXCLUDED))
    return steps.add(name, "ok" if code == 0 and not findings else "finding", exit_code=code,
                     facts=facts, findings=findings, notes=notes, output=output,
                     duration=time.monotonic() - started)


def run_dump(ctx, steps, run_dir, env, state):
    """`rexglue vfs dump <image> <game folder>` in the sandbox, with its stdout and stderr
    in the run folder. A non-zero status, a signal, a time-out or an interruption is a
    finding. Nothing is deleted after a failure. ReXGlue removes the entries it wrote itself
    when the extraction fails, and keeps the game folder (src/filesystem/container.cpp)."""
    rexglue = os.path.join(ctx.sdk, "bin", "rexglue")
    command = [rexglue, "vfs", "dump", ctx.iso, ctx.game]
    findings, facts = [], {}
    started = time.monotonic()
    code = None
    with open(os.path.join(run_dir, "vfs-dump.stdout"), "xb") as out, \
            open(os.path.join(run_dir, "vfs-dump.stderr"), "xb") as err:
        try:
            box = Sandbox(ctx, run_dir, command, env, out, err)
        except OSError as exc:
            findings.append(("dump-not-started", f"bubblewrap did not start "
                                                 f"({exc.strerror})"))
            return steps.add("vfs-dump", "ok", facts=facts, findings=findings)
        deadline = time.monotonic() + ctx.args.timeout
        try:
            state.update(phase="extracting", bwrap_pid=box.proc.pid,
                         bwrap_start=process_start(box.proc.pid))
            write_state(run_dir, state)
            while code is None:
                try:
                    code = box.proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    if time.monotonic() > deadline:
                        SIGNALS.defer = True
                        code = box.stop()
                        findings.append(("dump-timeout", f"stopped after "
                                                         f"{ctx.args.timeout} s"))
        except Interrupted:
            SIGNALS.defer = True
            code = box.stop()
            findings.append(("interrupted", "the extraction was interrupted and stopped"))
        finally:
            SIGNALS.defer = True
            if box.proc.poll() is None:
                code = box.stop()
                findings.append(("interrupted", "the extraction was stopped by an error of "
                                                "the tool"))
            state["sandbox_child"] = box.child_pid()
            box.close()
    statuses = [d.get("exit-code") for d in box.documents() if isinstance(d, dict)]
    inner = next((s for s in statuses if isinstance(s, int)), None)
    final = inner if inner is not None else code
    if isinstance(final, int) and final < 0:
        final = 128 - final
    if isinstance(final, int) and final > 128 and not findings:
        findings.append(("dump-crashed", f"killed by signal {final - 128}"))
        facts["signal"] = final - 128
    elif final not in (None, 0) and not findings:
        findings.append(("dump-failed", f"exited with status {final}"))
    block = dump_block(run_dir)
    if block.get("type") in ("GDFX", "STFS", "SVOD"):
        facts["type"] = block["type"]
    if block.get("nodes", "").isdigit():
        facts["nodes"] = int(block["nodes"])
    state.update(phase="extracted", dump_status=final)
    write_state(run_dir, state)
    return steps.add("vfs-dump", "ok", exit_code=final, facts=facts, findings=findings,
                     output="vfs-dump.stdout, vfs-dump.stderr",
                     duration=time.monotonic() - started)


def check_sdk_before(ctx, started_ns, findings):
    """The SDK was built before the controls started: its status change times precede
    them. A build or a change during the step would also write elsewhere."""
    for path in (ctx.sdk, os.path.join(ctx.sdk, "bin"), os.path.join(ctx.sdk, "bin",
                                                                       "rexglue")):
        try:
            st = os.lstat(path)
        except OSError as exc:
            findings.append(("sdk-changed", f"the SDK cannot be read: {path} "
                                            f"({exc.strerror})"))
            continue
        if st.st_ctime_ns >= started_ns:
            findings.append(("sdk-changed", f"changed after the controls started: {path}"))


def pb1_figures(ctx, steps, before=None, after=None, block=None, j0_sha256=None):
    """Compares the extracted tree with the references. The summary shows numbers for the
    counts, and only `match` or `DIFFERS` for the hashes."""
    reference = ctx.reference
    figures = survey_tree(ctx.game, reference["modules"])
    rows = []

    def row(name, expected, found, met=None, show=True):
        rows.append({"name": name, "expected": expected, "found": found,
                     "met": expected == found if met is None else bool(met), "show": show})

    row("files", reference["files"], figures["files"])
    row("directories (root not counted)", reference["directories"], figures["directories"])
    row("anomalies in the tree", 0, len(figures["anomalies"]))
    for key, expected in reference["modules"].items():
        module = figures["modules"].get(key, {})
        row(f"{key} sha256 = reference", expected, module.get("sha256", module.get(
            "status", "absent")), show=False)
    if before is not None:
        row("image unchanged (sha256 and identity, before and after)", None, None,
            met=after is not None and after == before, show=False)
        if j0_sha256:
            row("image sha256 = local J0 report, before and after", None, None,
                met=after is not None and before["sha256"] == j0_sha256 == after["sha256"],
                show=False)
    if block is not None:
        # Nodes counts the root of the container as well (src/filesystem/container.cpp).
        value = block.get("nodes", "")
        row("ReXGlue nodes = files + directories + root",
            figures["files"] + figures["directories"] + 1,
            int(value) if value.isdigit() else -1)
        row("ReXGlue container type is GDFX", None, None, met=block.get("type") == "GDFX",
            show=False)
    facts = {"files": figures["files"], "directories": figures["directories"],
             "hidden_names": figures["hidden_names"], "anomalies": len(figures["anomalies"]),
             "bytes": figures["bytes"]}
    findings = [("pb1-differs", f"PB-1 figure differs: {r['name']}") for r in rows
                if not r["met"]]
    findings += [("tree-anomaly", f"{kind}: {path}") for kind, path in figures["anomalies"]]
    item = steps.add("pb1-figures", "ok", facts=facts, findings=findings)
    item["criteria"] = rows
    item["modules"] = figures["modules"]
    item["reference"] = reference.get("source", "")
    return item


# --- reports (R04) ------------------------------------------------------------------------

def summary_text(ctx, steps, command, started, pb1=None):
    """Only allowlisted fields: step names, statuses and exit codes, the facts of
    SUMMARY_FACTS that pass their validator, finding codes and their counts, and the PB-1
    rows. No path, no free text from a command, an argument or an exception, and no hash of
    the image: report.json keeps them."""
    lines = ["fifa2010wc B1 summary: allowlisted metadata only. Review it before sharing it "
             "(CP-5).",
             f"tool: b1_extract version {TOOL_VERSION}, command {command}",
             f"started: {utc_stamp(started)}"]
    codes = steps.codes()
    lines.append(f"outcome: {'FINDINGS (' + str(len(codes)) + ')' if codes else 'no finding'}")
    lines.append("steps:")
    for item in steps.items:
        name = item["step"] if item["step"] in STEP_NAMES else "invalid-step"
        status = item["status"] if item["status"] in STATUSES else "invalid"
        code = item.get("exit_code")
        code_text = f"exit {code}" if _int(code) or (isinstance(code, int) and
                                                     -64 <= code < 0) else ""
        facts = []
        for key, validator in SUMMARY_FACTS.get(name, {}).items():
            if key not in item["facts"]:
                continue
            value = item["facts"][key]
            if not validator(value):
                facts.append(f"{key} invalid")
            elif isinstance(value, list):
                facts.append(f"{key} {','.join(value) or '-'}")
            else:
                facts.append(f"{key} {value}")
        lines.append(f"  {name:<20} {status:<8} {code_text:<8} {', '.join(facts)}".rstrip())
        counts = {}
        for finding in item["findings"]:
            counts[finding["code"]] = counts.get(finding["code"], 0) + 1
        for finding_code, count in counts.items():
            if finding_code in FINDING_CODES:
                lines.append(f"      finding {finding_code} (x{count})")
        if item["notes"]:
            lines.append(f"      notes: {len(item['notes'])}")
    if pb1 is not None:
        source = "J0 report" if ctx.reference is J0_REFERENCE else "--reference test file"
        lines.append(f"PB-1 figures (reference: {source}):")
        for row in pb1["criteria"]:
            mark = "match" if row["met"] else "DIFFERS"
            if row["show"] and _int(row["expected"]) and isinstance(row["found"], int):
                found = "not found" if row["found"] == -1 else row["found"]
                lines.append(f"  {row['name']}: expected {row['expected']}, found "
                             f"{found}: {mark}")
            else:
                lines.append(f"  {row['name']}: {mark}")
        hidden = pb1["facts"].get("hidden_names", 0)
        lines.append(f"  names starting with a dot: {hidden if _int(hidden) else 'invalid'} "
                     "(counted)")
    lines.append("decision: this tool does not declare PB-1; the orchestrator decides.")
    if codes:
        lines.append("STOP: a finding stops B1. Delete nothing; keep the local evidence; "
                     "report the summary.")
    return "\n".join(lines) + "\n"


def finish(ctx, steps, command, started, run_dir=None, pb1=None, state=None, suffix=""):
    summary = summary_text(ctx, steps, command, started, pb1)
    if run_dir:
        report = {"tool": {"name": "b1_extract", "version": TOOL_VERSION},
                  "command": command, "started": utc_stamp(started),
                  "finished": utc_stamp(), "steps": steps.items}
        write_new(os.path.join(run_dir, f"report{suffix}.json"),
                  json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        write_new(os.path.join(run_dir, f"summary{suffix}.txt"), summary)
        if state is not None:
            state["phase"] = "complete"
            # A rehearsal proves option B only if nothing but the extraction gates came up.
            state["controls_clean"] = all(code in EXTRACTION_GATES for code in steps.codes())
            write_state(run_dir, state)
    sys.stdout.write(summary)
    if run_dir and RUN_DIR_RE.fullmatch(os.path.basename(run_dir)):
        rel = "$WC2010_PRIVATE_DIR/logs/" + os.path.basename(run_dir)
        print(f"local report: {rel}/report{suffix}.json (do not share)")
        print(f"summary: {rel}/summary{suffix}.txt")
    return 1 if steps.has_findings() else 0


def new_run_dir(ctx, command):
    name = f"b1-{command}-{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}"
    path = os.path.join(ctx.logs, name)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        raise UsageError("a run folder of this second exists: start again in a second")
    return path


# --- commands -----------------------------------------------------------------------------

def prepare_checks(ctx, steps):
    """The checks that write nothing and do not read the image. Returns (watch list,
    relevant mounts, local J0 image hash)."""
    guard_step(ctx, steps, "check-dir", ctx.guard_cmd("check-dir"))

    found = incomplete_runs(ctx)
    steps.add("incomplete-runs", "ok", facts={"incomplete_runs": len(found)},
              findings=[("incomplete-run", f"incomplete: {name} (resume --run-folder "
                                           f"{name})") for name in found])

    findings, notes, facts = [], [], {}
    check_image(ctx, findings, notes, facts)
    steps.add("image", "ok", facts=facts, findings=findings, notes=notes)

    findings, facts = [], {}
    for rel in PRIVATE_COMPONENTS:
        check_component(ctx, rel, findings, required=rel in ("iso", "game", "logs"))
    if not any(code in ("folder-missing", "folder-invalid") for code, _ in findings):
        check_game_empty(ctx, findings, facts)
    steps.add("folders", "ok", facts=facts, findings=findings)

    findings = []
    ancestors = check_ancestors(ctx, findings)
    steps.add("private-tree", "ok", facts={"ancestors_checked": ancestors,
                                           "components_checked": len(PRIVATE_COMPONENTS)},
              findings=findings)

    findings, facts = [], {}
    check_sdk(ctx, findings, facts)
    steps.add("sdk", "ok", facts=facts, findings=findings)

    findings, facts = [], {}
    check_repo(ctx, findings, facts)
    steps.add("repository", "ok", facts=facts, findings=findings)

    mounts, _, error = read_mounts(ctx)
    watch, relevant = [], []
    if error:
        steps.add("mounts", "finding", findings=[("mounts-unavailable", error)])
    else:
        relevant, watch, facts, findings = mount_plan(ctx, mounts)
        steps.add("mounts", "ok", facts=facts, findings=findings)
        findings = []
        count = check_watch_places(ctx, watch, findings)
        steps.add("watched-places", "ok", facts={"places_checked": count},
                  findings=findings)

    findings = []
    facts = core_settings(ctx, findings)
    steps.add("core-settings", "ok", facts=facts, findings=findings)

    findings, facts, notes = [], {}, []
    j0_sha256 = check_j0_report(ctx, findings, facts, notes)
    steps.add("j0-report", "ok", facts=facts, findings=findings, notes=notes)
    return watch, relevant, j0_sha256


def cmd_prepare(ctx):
    steps = Steps(ctx.redact)
    started = time.time()
    prepare_checks(ctx, steps)
    return finish(ctx, steps, "prepare", started)


def cmd_verify(ctx):
    steps = Steps(ctx.redact)
    started = time.time()
    findings = []
    check_component(ctx, "game", findings)
    steps.add("folders", "ok", findings=findings)
    pb1 = pb1_figures(ctx, steps)
    return finish(ctx, steps, "verify", started, pb1=pb1)


def after_checks(ctx, steps, run_dir, state, events=None):
    """The controls after the extraction, also used by `resume`. They only read, and write
    their outputs in the run folder. Returns the PB-1 figures of a run."""
    suffix = "-resume" if state.get("resumed") else ""
    marker = os.path.join(run_dir, "b1.marker")
    if os.path.lexists(marker):
        watches = []
        for place in [ctx.home, ctx.tmp_watch] + state.get("watch", []):
            watches += ["--watch", place]
        post = ctx.guard_cmd("postflight", "--marker", marker, "--sdk", ctx.sdk,
                             "--nix", ctx.args.nix, *watches,
                             *(["--shm-dir", ctx.args.shm_dir] if ctx.args.shm_dir else []))
        guard_step(ctx, steps, "postflight", post, run_dir,
                   env=step_env(ctx, run_dir), cwd=ctx.private,
                   output=f"postflight{suffix}.txt")
    else:
        steps.add("postflight", "skipped", notes=["no marker: nothing was started"])
    state["phase"] = "postflight"
    write_state(run_dir, state)

    mounts, raw, error = read_mounts(ctx)
    if error:
        steps.add("mounts-after", "finding", findings=[("mounts-unavailable", error)])
    else:
        write_new(os.path.join(run_dir, f"mounts-after{suffix}.json"), raw)
        relevant, _, _, _ = mount_plan(ctx, mounts)
        facts, findings = compare_mounts(state.get("mounts_before", []), relevant)
        moved = events.changed() if events is not None else None
        facts["mount_events"] = bool(moved) if moved is not None else True
        if moved is None:
            findings.append(("mount-events", "the mount events could not be watched for "
                                             "this period"))
        elif moved and not findings:
            findings.append(("mount-events", "the mount table changed during the step; a "
                                             "mount undone since cannot be ruled out"))
        steps.add("mounts-after", "ok", facts=facts, findings=findings,
                  output=f"mounts-after{suffix}.json")

    entries, raw, error = coredumps_since(ctx, state["started"])
    write_new(os.path.join(run_dir, f"coredumps{suffix}.txt"), raw)
    core = state.get("core", {})
    if error and error.startswith("command not found") and \
            core.get("core_pattern_kind") == "file":
        steps.add("core-dumps", "skipped", notes=["coredumpctl not found; core dumps go to "
                                                  "a file, which RLIMIT_CORE 0 prevents"])
    elif error:
        steps.add("core-dumps", "finding", findings=[("coredumpctl-failed", error)])
    else:
        # The synthetic crash of the core probe (rehearse) is expected, and left out.
        probe_pids = set(state.get("core_probe_pids", []))
        notes = [f"synthetic crash of the core probe left out (pid {e.get('pid')})"
                 for e in entries if e.get("pid") in probe_pids]
        entries = [e for e in entries if e.get("pid") not in probe_pids]
        steps.add("core-dumps", "ok", facts={"core_dumps_since_start": len(entries)},
                  findings=[("core-dump-recorded", f"{len(entries)} entries since the start "
                                                   "(keep them local)")] if entries else [],
                  notes=notes)

    after_store, code, findings, facts, seconds = store_survey(ctx, run_dir,
                                                               f"cp3-after{suffix}")
    before_store = set(state.get("store_before", []))
    new = sorted(after_store - before_store)
    gone = sorted(before_store - after_store)
    findings += [("cp3-new-match", f"new match in the store: {path}") for path in new]
    facts.update({"new_matches": len(new), "gone_matches": len(gone)})
    steps.add("cp3-after", "ok", exit_code=code, facts=facts, findings=findings,
              notes=[f"match gone: {path}" for path in gone],
              output=f"cp3-after{suffix}.txt", duration=seconds)

    after_ids = private_identities(ctx, run_dir)
    findings = compare_identities(state.get("identities", {}), after_ids)
    steps.add("private-tree-after", "ok", facts={"replaced": len(findings)},
              findings=findings)

    pb1 = None
    if state.get("command") == "run" and state.get("image_before"):
        before = state["image_before"]
        j0_sha256 = state.get("j0_sha256")
        started = time.monotonic()
        try:
            after = image_state(ctx.iso)
            facts = {"image_unchanged": after == before}
            findings = [] if after == before else [("image-changed", "the disc image "
                                                    "changed during the step")]
            if j0_sha256:
                facts["image_matches_j0_report"] = after["sha256"] == j0_sha256
                if after["sha256"] != j0_sha256:
                    findings.append(("j0-image-mismatch", "after the step"))
            steps.add("image-after", "ok", facts=facts, findings=findings,
                      duration=time.monotonic() - started)
        except OSError as exc:
            after = None
            steps.add("image-after", "finding",
                      findings=[("image-unreadable", f"after the step ({exc.strerror})")])
        if state.get("phase_reached_extraction"):
            block = dump_block(run_dir)
            pb1 = pb1_figures(ctx, steps, before=before, after=after, block=block,
                              j0_sha256=j0_sha256)
    return pb1


def cmd_step(ctx, extract):
    """`run` (extract=True) and `rehearse` (extract=False)."""
    command = "run" if extract else "rehearse"
    steps = Steps(ctx.redact)
    started = time.time()
    SIGNALS.install()
    try:
        watch, _, j0_sha256 = prepare_checks(ctx, steps)
    except Interrupted:
        steps.add("interrupted", "finding", findings=[("interrupted", "during prepare")])
        return finish(ctx, steps, command, started)
    if steps.blocking(extract):
        print("a check found something: nothing was started, nothing was written.")
        return finish(ctx, steps, command, started)

    # Settings of the step, inherited by every command it starts.
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, SUPERVISOR_CORE_LIMIT)
    run_dir = new_run_dir(ctx, command)
    state = {"tool_version": TOOL_VERSION, "command": command, "started": started,
             "phase": "started", "core": steps.get("core-settings")["facts"],
             "j0_sha256": j0_sha256}
    write_state(run_dir, state)
    pb1 = None
    try:
        make_env_folders(ctx)
        env = step_env(ctx, run_dir)
        events = MountEvents(ctx.args.mountinfo)
        started_ns = time.time_ns()

        findings = []
        for rel in PRIVATE_COMPONENTS:
            check_component(ctx, rel, findings)
        if findings:
            steps.add("private-tree", "finding", findings=findings)
            return finish(ctx, steps, command, started, run_dir, state=state)

        mounts, raw, error = read_mounts(ctx)
        if error:
            steps.add("mounts-before", "finding", findings=[("mounts-unavailable", error)])
            return finish(ctx, steps, command, started, run_dir, state=state)
        write_new(os.path.join(run_dir, "mounts-before.json"), raw)
        relevant, watch, facts, findings = mount_plan(ctx, mounts)
        if events.fd is None:
            findings.append(("mount-events", f"cannot watch the mount events "
                                             f"({events.error})"))
        state.update(mounts_before=relevant, watch=watch)
        steps.add("mounts-before", "ok", facts={k: facts[k] for k in (
            "mounts_in_scope", "mount_points_watched")}, findings=findings,
            output="mounts-before.json")

        run_probe(ctx, steps, run_dir, env)
        if not extract and state["core"].get("core_pattern_kind") == "pipe" and \
                not steps.blocking(extract):
            run_core_probe(ctx, steps, run_dir, state)
        if steps.blocking(extract):
            return finish(ctx, steps, command, started, run_dir, state=state)

        if extract:
            t = time.monotonic()
            try:
                before = image_state(ctx.iso)
                state["image_before"] = before
                facts, findings = {}, []
                if j0_sha256:
                    facts["image_matches_j0_report"] = before["sha256"] == j0_sha256
                    if before["sha256"] != j0_sha256:
                        findings.append(("j0-image-mismatch", "before the step"))
                else:
                    findings.append(("j0-report-absent", "no image hash to compare with"))
                steps.add("image-before", "ok", facts=facts, findings=findings,
                          duration=time.monotonic() - t)
            except OSError as exc:
                steps.add("image-before", "finding",
                          findings=[("image-unreadable", f"before the step ({exc.strerror})")])

        store_before, code, findings, facts, seconds = store_survey(ctx, run_dir,
                                                                    "cp3-before")
        state["store_before"] = sorted(store_before)
        steps.add("cp3-before", "ok", exit_code=code, facts=facts, findings=findings,
                  output="cp3-before.txt", duration=seconds)
        state["identities"] = private_identities(ctx, run_dir)
        write_state(run_dir, state)
        if steps.blocking(extract):
            return finish(ctx, steps, command, started, run_dir, state=state)

        marker = os.path.join(run_dir, "b1.marker")
        dests = []
        for path in [run_dir] + [os.path.join(ctx.private, n) for n in SANDBOX_WRITABLE]:
            dests += ["--dest", path]
        pre = ctx.guard_cmd("preflight", *dests, "--game-root", ctx.game,
                            "--sdk-bin", os.path.join(ctx.sdk, "bin"), "--marker", marker,
                            *(["--shm-dir", ctx.args.shm_dir] if ctx.args.shm_dir else []))
        item = guard_step(ctx, steps, "preflight", pre, run_dir, env=env, cwd=ctx.private)
    except Interrupted:
        steps.add("interrupted", "finding", findings=[("interrupted", "before the marker")])
        return finish(ctx, steps, command, started, run_dir, state=state)
    except Exception as exc:  # nothing was started: the report is still written
        steps.add("internal-error", "finding", findings=[("internal-error",
                                                          type(exc).__name__)])
        return finish(ctx, steps, command, started, run_dir, state=state)

    # From here on, the marker decides: if it exists, postflight runs, whatever happens.
    if not os.path.lexists(marker):
        if item["status"] == "ok":
            steps.add("before-extraction", "finding",
                      findings=[("preflight-no-marker", "preflight passed without a "
                                                        "marker")])
        steps.add("postflight", "skipped", notes=["no marker: nothing was started"])
        return finish(ctx, steps, command, started, run_dir, state=state)
    SIGNALS.defer = False
    state["phase"] = "marker"
    write_state(run_dir, state)
    try:
        findings = []
        check_sdk_before(ctx, started_ns, findings)
        check_game_empty(ctx, findings, {})
        if extract and not find_core_proof(ctx, core_identity(
                ctx.args.core_pattern_file, ctx.args.suid_dumpable_file)):
            findings.append(("core-changed", "the proof no longer holds for this boot, "
                                             "kernel and setting"))
        findings += compare_identities(state["identities"], private_identities(ctx, run_dir))
        steps.add("before-extraction", "ok", findings=findings)
        if not extract:
            steps.add("vfs-dump", "skipped", notes=["rehearsal: no extraction"])
        elif steps.blocking(extract):
            steps.add("vfs-dump", "skipped", notes=["not started: a check found something"])
        else:
            state["phase_reached_extraction"] = True
            run_dump(ctx, steps, run_dir, env, state)
    except Interrupted:
        steps.add("interrupted", "finding", findings=[("interrupted", "before the "
                                                                      "extraction")])
    except Exception as exc:  # the controls must still run
        steps.add("internal-error", "finding", findings=[("internal-error",
                                                          type(exc).__name__)])
    SIGNALS.defer = True
    try:
        pb1 = after_checks(ctx, steps, run_dir, state, events)
    except Exception as exc:  # the report is still written
        steps.add("internal-error", "finding", findings=[("internal-error",
                                                          type(exc).__name__)])
    if SIGNALS.count:
        steps.add("interrupted", "finding", facts={"signals": SIGNALS.count},
                  findings=[("interrupted", f"{SIGNALS.count} signal(s) received; the "
                                            "controls were finished")])
    return finish(ctx, steps, command, started, run_dir, pb1=pb1, state=state)


def cmd_resume(ctx):
    """The controls after the extraction for a run whose supervisor stopped. The extraction
    is never started again, and nothing is deleted."""
    steps = Steps(ctx.redact)
    started = time.time()
    name = ctx.args.run_folder or ""
    if not RUN_DIR_RE.fullmatch(name):
        raise UsageError("--run-folder takes the name of a run folder, b1-run-<UTC time>")
    run_dir = os.path.join(ctx.logs, name)
    state = read_state(run_dir)
    if not state or state.get("phase") == "complete" or \
            state.get("tool_version") != TOOL_VERSION:
        raise UsageError("this run folder has no incomplete state to resume")
    SIGNALS.install()
    SIGNALS.defer = True
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, SUPERVISOR_CORE_LIMIT)
    pid, start = state.get("bwrap_pid"), state.get("bwrap_start")
    if pid and start and process_start(pid) == start:
        steps.add("resume", "finding", findings=[("still-running", "the sandbox of the "
                                                                    "extraction is alive")])
        return finish(ctx, steps, "resume", started)
    state["resumed"] = True
    if state.get("phase") == "started" and not os.path.lexists(
            os.path.join(run_dir, "b1.marker")):
        steps.add("resume", "finding", findings=[("interrupted", "stopped before the "
                                                                  "marker: nothing was "
                                                                  "started")])
        return finish(ctx, steps, "resume", started, run_dir, state=state, suffix="-resume")
    steps.add("resume", "ok", notes=[f"phase reached: {state.get('phase')}"])
    if state.get("phase") in ("extracting",):
        steps.add("vfs-dump", "finding", findings=[("interrupted", "the extraction did not "
                                                                   "finish")])
    try:
        pb1 = after_checks(ctx, steps, run_dir, state)
    except Exception as exc:
        pb1 = None
        steps.add("internal-error", "finding", findings=[("internal-error",
                                                          type(exc).__name__)])
    return finish(ctx, steps, "resume", started, run_dir, pb1=pb1, state=state,
                  suffix="-resume")


def main(argv):
    if argv[:1] == ["_probe"]:
        return probe_main(argv[1:])
    if argv[:1] == ["_crash"]:
        return crash_main(argv[1:])
    parser = argparse.ArgumentParser(
        prog="b1_extract",
        description="J2 step B1: controlled extraction of the disc tree with rexglue vfs "
                    "dump, on the user's machine (docs/J2_B1_EXTRACTION.md).")
    parser.add_argument("--private-dir", default=os.environ.get("WC2010_PRIVATE_DIR"),
                        help="private folder (default: $WC2010_PRIVATE_DIR)")
    parser.add_argument("--repo", help="the project repository, which must stay unchanged")
    parser.add_argument("--sdk", help="store path of the ReXGlue SDK, built beforehand")
    parser.add_argument("--guard", default=DEFAULT_GUARD, help="path of private_guard.py")
    parser.add_argument("--j0-report", help="the local J0 report (JSON); default: "
                                            f"$WC2010_PRIVATE_DIR/{DEFAULT_J0_REPORT}")
    parser.add_argument("--timeout", type=int, default=DUMP_TIMEOUT,
                        help=f"seconds before rexglue is stopped (default {DUMP_TIMEOUT})")
    parser.add_argument("--run-folder", help="resume: the run folder to finish")
    # Commands, files and references replaced by the tests (tools/test_b1_extract.py).
    for name, default in (("--git", "git"), ("--nix", "nix"), ("--find", "find"),
                          ("--findmnt", "findmnt"), ("--coredumpctl", "coredumpctl"),
                          ("--bwrap", "bwrap"), ("--store-dir", "/nix/store"),
                          ("--tmp-watch", "/tmp"), ("--shm-dir", None),
                          ("--reference", None),
                          ("--mountinfo", "/proc/self/mountinfo"),
                          ("--core-pattern-file", "/proc/sys/kernel/core_pattern"),
                          ("--suid-dumpable-file", "/proc/sys/fs/suid_dumpable")):
        parser.add_argument(name, default=default, help=argparse.SUPPRESS)
    parser.add_argument("command", choices=("prepare", "rehearse", "run", "verify", "resume"))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    if os.geteuid() == 0:
        print("FINDING root: B1 never runs as root (a root rexglue can write into "
              "/nix/store, docs/J2_A1_SDK_INVENTORY.md section 2)")
        return 1
    try:
        ctx = Context(args)
        if args.command == "prepare":
            return cmd_prepare(ctx)
        if args.command == "verify":
            return cmd_verify(ctx)
        if args.command == "resume":
            return cmd_resume(ctx)
        return cmd_step(ctx, extract=args.command == "run")
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Step B1 of the J2 plan (docs/J2_PLAN.md section 4.1, ticket #32): extract the disc tree
with `rexglue vfs dump` into the private folder, between the CP-3 and CP-4 controls, then
compare the result with the J0 references for PB-1 (docs/J2_B1_EXTRACTION.md).

It is run by hand on the user's machine, after PB-0 (D-017). It never decodes a module, and
it never deletes, moves or overwrites anything. It never declares PB-1: the orchestrator
decides from the summary.

Commands:
  prepare   No extraction: it writes nothing and does not read the disc image.
            - CP-1 with private_guard check-dir.
            - iso/fifa2010wc.iso is a read-only regular file in iso/.
            - game/ and logs/ are real folders of the private folder, not links or mount
              points, and game/ is empty.
            - The SDK is built: a store path with bin/rexglue.
            - The repository is clean.
            - The watched places (the home folder, /tmp and the mount points under them,
              from findmnt) are readable folders.
            - It reports how the kernel handles core dumps.
  rehearse  The controls of `run`, without the extraction and without reading the image.
  run       prepare; then the image hash, CP-3, the mount points and preflight with the
            marker; the extraction; postflight, in every case once the marker exists; then
            the mount points, the core dumps, CP-3 and the image hash again, and the PB-1
            figures.
  verify    The PB-1 figures of the extracted tree, read only. Writes nothing.

Every step gets a status and, for a command, its exit status. A check that cannot run is a
finding. rehearse and run write only in a new folder,
$WC2010_PRIVATE_DIR/logs/b1-<command>-<UTC time>:
- report.json: every step and finding, for local use only;
- summary.txt: metadata only (numbers, statuses, allowed hashes). Review it before sharing
  anything (CP-5);
- the outputs of private_guard, find and rexglue, and the ReXGlue log.
The console shows the summary only.

Exit status: 0 when every step passes (and, for run and verify, the PB-1 figures match),
1 on a finding, 2 on usage error. Only the Python standard library is used. Run it with
`python3 -I`.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import resource
import stat
import subprocess
import sys
import time

TOOL_VERSION = 1
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GUARD = os.path.join(HERE, "private_guard.py")
ISO_NAME = "fifa2010wc.iso"
SDK_SUFFIX = "-rexglue-sdk-0.11.0"
# PB-1 references (docs/reports/J0_IDENTIFICATION.md section 2). The J0 tool counts the
# entries below the root of the disc: the root folder is not one of the 8 folders.
J0_REFERENCE = {
    "source": "docs/reports/J0_IDENTIFICATION.md section 2 (built in)",
    "files": 49,
    "directories": 8,
    "modules": {
        "default.xex": "dce08ce39dd11a6f45c74064d8f6c181326de1999b86bbd4ddcaf0feaa6de287",
        "fifadllzf.xex": "788474d3ee970d1777bbaf2f2ef950e937dd56ac7fc57a5a9e5c0d2874736485",
    },
}
# The folders of the step's environment (docs/J2_PHASE_B_CONTROLS.md section 2), and
# ReXGlue's log, written into the run folder.
ENV_FOLDERS = (("TMPDIR", "tmp"), ("XDG_CONFIG_HOME", "xdg/config"),
               ("XDG_DATA_HOME", "xdg/data"), ("XDG_CACHE_HOME", "xdg/cache"),
               ("REX_APP_ROOT", "app"))
# Every place the step may write, declared to preflight (docs/J2_B1_EXTRACTION.md
# section 2): the tree, the run folder with the ReXGlue log, ReXGlue's application folder,
# and TMPDIR.
DESTINATIONS = ("game", "logs", "app", "tmp")
# The store entry already found by CP-3 before PB-0: never opened, never deleted.
KNOWN_STORE_ENTRY = "nl2dwawyxdkljdkiay1nd4fiwp98qckw-claude"
DUMP_TIMEOUT = 7200
# The summary block that `rexglue vfs dump` writes on stderr
# (src/rexglue/command/vfs_command.cpp). Nodes counts the root of the container too. The
# Source row names the image path, so it is never read here.
BLOCK_RE = re.compile(r"^\s+(Type|Nodes|Bytes):\s+(\S+)\s*$", re.MULTILINE)
CORE_PATTERN = "/proc/sys/kernel/core_pattern"
SUID_DUMPABLE = "/proc/sys/fs/suid_dumpable"


class UsageError(Exception):
    pass


def load_guard(guard_path):
    """private_guard as a module, for its path helpers. No bytecode is written next to it."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("private_guard", guard_path)
    if spec is None or spec.loader is None or not os.path.isfile(guard_path):
        raise UsageError(f"cannot load private_guard from {guard_path}")
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


class Redactor:
    """Replaces the private folder, the repository and the home folder in a text by their
    names, so that a shared line names no local path."""

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


def finding_kind(text):
    """The kind of a finding, without the path or the name it may hold: the words before
    the first colon. Only kinds and counts go into the summary."""
    return text.split(": ", 1)[0].strip()


class Steps:
    def __init__(self, redact):
        self.items = []
        self.redact = redact

    def add(self, name, status, exit_code=None, facts=None, findings=(), notes=(),
            output=None, duration=None):
        item = {"step": name, "status": status}
        if exit_code is not None:
            item["exit_code"] = exit_code
        if duration is not None:
            item["seconds"] = round(duration, 1)
        item["facts"] = dict(facts or {})
        item["findings"] = [self.redact(text) for text in findings]
        item["notes"] = [self.redact(text) for text in notes]
        if output:
            item["output"] = output
        if findings and status == "ok":
            item["status"] = "finding"
        self.items.append(item)
        return item

    def has_findings(self):
        return any(item["status"] == "finding" for item in self.items)

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
            raise UsageError(f"the private folder is not an absolute path: "
                             f"{args.private_dir}")
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
        self.reference = J0_REFERENCE
        if args.reference:
            # Test references only. The summary says so, whatever the file claims.
            try:
                with open(args.reference, encoding="utf-8") as f:
                    reference = json.load(f)
                self.reference = {"files": int(reference["files"]),
                                  "directories": int(reference["directories"]),
                                  "modules": dict(reference["modules"])}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise UsageError(f"unreadable --reference file ({type(exc).__name__})")
            self.reference["source"] = ("--reference file, not the J0 report: "
                                        + str(reference.get("source", "no source given")))

    def guard_cmd(self, *rest):
        cmd = [sys.executable, "-I", self.guard_path, "--private-dir", self.private]
        if self.repo:
            cmd += ["--repo", self.repo]
        cmd += ["--git", self.args.git]
        return cmd + list(rest)

    def tops(self):
        """The places postflight searches: the repository, the home folder and /tmp."""
        tops = [self.home, self.tmp_watch]
        if self.repo:
            tops.append(self.repo)
        return tops


# --- running commands -------------------------------------------------------------------

def run_capture(argv, env=None, cwd=None, timeout=600):
    """Runs argv and returns (exit_code, stdout bytes, stderr bytes, error). exit_code is
    None, with an error text, when the command could not run or timed out."""
    try:
        result = subprocess.run(argv, capture_output=True, env=env, cwd=cwd,
                                timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return None, b"", b"", f"command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return None, b"", b"", f"timed out after {timeout} s: {os.path.basename(argv[0])}"
    except OSError as exc:
        return None, b"", b"", f"cannot run {argv[0]} ({exc.strerror or exc})"
    return result.returncode, result.stdout, result.stderr, None


def write_new(path, data):
    """Creates `path` with mode 0600; never overwrites and never follows a link."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600)
    with open(fd, "wb") as f:
        f.write(data)


def parse_guard_output(text):
    findings = [line[len("FINDING: "):] for line in text.splitlines()
                if line.startswith("FINDING: ")]
    notes = [line[len("note: "):] for line in text.splitlines() if line.startswith("note: ")]
    return findings, notes


def guard_step(ctx, steps, name, argv, run_dir=None, env=None, cwd=None):
    """Runs one private_guard command. Its exit status is kept as it is: 0 passes, 1 is a
    finding, any other status or a failure to run is a finding too."""
    started = time.monotonic()
    code, out, err, error = run_capture(argv, env=env, cwd=cwd, timeout=7200)
    text = os.fsdecode(out) + os.fsdecode(err)
    output = None
    if run_dir:
        output = f"{name}.txt"
        write_new(os.path.join(run_dir, output), text)
    findings, notes = parse_guard_output(text)
    if error:
        findings.append(f"private_guard {name} did not run: {error}")
    elif code == 1 and not findings:
        findings.append(f"private_guard {name} exited with status 1 without a finding line")
    elif code not in (0, 1):
        findings.append(f"private_guard {name} exited with status {code}")
    excluded = sum(1 for note in notes if note.startswith(ctx.guard.EXCLUDED))
    facts = {"excluded_systemd_folders": excluded} if name == "postflight" else {}
    return steps.add(name, "ok" if code == 0 and not findings else "finding", exit_code=code,
                     facts=facts, findings=findings, notes=notes, output=output,
                     duration=time.monotonic() - started)


# --- prepare ----------------------------------------------------------------------------

def check_real_folder(ctx, name, findings, facts, required=True):
    """A folder of the private folder that this step uses: a real folder, not a link, on
    the same file system as the private folder, owned by the user."""
    path = os.path.join(ctx.private, name)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        if required:
            findings.append(f"missing folder: {name}/ (CP-1, docs/J2_PHASE_B_CONTROLS.md §1)")
        return None
    except OSError as exc:
        findings.append(f"cannot read the folder's metadata: {name}/ ({exc.strerror})")
        return None
    if stat.S_ISLNK(st.st_mode):
        findings.append(f"symbolic link where a folder is expected: {name}/ (it must be a "
                        "real folder of the private folder)")
        return None
    if not stat.S_ISDIR(st.st_mode):
        findings.append(f"not a folder: {name}/")
        return None
    if st.st_dev != os.lstat(ctx.private).st_dev:
        findings.append(f"mount point where a dedicated folder is expected: {name}/")
    if st.st_uid != os.geteuid():
        findings.append(f"folder of another user: {name}/ (uid {st.st_uid})")
    facts[f"{name}_mode"] = f"{stat.S_IMODE(st.st_mode):04o}"
    return st


def check_image(ctx, findings, notes, facts):
    rel = f"iso/{ISO_NAME}"
    try:
        st = os.lstat(ctx.iso)
    except FileNotFoundError:
        findings.append(f"disc image absent: {rel}")
        return
    except OSError as exc:
        findings.append(f"cannot read the image's metadata: {rel} ({exc.strerror})")
        return
    if stat.S_ISLNK(st.st_mode):
        findings.append(f"the disc image is a symbolic link: {rel} (copy the image itself "
                        "into iso/)")
        return
    if not stat.S_ISREG(st.st_mode):
        findings.append(f"the disc image is not a regular file: {rel}")
        return
    if os.path.realpath(ctx.iso) != ctx.iso:
        findings.append(f"the disc image is not at its canonical path: {rel}")
    if st.st_mode & 0o222:
        findings.append(f"writable disc image: {rel} (chmod a-w)")
    elif os.access(ctx.iso, os.W_OK):
        findings.append(f"the disc image can be written by this user: {rel} (access control "
                        "list?)")
    if not os.access(ctx.iso, os.R_OK):
        findings.append(f"the disc image cannot be read: {rel}")
    if st.st_size == 0:
        findings.append(f"empty disc image: {rel}")
    if st.st_nlink > 1:
        notes.append(f"the disc image has {st.st_nlink} hard links: the same file may have "
                     "another name outside the private folder")
    facts.update({"image_size": st.st_size, "image_mode": f"{stat.S_IMODE(st.st_mode):04o}",
                  "image_hard_links": st.st_nlink})


def check_game_empty(ctx, findings, facts):
    try:
        names = os.listdir(ctx.game)
    except OSError as exc:
        findings.append(f"cannot list game/ ({exc.strerror})")
        return
    facts["game_entries"] = len(names)
    if names:
        findings.append(f"game/ is not empty: {len(names)} entr{'y' if len(names) == 1 else 'ies'} "
                        "(B1 extracts into an empty folder only; this tool never overwrites "
                        "or deletes anything)")


def check_sdk(ctx, findings, facts):
    if not ctx.sdk:
        findings.append("no SDK given (--sdk)")
        return
    if os.path.dirname(ctx.sdk) != ctx.store:
        findings.append(f"the SDK is not a store path of {ctx.store}: {ctx.sdk}")
        return
    if not os.path.basename(ctx.sdk).endswith(SDK_SUFFIX):
        findings.append(f"the SDK is not ReXGlue 0.11.0: {os.path.basename(ctx.sdk)}")
    try:
        st = os.lstat(ctx.sdk)
        rex = os.lstat(os.path.join(ctx.sdk, "bin", "rexglue"))
    except OSError as exc:
        findings.append(f"the SDK is not built: {ctx.sdk} ({exc.strerror}); build it before "
                        "the step: nix build --no-link .#rexglue-sdk")
        return
    if not stat.S_ISDIR(st.st_mode):
        findings.append(f"the SDK is not a folder: {ctx.sdk}")
    if not stat.S_ISREG(rex.st_mode) or not rex.st_mode & 0o111:
        findings.append("bin/rexglue of the SDK is not an executable file")
    facts.update({"sdk": os.path.basename(ctx.sdk), "sdk_registered": utc_stamp(
        max(st.st_ctime, rex.st_ctime))})


def check_repo(ctx, findings, facts):
    if not ctx.repo:
        findings.append("no repository given (--repo): postflight must check it")
        return
    code, out, _, error = run_capture([ctx.args.git, "-C", ctx.repo, "status", "--porcelain",
                                       "--untracked-files=all"], timeout=120)
    if error or code != 0:
        findings.append(f"git status failed in the repository ({error or f'status {code}'})")
    else:
        lines = [line for line in os.fsdecode(out).splitlines() if line.strip()]
        facts["repository_changes"] = len(lines)
        if lines:
            findings.append(f"the repository is not clean: {len(lines)} entr"
                            f"{'y' if len(lines) == 1 else 'ies'} (postflight reports each "
                            "one as a change; commit or stash them first)")
    code, out, _, error = run_capture([ctx.args.git, "-C", ctx.repo, "rev-parse", "HEAD"],
                                      timeout=60)
    facts["repository_commit"] = os.fsdecode(out).strip() if code == 0 else "unknown"


def unescape_mount(raw):
    """A TARGET of `findmnt -r`, which writes unsafe bytes as \\xHH."""
    return os.fsdecode(re.sub(rb"\\x([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]),
                              raw))


def list_mounts(ctx):
    """Every mount target, from `findmnt -rn -o TARGET`. Returns (targets, error)."""
    code, out, _, error = run_capture([ctx.args.findmnt, "-rn", "-o", "TARGET"], timeout=60)
    if error:
        return None, error
    if code != 0:
        return None, f"findmnt exited with status {code}"
    return sorted({unescape_mount(line) for line in out.split(b"\n") if line}), None


def watch_plan(ctx, targets):
    """The mount points to watch on their own: the targets strictly under the home folder,
    /tmp or the repository, outside the private folder. A mount point that is not a folder,
    such as a bound file, is searched as an entry of its parent folder. Returns
    (relevant, watch, facts): `relevant` holds every target under those places, for the
    comparison before and after the step."""
    tops = [os.path.realpath(top) for top in ctx.tops()]
    relevant, watch = [], []
    files = inside = 0
    for target in targets:
        if not os.path.isabs(target):
            continue
        target = os.path.normpath(target)
        if not any(strictly_under(target, top) for top in tops):
            continue
        relevant.append(target)
        if ctx.guard.within(target, ctx.private):
            inside += 1
            continue
        try:
            st = os.lstat(target)
        except OSError:
            watch.append(target)  # postflight reports a watched place that is absent
            continue
        if stat.S_ISDIR(st.st_mode):
            watch.append(target)
        else:
            files += 1
    facts = {"mount_points_watched": len(watch), "mount_points_not_folders": files,
             "mount_points_in_private_folder": inside}
    return relevant, watch, facts


def check_watch_places(ctx, findings, facts):
    targets, error = list_mounts(ctx)
    if error:
        findings.append(f"cannot list the mount points: {error}")
        return
    _, watch, plan = watch_plan(ctx, targets)
    facts.update(plan)
    for place in [ctx.home, ctx.tmp_watch] + watch:
        if not os.path.isdir(place):
            findings.append(f"watched place absent or not a folder: {place}")
        elif not os.access(place, os.R_OK | os.X_OK):
            findings.append(f"watched place not readable: {place}")


def core_handling():
    """How the kernel handles a core dump, read from /proc (CP-4, docs/J2_A6_LINUX_GAPS.md
    §5.2). Only the name of a pipe handler is kept, not its path."""
    facts = {}
    try:
        with open(CORE_PATTERN, encoding="utf-8", errors="replace") as f:
            pattern = f.read().strip()
    except OSError:
        return {"core_pattern": "unknown"}
    facts["core_pattern_pipe"] = pattern.startswith("|")
    if pattern.startswith("|"):
        words = pattern[1:].split()
        facts["core_handler"] = os.path.basename(words[0]) if words else ""
    try:
        with open(SUID_DUMPABLE, encoding="utf-8") as f:
            facts["suid_dumpable"] = f.read().strip()
    except OSError:
        facts["suid_dumpable"] = "unknown"
    return facts


def prepare_checks(ctx, steps):
    """The checks of `prepare`, which write nothing and do not read the image."""
    guard_step(ctx, steps, "check-dir", ctx.guard_cmd("check-dir"))

    findings, notes, facts = [], [], {}
    check_image(ctx, findings, notes, facts)
    steps.add("image", "ok", facts=facts, findings=findings, notes=notes)

    findings, facts = [], {}
    check_real_folder(ctx, "iso", findings, facts)
    check_real_folder(ctx, "logs", findings, facts)
    for _, name in ENV_FOLDERS:
        check_real_folder(ctx, name, findings, facts, required=False)
    check_real_folder(ctx, "xdg", findings, facts, required=False)
    if check_real_folder(ctx, "game", findings, facts):
        check_game_empty(ctx, findings, facts)
    steps.add("folders", "ok", facts=facts, findings=findings)

    findings, facts = [], {}
    check_sdk(ctx, findings, facts)
    steps.add("sdk", "ok", facts=facts, findings=findings)

    findings, facts = [], {}
    check_repo(ctx, findings, facts)
    steps.add("repository", "ok", facts=facts, findings=findings)

    findings, facts = [], {}
    check_watch_places(ctx, findings, facts)
    steps.add("watched-places", "ok", facts=facts, findings=findings)

    facts = core_handling()
    notes = []
    if facts.get("core_pattern_pipe"):
        notes.append("core dumps go to a pipe: the kernel ignores ulimit -c 0 and hands a "
                     "crash to the handler, which then honours the limit "
                     "(docs/J2_B1_EXTRACTION.md §5)")
    steps.add("core-dump-setting", "ok", facts=facts, notes=notes)


# --- the step ---------------------------------------------------------------------------

def step_env(ctx):
    """The environment of docs/J2_PHASE_B_CONTROLS.md section 2 for every command of the
    step. ReXGlue settings inherited from the shell (REX_*) are dropped: only the ones set
    here apply."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("REX_")}
    for name, folder in ENV_FOLDERS:
        env[name] = os.path.join(ctx.private, folder)
    env["WC2010_PRIVATE_DIR"] = ctx.private
    env["NO_COLOR"] = "1"
    return env


def make_env_folders(ctx):
    for _, folder in ENV_FOLDERS:
        path = os.path.join(ctx.private, folder)
        os.makedirs(path, mode=0o700, exist_ok=True)


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
        if error:
            findings.append(f"CP-3 search did not run: {error}")
        elif code != 0:
            findings.append(f"CP-3 search exited with status {code} (see {name}.txt)")
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
        return {"status": f"unreadable ({exc.strerror})"}
    digest = hashlib.sha256()
    with open(fd, "rb", buffering=0) as f:
        st = os.fstat(f.fileno())
        if (st.st_dev, st.st_ino) != (listed.st_dev, listed.st_ino):
            return {"status": "changed while counted"}
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return {"status": "hashed", "sha256": digest.hexdigest(), "size": st.st_size}


def dump_block(run_dir):
    """Type, Nodes and Bytes from the summary block of `rexglue vfs dump`."""
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


def run_dump(ctx, steps, run_dir, env):
    """`rexglue vfs dump <image> <game folder>`, with its stdout and stderr in the run
    folder. A non-zero status, a signal, a time-out or an interruption is a finding. Nothing
    is deleted after a failure. ReXGlue removes the entries it wrote itself when the
    extraction fails, and keeps the game folder (src/filesystem/container.cpp)."""
    rexglue = os.path.join(ctx.sdk, "bin", "rexglue")
    argv = [rexglue, "vfs", "dump", ctx.iso, ctx.game]
    findings, facts = [], {}
    started = time.monotonic()
    out_fd = os.open(os.path.join(run_dir, "vfs-dump.stdout"),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    err_fd = os.open(os.path.join(run_dir, "vfs-dump.stderr"),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    code = None
    try:
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out_fd,
                                    stderr=err_fd, env=env, cwd=ctx.private)
        except OSError as exc:
            findings.append(f"rexglue did not start ({exc.strerror or exc})")
            proc = None
        if proc is not None:
            try:
                code = proc.wait(timeout=ctx.args.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait()
                findings.append(f"rexglue vfs dump timed out after {ctx.args.timeout} s and "
                                "was killed")
            except KeyboardInterrupt:
                try:
                    code = proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    code = proc.wait()
                findings.append("rexglue vfs dump was interrupted")
    finally:
        os.close(out_fd)
        os.close(err_fd)
    if code is not None and code < 0:
        findings.append(f"rexglue vfs dump crashed: signal {-code} (check the core dumps; "
                        "docs/J2_B1_EXTRACTION.md §5)")
        facts["signal"] = -code
    elif code not in (None, 0) and not findings:
        findings.append(f"rexglue vfs dump exited with status {code}")
    facts.update(dump_block(run_dir))
    return steps.add("vfs-dump", "ok", exit_code=code, facts=facts, findings=findings,
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
            findings.append(f"the SDK cannot be read: {path} ({exc.strerror})")
            continue
        if st.st_ctime_ns >= started_ns:
            findings.append(f"the SDK changed after the controls started: {path}")


def coredump_check(ctx, since, core):
    """Core dumps recorded since the start of the step, from `coredumpctl list`. Any entry
    is a finding: it is examined locally, never shared."""
    argv = [ctx.args.coredumpctl, "list", "--no-pager", f"--since=@{int(since)}"]
    code, out, err, error = run_capture(argv, timeout=120)
    text = os.fsdecode(out) + os.fsdecode(err)
    facts, findings, notes = {}, [], []
    if error and error.startswith("command not found"):
        if core.get("core_pattern_pipe") and core.get("core_handler") == "systemd-coredump":
            findings.append("coredumpctl not found, although core dumps go to "
                            "systemd-coredump")
        else:
            notes.append("coredumpctl not found: no systemd-coredump record to check")
        return code, text, facts, findings, notes
    if error:
        findings.append(f"coredumpctl did not run: {error}")
    elif code == 1 and "No coredumps found" in text:
        facts["core_dumps_since_start"] = 0
    elif code == 0:
        entries = [line for line in os.fsdecode(out).splitlines()[1:] if line.strip()]
        facts["core_dumps_since_start"] = len(entries)
        findings.append(f"core dump recorded since the start of the step: {len(entries)} "
                        "entr" + ("y" if len(entries) == 1 else "ies") + " (coredumpctl "
                        "list; keep them local)")
    else:
        findings.append(f"coredumpctl exited with status {code}")
    return code, text, facts, findings, notes


def pb1_figures(ctx, steps, before=None, after=None, block=None):
    """Compares the extracted tree with the references. Returns the list of criteria:
    (name, expected, found, met)."""
    reference = ctx.reference
    figures = survey_tree(ctx.game, reference["modules"])
    rows = []

    def row(name, expected, found, met=None):
        rows.append((name, expected, found, expected == found if met is None else met))

    row("files", reference["files"], figures["files"])
    row("directories (root not counted)", reference["directories"], figures["directories"])
    row("anomalies in the tree", 0, len(figures["anomalies"]))
    for key, expected in reference["modules"].items():
        module = figures["modules"].get(key, {})
        row(f"{key} sha256", expected, module.get("sha256", module.get("status", "absent")))
    if before is not None:
        row("image unchanged (sha256 and identity, before and after)", before["sha256"],
            after["sha256"] if after else "not hashed", after == before)
    if block is not None:
        # Nodes counts the root of the container as well (src/filesystem/container.cpp).
        # Bytes is not compared: it adds the size of every node, folder tables included
        # (9197 bytes for 5101 bytes of files in the Nix check b1-extract-selftest).
        value = block.get("nodes", "")
        row("ReXGlue nodes = files + directories + root",
            figures["files"] + figures["directories"] + 1,
            int(value) if value.isdigit() else "not found")
        row("ReXGlue container type", "GDFX", block.get("type", "not found"))
    if ctx.args.j0_report and before is not None:
        rows.append(j0_local_row(ctx, before["sha256"]))
    facts = {"files": figures["files"], "directories": figures["directories"],
             "bytes": figures["bytes"], "hidden_names": figures["hidden_names"],
             "anomalies": len(figures["anomalies"])}
    for key, module in figures["modules"].items():
        facts[key] = module.get("sha256", module.get("status"))
    findings = [f"PB-1 figure differs: {name}" for name, _, _, met in rows if not met]
    findings += [f"tree anomaly: {kind}: {path}" for kind, path in figures["anomalies"]]
    kinds = {}
    for kind, _ in figures["anomalies"]:
        kinds[kind] = kinds.get(kind, 0) + 1
    facts["anomaly_kinds"] = kinds
    item = steps.add("pb1-figures", "ok", facts=facts, findings=findings)
    item["criteria"] = [{"name": name, "expected": expected, "found": found, "met": met}
                        for name, expected, found, met in rows]
    item["reference"] = reference.get("source", "")
    return item


def j0_local_row(ctx, image_sha256):
    """The image hash of the user's local J0 report (docs/J0_ISO_IDENTIFICATION.md: the JSON
    written by iso-identify --json), when it is given."""
    try:
        with open(ctx.args.j0_report, encoding="utf-8") as f:
            report = json.load(f)
        expected = report["source"]["sha256"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ("image sha256 = local J0 report", "readable report",
                f"unreadable ({type(exc).__name__})", False)
    return ("image sha256 = local J0 report", expected, image_sha256,
            expected == image_sha256)


# --- reports ----------------------------------------------------------------------------

def summary_text(ctx, steps, command, started, pb1=None):
    lines = [f"fifa2010wc B1 summary: metadata only. Review it before sharing it (CP-5).",
             f"tool: b1_extract version {TOOL_VERSION}, command {command}",
             f"started: {utc_stamp(started)}"]
    repo = steps.get("repository")
    if repo:
        lines.append(f"repository commit: {repo['facts'].get('repository_commit', 'unknown')}")
    if ctx.sdk:
        lines.append(f"SDK: {os.path.basename(ctx.sdk).split('-', 1)[-1]}")
    total = sum(len(item["findings"]) for item in steps.items)
    lines.append(f"outcome: {'FINDINGS (' + str(total) + ')' if total else 'no finding'}")
    lines.append("steps:")
    for item in steps.items:
        code = f"exit {item['exit_code']}" if "exit_code" in item else ""
        facts = ", ".join(f"{key} {value}" for key, value in item["facts"].items()
                          if key not in ("repository_commit",) and not isinstance(value, dict))
        kinds = {}
        for text in item["findings"]:
            kind = finding_kind(text)
            kinds[kind] = kinds.get(kind, 0) + 1
        line = f"  {item['step']:<22} {item['status']:<8} {code:<8} {facts}".rstrip()
        lines.append(line)
        for kind, count in kinds.items():
            lines.append(f"      finding: {kind} (x{count})")
        if item["notes"]:
            lines.append(f"      notes: {len(item['notes'])}")
    if pb1 is not None:
        lines.append(f"PB-1 figures (reference: {pb1['reference']}):")
        for row in pb1["criteria"]:
            mark = "match" if row["met"] else "DIFFERS"
            lines.append(f"  {row['name']}: expected {row['expected']}, found {row['found']}: "
                         f"{mark}")
        hidden = pb1["facts"].get("hidden_names", 0)
        lines.append(f"  names starting with a dot: {hidden} (counted)")
        for kind, count in pb1["facts"].get("anomaly_kinds", {}).items():
            lines.append(f"  anomaly: {kind} (x{count}, not counted)")
    lines.append("decision: this tool does not declare PB-1; the orchestrator decides.")
    if steps.has_findings():
        lines.append("STOP: a finding stops B1. Delete nothing; keep the local evidence; "
                     "report the summary.")
    return "\n".join(lines) + "\n"


def finish(ctx, steps, command, started, run_dir=None, pb1=None):
    summary = summary_text(ctx, steps, command, started, pb1)
    if run_dir:
        report = {"tool": {"name": "b1_extract", "version": TOOL_VERSION},
                  "command": command, "started": utc_stamp(started),
                  "finished": utc_stamp(), "steps": steps.items}
        write_new(os.path.join(run_dir, "report.json"),
                  json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        write_new(os.path.join(run_dir, "summary.txt"), summary)
    sys.stdout.write(summary)
    if run_dir:
        rel = ctx.redact(run_dir)
        print(f"local report: {rel}/report.json (do not share)")
        print(f"summary: {rel}/summary.txt")
    return 1 if steps.has_findings() else 0


def new_run_dir(ctx, command):
    name = f"b1-{command}-{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}"
    path = os.path.join(ctx.logs, name)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        raise UsageError(f"{name} already exists: wait one second and start again")
    return path


def cmd_prepare(ctx):
    steps = Steps(ctx.redact)
    started = time.time()
    prepare_checks(ctx, steps)
    return finish(ctx, steps, "prepare", started)


def cmd_verify(ctx):
    steps = Steps(ctx.redact)
    started = time.time()
    findings, facts = [], {}
    check_real_folder(ctx, "game", findings, facts)
    steps.add("folders", "ok", facts=facts, findings=findings)
    pb1 = pb1_figures(ctx, steps)
    return finish(ctx, steps, "verify", started, pb1=pb1)


def cmd_step(ctx, extract):
    """`run` (extract=True) and `rehearse` (extract=False)."""
    command = "run" if extract else "rehearse"
    steps = Steps(ctx.redact)
    started = time.time()
    prepare_checks(ctx, steps)
    if steps.has_findings():
        print("prepare found something: nothing was started, nothing was written.")
        return finish(ctx, steps, command, started)

    # Settings of the step, inherited by every command it starts.
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    run_dir = new_run_dir(ctx, command)
    make_env_folders(ctx)
    env = step_env(ctx)
    env["REX_APP_LOG_ROOT"] = run_dir
    core = steps.get("core-dump-setting")["facts"]
    started_ns = time.time_ns()

    targets, error = list_mounts(ctx)
    if error:
        steps.add("mounts-before", "finding", findings=[f"cannot list the mount points: {error}"])
        return finish(ctx, steps, command, started, run_dir)
    relevant_before, watch, plan = watch_plan(ctx, targets)
    write_new(os.path.join(run_dir, "mounts-before.txt"), "\n".join(targets) + "\n")
    steps.add("mounts-before", "ok", facts=plan, output="mounts-before.txt")

    before = None
    if extract:
        t = time.monotonic()
        try:
            before = image_state(ctx.iso)
        except OSError as exc:
            steps.add("image-before", "finding",
                      findings=[f"the disc image cannot be read ({exc.strerror})"])
            return finish(ctx, steps, command, started, run_dir)
        steps.add("image-before", "ok", facts={"sha256": before["sha256"],
                                               "size": before["identity"]["st_size"]},
                  duration=time.monotonic() - t)

    store_before, code, findings, facts, seconds = store_survey(ctx, run_dir, "cp3-before")
    steps.add("cp3-before", "ok", exit_code=code, facts=facts, findings=findings,
              output="cp3-before.txt", duration=seconds)
    if steps.has_findings():
        return finish(ctx, steps, command, started, run_dir)

    marker = os.path.join(run_dir, "b1.marker")
    dests = []
    for name in DESTINATIONS:
        dests += ["--dest", os.path.join(ctx.private, name)]
    pre = ctx.guard_cmd("preflight", *dests, "--game-root", ctx.game,
                        "--sdk-bin", os.path.join(ctx.sdk, "bin"), "--marker", marker,
                        *(["--shm-dir", ctx.args.shm_dir] if ctx.args.shm_dir else []))
    guard_step(ctx, steps, "preflight", pre, run_dir, env=env, cwd=ctx.private)
    if steps.has_findings() or not os.path.exists(marker):
        steps.add("postflight", "skipped", notes=["no marker: preflight did not pass, so "
                                                  "nothing was started"])
        return finish(ctx, steps, command, started, run_dir)

    # From here on, postflight runs whatever happens.
    try:
        findings = []
        check_sdk_before(ctx, started_ns, findings)
        check_game_empty(ctx, findings, {})
        steps.add("before-extraction", "ok", findings=findings)
        if not extract:
            steps.add("vfs-dump", "skipped", notes=["rehearsal: no extraction"])
        elif steps.has_findings():
            steps.add("vfs-dump", "skipped", notes=["not started: a check found something"])
        else:
            run_dump(ctx, steps, run_dir, env)
    except KeyboardInterrupt:
        steps.add("interrupted", "finding", findings=["the step was interrupted"])
    except Exception as exc:  # postflight must still run
        steps.add("internal-error", "finding",
                  findings=[f"internal error before postflight: {type(exc).__name__}"])
    finally:
        watches = []
        for place in [ctx.home, ctx.tmp_watch] + watch:
            watches += ["--watch", place]
        post = ctx.guard_cmd("postflight", "--marker", marker, "--sdk", ctx.sdk,
                             "--nix", ctx.args.nix, *watches,
                             *(["--shm-dir", ctx.args.shm_dir] if ctx.args.shm_dir else []))
        guard_step(ctx, steps, "postflight", post, run_dir, env=env, cwd=ctx.private)

    pb1 = None
    try:
        pb1 = after_step(ctx, steps, run_dir, extract, started, core, relevant_before,
                         store_before, before)
    except KeyboardInterrupt:
        steps.add("interrupted", "finding", findings=["the checks after postflight were "
                                                      "interrupted"])
    except Exception as exc:  # the report is still written
        steps.add("internal-error", "finding",
                  findings=[f"internal error after postflight: {type(exc).__name__}"])
    return finish(ctx, steps, command, started, run_dir, pb1=pb1)


def after_step(ctx, steps, run_dir, extract, started, core, relevant_before, store_before,
               before):
    """The checks after postflight. They read only, and write their outputs in the run
    folder. Returns the PB-1 figures of `run`."""
    targets, error = list_mounts(ctx)
    if error:
        steps.add("mounts-after", "finding", findings=[f"cannot list the mount points: {error}"])
    else:
        write_new(os.path.join(run_dir, "mounts-after.txt"), "\n".join(targets) + "\n")
        relevant_after, _, plan = watch_plan(ctx, targets)
        added = sorted(set(relevant_after) - set(relevant_before))
        removed = sorted(set(relevant_before) - set(relevant_after))
        findings = [f"new mount point during the step: {path}" for path in added]
        findings += [f"mount point gone during the step: {path}" for path in removed]
        steps.add("mounts-after", "ok", facts={"added": len(added), "removed": len(removed)},
                  findings=findings, output="mounts-after.txt")

    code, text, facts, findings, notes = coredump_check(ctx, started, core)
    write_new(os.path.join(run_dir, "coredumps.txt"), text)
    steps.add("core-dumps", "ok" if not notes else "skipped", exit_code=code, facts=facts,
              findings=findings, notes=notes, output="coredumps.txt")

    store_after, code, findings, facts, seconds = store_survey(ctx, run_dir, "cp3-after")
    new = sorted(store_after - store_before)
    gone = sorted(store_before - store_after)
    findings += [f"CP-3 new match in the store: {path}" for path in new]
    facts.update({"new_matches": len(new), "gone_matches": len(gone)})
    steps.add("cp3-after", "ok", exit_code=code, facts=facts, findings=findings,
              notes=[f"CP-3 match gone: {path}" for path in gone],
              output="cp3-after.txt", duration=seconds)

    pb1 = None
    if extract:
        t = time.monotonic()
        try:
            after = image_state(ctx.iso)
            steps.add("image-after", "ok", facts={"sha256": after["sha256"],
                                                  "size": after["identity"]["st_size"]},
                      findings=[] if after == before else
                      ["the disc image changed during the step"],
                      duration=time.monotonic() - t)
        except OSError as exc:
            after = None
            steps.add("image-after", "finding",
                      findings=[f"the disc image cannot be read ({exc.strerror})"])
        dump = steps.get("vfs-dump")
        block = dump_block(run_dir) if dump and dump["status"] != "skipped" else None
        pb1 = pb1_figures(ctx, steps, before=before, after=after, block=block)
    return pb1



def main(argv):
    parser = argparse.ArgumentParser(
        prog="b1_extract",
        description="J2 step B1: controlled extraction of the disc tree with rexglue vfs "
                    "dump, on the user's machine (docs/J2_B1_EXTRACTION.md).")
    parser.add_argument("--private-dir", default=os.environ.get("WC2010_PRIVATE_DIR"),
                        help="private folder (default: $WC2010_PRIVATE_DIR)")
    parser.add_argument("--repo", help="the project repository, which must stay unchanged")
    parser.add_argument("--sdk", help="store path of the ReXGlue SDK, built beforehand")
    parser.add_argument("--guard", default=DEFAULT_GUARD, help="path of private_guard.py")
    parser.add_argument("--j0-report", help="the local J0 report (JSON) holding the image "
                                            "hash, to compare with")
    parser.add_argument("--timeout", type=int, default=DUMP_TIMEOUT,
                        help=f"seconds before rexglue is stopped (default {DUMP_TIMEOUT})")
    # Commands, folders and references replaced by the tests (tools/test_b1_extract.py).
    for name, default in (("--git", "git"), ("--nix", "nix"), ("--find", "find"),
                          ("--findmnt", "findmnt"), ("--coredumpctl", "coredumpctl"),
                          ("--store-dir", "/nix/store"), ("--tmp-watch", "/tmp"),
                          ("--shm-dir", None), ("--reference", None)):
        parser.add_argument(name, default=default, help=argparse.SUPPRESS)
    parser.add_argument("command", choices=("prepare", "rehearse", "run", "verify"))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    if os.geteuid() == 0:
        print("FINDING: running as root: B1 never runs as root (a root rexglue can write "
              "into /nix/store, docs/J2_A1_SDK_INVENTORY.md §2)")
        return 1
    try:
        ctx = Context(args)
        if args.command == "prepare":
            return cmd_prepare(ctx)
        if args.command == "verify":
            return cmd_verify(ctx)
        return cmd_step(ctx, extract=args.command == "run")
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

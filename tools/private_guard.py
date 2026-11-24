#!/usr/bin/env python3
"""Controls before and after every step that touches the user's game files (J2, phase B).

They implement CP-1 and CP-4 of docs/J2_PREREQUISITES.md section 6, as step A4 of
docs/J2_PLAN.md asks, with the destinations found by the A1 inventory
(docs/J2_A1_SDK_INVENTORY.md section 6). Nothing here opens a game file: the script looks
only at paths, owners, modes, timestamps and process settings. It never deletes, moves or
changes anything, except the marker file that `preflight --marker` writes.

Commands:
  check-dir   CP-1. The private folder ($WC2010_PRIVATE_DIR) is an absolute path to a
              folder outside /nix/store, the repository and any git work tree; it belongs
              to the user and nobody else may enter it (mode 0700 or stricter); its
              subfolders exist; the files under iso/ are read only.
  preflight   CP-4 before an invocation. check-dir, then: each declared write destination,
              the working folder, TMPDIR, the XDG folders and REX_APP_ROOT lie in the
              private folder; not root; umask 077; core dumps off (RLIMIT_CORE 0); no
              settings file that ReXGlue would read before the environment; no unexpected
              .xexp patch in the game folder; no guest memory object left in /dev/shm.
              With --marker FILE, writes the marker that postflight compares against.
  postflight  CP-4 after. Files created, modified or moved since the marker in the watched
              places outside the private folder; guest memory objects left in /dev/shm;
              with --sdk, `nix store verify` of the SDK store path; with --repo,
              `git status` of the repository.

A check that cannot run in full is a finding, never an OK: /dev/shm that cannot be
listed, a watched place that is absent (unless declared with --optional-watch), or a
folder or file under it that cannot be read. preflight also refuses a step that declares
no write destination, unless --no-writes says it writes nothing.

One kind of unreadable folder is a note instead (#30): a systemd PrivateTmp= folder, when
every condition of systemd_private_tmp() holds. It is directly under /tmp, named as the
service manager names it for this boot, a real folder (not a link), owned by root:root,
mode 0700, unchanged while it is checked, opening it fails with EACCES, and this check
runs without privileges. Such a folder is excluded from the watched scope and never
searched, and the note says so. A folder on another file system, such as a mount point, is
not searched either: that is an incomplete check, a finding, unless the folder is itself one
of the watched places, which is then searched on its own.

These checks cover the declared destinations and the watched places only. They do not
prove that nothing was written anywhere else (docs/J2_PREREQUISITES.md section 6.1). A
root process could write into an excluded systemd folder; phase B runs nothing as root.

Exit status: 0 when nothing is found, 1 when a finding is reported, 2 on usage error.
Only the Python standard library is used. Run it with `python3 -I`.
"""

import argparse
import errno
import os
import re
import resource
import stat
import subprocess
import sys

# Subfolders of the private folder (docs/audit/ISO_REQUIREMENTS.md section 6).
SUBFOLDERS = ("iso", "game", "xex", "generated", "cache", "saves", "logs")
STORE = "/nix/store"
# ReXGlue names its guest memory object /xenia_memory_<pid>_<random> (src/kernel/memory.cpp).
SHM_PREFIX = "xenia_memory_"
# Must be set, absolute and inside the private folder (docs/J2_PREREQUISITES.md 6.1).
REQUIRED_ENV = ("TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "REX_APP_ROOT")
# Checked the same way when set: other ReXGlue folders (docs/J2_A1_SDK_INVENTORY.md 2).
OPTIONAL_ENV = ("REX_APP_LOG_ROOT", "REX_APP_USER_ROOT", "REX_APP_CACHE_ROOT")
APP_NAMES = ("rexglue",)
# systemd PrivateTmp= folders (systemd, src/core/namespace.c, setup_one_tmp_dir()): the
# service manager makes "<parent>/systemd-private-<boot id>-<unit>-XXXXXX" with mkdtemp(3)
# under umask 0077, so owned by root:root with mode 0700, and systemd-tmpfiles removes them
# at boot (tmpfiles.d/systemd-tmp.conf). The boot id is 32 lowercase hexadecimal digits; the
# unit is a unit name of a type that has PrivateTmp=; mkdtemp(3) puts six letters or digits.
SYSTEMD_TMP_PARENT = "/tmp"
BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"
SYSTEMD_PRIVATE_RE = re.compile(
    r"systemd-private-(?P<boot>[0-9a-f]{32})-"
    r"(?P<unit>[A-Za-z0-9:_.\\@-]{1,240}\.(?:service|socket|mount|swap))-[A-Za-z0-9]{6}")
EXCLUDED = "excluded from the watched scope"


def canonical(path):
    return os.path.realpath(path)


def located_within(path, folder):
    """True when the entry `path` itself, not what it may link to, is in `folder`."""
    place = os.path.join(canonical(os.path.dirname(path)), os.path.basename(path))
    folder = canonical(folder)
    try:
        return os.path.commonpath([place, folder]) == folder
    except ValueError:
        return False


def within(path, folder):
    """True when the canonical `path` is `folder` or lies under it."""
    path, folder = canonical(path), canonical(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


def git_work_tree(folder, git):
    """True if `folder` is inside a git work tree, False if not, None if git cannot run."""
    try:
        result = subprocess.run([git, "-C", folder, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0 and result.stdout.strip() == "true"


def check_dir(private, repo=None, git="git", uid=None, home=None):
    """CP-1. Returns the list of findings (empty when the folder passes)."""
    if not private:
        return ["WC2010_PRIVATE_DIR is not set"]
    if not os.path.isabs(private):
        return [f"the private folder is not an absolute path: {private}"]
    folder = canonical(private)
    if not os.path.isdir(folder):
        return [f"the private folder does not exist or is not a folder: {folder}"]
    findings = []
    home = canonical(home or os.path.expanduser("~"))
    if folder in ("/", home):
        findings.append(f"the private folder must be a dedicated folder, not {folder}")
    if within(folder, STORE):
        findings.append(f"the private folder is in {STORE}, readable by every user: {folder}")
    if repo and (within(folder, repo) or within(repo, folder)):
        findings.append(f"the private folder and the repository overlap: {folder}")
    inside = git_work_tree(folder, git)
    if inside is None:
        findings.append(f"cannot run {git} to check that the private folder is outside any "
                        "git work tree")
    elif inside:
        findings.append(f"the private folder is inside a git work tree: {folder}")
    st = os.stat(folder)
    if st.st_uid != (os.geteuid() if uid is None else uid):
        findings.append(f"the private folder belongs to another user (uid {st.st_uid})")
    if st.st_mode & 0o077:
        findings.append(f"the private folder has mode {stat.S_IMODE(st.st_mode):04o}: group "
                        "and others must have no access (chmod 700)")
    for name in SUBFOLDERS:
        sub = os.path.join(folder, name)
        if not os.path.isdir(sub):
            findings.append(f"missing subfolder: {name}/")
    iso = os.path.join(folder, "iso")
    if os.path.isdir(iso):
        for root, dirs, files in os.walk(iso):
            for name in files:
                path = os.path.join(root, name)
                try:
                    mode = os.lstat(path).st_mode
                except OSError:
                    continue
                if stat.S_ISREG(mode) and mode & 0o222:
                    findings.append(f"writable file under iso/ (chmod a-w): "
                                    f"{os.path.relpath(path, folder)}")
    return findings


def check_env(private, env):
    findings = []
    for name in REQUIRED_ENV + OPTIONAL_ENV:
        value = env.get(name)
        if not value:
            if name in REQUIRED_ENV:
                findings.append(f"{name} is not set: point it into the private folder")
            continue
        if not os.path.isabs(value):
            findings.append(f"{name} is not an absolute path: {value}")
        elif not within(value, private):
            findings.append(f"{name} is outside the private folder: {value}")
    return findings


def stray_settings_files(env, sdk_bin=None, home=None):
    """Settings files ReXGlue reads before it applies the environment
    (docs/J2_A1_SDK_INVENTORY.md section 2): {app.root}/<app>.toml, where app.root is the
    executable's folder when writable, else $XDG_CONFIG_HOME/<app> or ~/.config/<app>."""
    config_home = env.get("XDG_CONFIG_HOME") or os.path.join(
        home or os.path.expanduser("~"), ".config")
    candidates = []
    for name in APP_NAMES:
        candidates.append(os.path.join(config_home, name, f"{name}.toml"))
        if sdk_bin:
            candidates.append(os.path.join(sdk_bin, f"{name}.toml"))
    return [path for path in candidates if os.path.lexists(path)]


def xexp_files(game_root):
    found = []
    for root, dirs, files in os.walk(game_root):
        found.extend(os.path.join(root, name) for name in files
                     if name.lower().endswith(".xexp"))
    return sorted(found)


def shm_findings(shm_dir):
    """Guest memory objects left in `shm_dir`. A folder that cannot be listed is itself a
    finding: the check could not run, which must not read as "nothing found"."""
    try:
        names = os.listdir(shm_dir)
    except OSError as exc:
        return [f"incomplete check: cannot list {shm_dir} ({exc.strerror or exc}), so guest "
                "memory objects cannot be ruled out"]
    return [f"guest memory object left in {shm_dir}: {name}"
            for name in sorted(names) if name.startswith(SHM_PREFIX)]


def process_settings():
    """Current umask, effective uid and soft core size limit of this process. A guarded
    command started from the same shell inherits them."""
    mask = os.umask(0o077)
    os.umask(mask)
    return {"umask": mask, "euid": os.geteuid(),
            "core": resource.getrlimit(resource.RLIMIT_CORE)[0]}


def preflight(private, dests=(), cwd=None, env=None, settings=None, repo=None, git="git",
              sdk_bin=None, game_root=None, allow_xexp=False, allowed_settings=(),
              shm_dir="/dev/shm", home=None, no_writes=False):
    """CP-4, before an invocation. Returns the list of findings.

    The step's write destinations are required: an empty list is a finding unless
    `no_writes` states that the step writes nothing."""
    env = os.environ if env is None else env
    settings = process_settings() if settings is None else settings
    findings = check_dir(private, repo=repo, git=git, home=home)
    if findings and not (private and os.path.isabs(private) and os.path.isdir(private)):
        return findings
    if not dests and not no_writes:
        findings.append("no write destination declared: give each folder or file the step "
                        "writes with --dest, or --no-writes for a step that writes nothing")
    if dests and no_writes:
        findings.append("--no-writes contradicts the declared write destinations")
    for dest in dests:
        if not within(dest, private):
            findings.append(f"write destination outside the private folder: {dest}")
    cwd = os.getcwd() if cwd is None else cwd
    if not within(cwd, private):
        findings.append(f"the working folder is outside the private folder: {cwd}")
    if settings["euid"] == 0:
        findings.append("running as root: ReXGlue can then write next to its executable, in "
                        "/nix/store (docs/J2_A1_SDK_INVENTORY.md section 2)")
    if settings["umask"] & 0o077 != 0o077:
        findings.append(f"umask is {settings['umask']:03o}: set umask 077, so that the guest "
                        "memory object in /dev/shm and every output are private")
    if settings["core"] != 0:
        findings.append("core dumps are allowed (ulimit -c is not 0): a core dump would hold "
                        "the decoded image")
    findings.extend(check_env(private, env))
    allowed = {canonical(path) for path in allowed_settings}
    for path in stray_settings_files(env, sdk_bin=sdk_bin, home=home):
        if canonical(path) not in allowed:
            findings.append(f"settings file read before the environment: {path}")
    if game_root:
        if not within(game_root, private):
            findings.append(f"the game folder is outside the private folder: {game_root}")
        if not allow_xexp:
            for path in xexp_files(game_root):
                findings.append(f"title update patch applied automatically by ReXGlue: {path}")
    findings.extend(shm_findings(shm_dir))
    return findings


def write_marker(private, marker):
    if not within(marker, private):
        raise ValueError(f"the marker must be in the private folder: {marker}")
    with open(marker, "w") as f:
        f.write("fifa2010wc private_guard marker\n")
    return os.stat(marker).st_mtime_ns


def current_boot_id():
    """The boot id of the running kernel as systemd writes it in folder names (32 lowercase
    hexadecimal digits), or None when it cannot be read."""
    try:
        with open(BOOT_ID_PATH) as f:
            value = f.read().strip().replace("-", "").lower()
    except OSError:
        return None
    return value if re.fullmatch(r"[0-9a-f]{32}", value) else None


def _identity(st):
    """The attributes of a folder that must not change while it is checked."""
    return (st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode), stat.S_IMODE(st.st_mode),
            st.st_uid, st.st_gid, st.st_ctime_ns)


def systemd_private_tmp(path, first):
    """Decides on a folder whose name has the form of a systemd PrivateTmp= folder.

    `first` is its lstat() from the traversal. Returns ("search", None) when this process
    can open the folder, which is then searched like any other; ("exclude", note) when it is
    a verified systemd folder that this process cannot read; ("refuse", reason) otherwise,
    which the caller reports as a location that could not be read. Only EACCES counts as
    the refusal to open: EPERM or any other error is a refusal here. The name alone proves
    nothing: the place, the type, the owner, the mode and their stability are all needed."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        if exc.errno != errno.EACCES:
            # EPERM, which PermissionError also carries, is not the refusal of a folder
            # mode to an unprivileged user (review R-31-2).
            return "refuse", f"cannot be opened ({exc.strerror or exc})"
    else:
        os.close(fd)
        return "search", None
    try:
        second = os.lstat(path)
    except OSError as exc:
        return "refuse", f"vanished while it was checked ({exc.strerror or exc})"
    if _identity(first) != _identity(second):
        return "refuse", "changed while it was checked"
    reasons = []
    parent = os.path.dirname(path)
    if parent != SYSTEMD_TMP_PARENT or canonical(parent) != SYSTEMD_TMP_PARENT:
        reasons.append(f"not directly under {SYSTEMD_TMP_PARENT}")
    if not stat.S_ISDIR(second.st_mode):
        reasons.append("not a real folder")
    if second.st_uid != 0 or second.st_gid != 0:
        reasons.append(f"owner {second.st_uid}:{second.st_gid}, not root:root")
    if stat.S_IMODE(second.st_mode) != 0o700:
        reasons.append(f"mode {stat.S_IMODE(second.st_mode):04o}, not 0700")
    if os.geteuid() == 0:
        reasons.append("this check runs as root")
    match = SYSTEMD_PRIVATE_RE.fullmatch(os.path.basename(path))
    boot = current_boot_id()
    if boot is None:
        reasons.append(f"the boot id cannot be read from {BOOT_ID_PATH}")
    elif match is None or match.group("boot") != boot:
        reasons.append("not named for the current boot")
    if reasons:
        return "refuse", "not accepted as a systemd PrivateTmp folder: " + "; ".join(reasons)
    return "exclude", (f"{EXCLUDED}: {path} is the systemd PrivateTmp folder of "
                       f"{match.group('unit')} (root:root, mode 0700, this boot); this "
                       "unprivileged check cannot read it and does not search it")


def changed_since(top, marker_ns, private, searched_elsewhere=()):
    """Files and symbolic links under `top`, on the same file system, outside the private
    folder, whose modification or status change time is after the marker. Links are never
    followed. Returns (changed, unreadable_locations, unsearched, notes).

    `unsearched` lists the folders on another file system: they are not searched here, which
    makes the check incomplete, unless their canonical path is in `searched_elsewhere`, the
    watched places searched on their own (review R-31-1). A note names each verified systemd
    PrivateTmp folder left out of the search."""
    changed, unreadable, unsearched, notes = [], [], [], []
    searched_elsewhere = {canonical(path) for path in searched_elsewhere}
    try:
        top_dev = os.lstat(top).st_dev
    except OSError:
        return changed, [top], unsearched, notes
    private = canonical(private)

    def on_error(error):
        unreadable.append(error.filename)

    def is_new(st):
        return max(st.st_mtime_ns, st.st_ctime_ns) > marker_ns

    for root, dirs, files in os.walk(top, onerror=on_error):
        keep = []
        for name in dirs:
            if name == ".git":
                # git itself rewrites its index when `git status` runs (postflight --repo).
                continue
            path = os.path.join(root, name)
            try:
                st = os.lstat(path)
            except OSError:
                unreadable.append(path)
                continue
            if stat.S_ISLNK(st.st_mode):
                # A link to a folder: never followed, and a change when it is new.
                if not located_within(path, private) and is_new(st):
                    changed.append(path)
                continue
            if within(path, private):
                continue
            if st.st_dev != top_dev:
                # Not followed: another file system is searched only as a watched place.
                if canonical(path) not in searched_elsewhere:
                    unsearched.append(path)
                continue
            if SYSTEMD_PRIVATE_RE.fullmatch(name):
                outcome, detail = systemd_private_tmp(path, st)
                if outcome == "exclude":
                    notes.append(detail)
                    continue
                if outcome == "refuse":
                    unreadable.append(f"{path} ({detail})")
                    continue
            keep.append(name)
        dirs[:] = keep
        for name in files:
            path = os.path.join(root, name)
            try:
                st = os.lstat(path)
            except OSError:
                unreadable.append(path)
                continue
            inside = (located_within(path, private) if stat.S_ISLNK(st.st_mode)
                      else within(path, private))
            if inside:
                continue
            if is_new(st):
                changed.append(path)
    return sorted(changed), unreadable, unsearched, notes


def postflight(private, marker, watch=(), shm_dir="/dev/shm", sdk=None, nix="nix", repo=None,
               git="git", optional=()):
    """CP-4, after an invocation. Returns (findings, notes).

    Every place in `watch` must be searched in full. A place that is absent, or a folder or
    file under it that cannot be read, makes the check incomplete, which is a finding.
    Only the places listed in `optional` may be absent, and that is reported as a note.
    A folder on another file system under a watched place is a finding too, unless it is
    itself a watched place. The verified systemd PrivateTmp folders that changed_since()
    leaves out of the search are reported as notes."""
    findings, notes = [], []
    try:
        marker_ns = os.stat(marker).st_mtime_ns
    except OSError:
        return [f"marker not found: {marker} (run preflight --marker first)"], notes
    optional = {canonical(path) for path in optional}
    tops = list(watch) + sorted(optional - {canonical(t) for t in watch})
    searched = {canonical(top) for top in tops if os.path.isdir(top)}
    for top in tops:
        if not os.path.isdir(top):
            if canonical(top) in optional:
                notes.append(f"optional watched folder absent: {top}")
            else:
                findings.append(f"incomplete check: watched folder absent or not a folder: "
                                f"{top}")
            continue
        changed, unreadable, unsearched, scope_notes = changed_since(
            top, marker_ns, private, searched_elsewhere=searched - {canonical(top)})
        notes.extend(note for note in scope_notes if note not in notes)
        for path in unsearched:
            findings.append(f"incomplete check: {path} under {top} is on another file system "
                            "and was not searched; watch it with --watch to search it")
        for path in changed:
            finding = f"file written outside the private folder: {path}"
            if finding not in findings:
                findings.append(finding)
        if unreadable:
            shown = ", ".join(unreadable[:5]) + (" ..." if len(unreadable) > 5 else "")
            findings.append(f"incomplete check: {len(unreadable)} location(s) under {top} "
                            f"could not be read: {shown}")
    findings.extend(shm_findings(shm_dir))
    if sdk:
        try:
            result = subprocess.run([nix, "store", "verify", sdk], capture_output=True,
                                    text=True, timeout=600)
            if result.returncode != 0:
                findings.append(f"the SDK store path was modified: {sdk}")
        except (OSError, subprocess.SubprocessError):
            findings.append(f"cannot run {nix} store verify on {sdk}")
    if repo:
        try:
            result = subprocess.run([git, "-C", repo, "status", "--porcelain",
                                     "--untracked-files=all"],
                                    capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                findings.append(f"git status failed in {repo}")
            else:
                findings.extend(f"repository changed: {line}"
                                for line in result.stdout.splitlines() if line.strip())
        except (OSError, subprocess.SubprocessError):
            findings.append(f"cannot run {git} status in {repo}")
    return findings, notes


def report(findings, notes=(), ok_message="nothing found"):
    for note in notes:
        print(f"note: {note}")
    if findings:
        for finding in findings:
            print(f"FINDING: {finding}")
        print(f"{len(findings)} finding(s)")
        return 1
    print(f"OK: {ok_message}")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(
        prog="private_guard",
        description="CP-1 and CP-4 controls around steps on the user's game files.")
    parser.add_argument("--private-dir", default=os.environ.get("WC2010_PRIVATE_DIR"),
                        help="private folder (default: $WC2010_PRIVATE_DIR)")
    parser.add_argument("--repo", help="the project repository, which must stay unchanged")
    parser.add_argument("--git", default="git", help="git command (default: git)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-dir", help="CP-1: check the private folder")

    pre = sub.add_parser("preflight", help="CP-4 before an invocation")
    pre.add_argument("--dest", action="append", default=[],
                     help="a folder or file the step writes (repeatable; required unless "
                          "--no-writes)")
    pre.add_argument("--no-writes", action="store_true",
                     help="the step writes nothing (instead of --dest)")
    pre.add_argument("--sdk-bin", help="folder of the rexglue executable or of the game")
    pre.add_argument("--game-root", help="folder mounted as game:")
    pre.add_argument("--allow-xexp", action="store_true",
                     help="a .xexp in the game folder is intended")
    pre.add_argument("--allow-settings", action="append", default=[],
                     help="a ReXGlue settings file that is intended (repeatable)")
    pre.add_argument("--shm-dir", default="/dev/shm", help=argparse.SUPPRESS)
    pre.add_argument("--marker", help="write this marker file in the private folder")

    post = sub.add_parser("postflight", help="CP-4 after an invocation")
    post.add_argument("--marker", required=True, help="marker written by preflight")
    post.add_argument("--watch", action="append", default=[],
                      help="a folder to search for new files, which must exist and be "
                           "readable (repeatable; default: the home folder and /tmp)")
    post.add_argument("--optional-watch", action="append", default=[],
                      help="a folder searched if it exists; its absence is only a note")
    post.add_argument("--sdk", help="SDK store path to check with nix store verify")
    post.add_argument("--nix", default="nix", help="nix command (default: nix)")
    post.add_argument("--shm-dir", default="/dev/shm", help=argparse.SUPPRESS)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0

    if args.command == "check-dir":
        return report(check_dir(args.private_dir, repo=args.repo, git=args.git),
                      ok_message=f"private folder {args.private_dir}")

    if args.command == "preflight":
        findings = preflight(args.private_dir, dests=args.dest, repo=args.repo, git=args.git,
                             sdk_bin=args.sdk_bin, game_root=args.game_root,
                             allow_xexp=args.allow_xexp, allowed_settings=args.allow_settings,
                             shm_dir=args.shm_dir, no_writes=args.no_writes)
        if findings:
            return report(findings)
        if args.marker:
            try:
                write_marker(args.private_dir, args.marker)
            except (OSError, ValueError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
        return report([], ok_message="ready" + (f", marker {args.marker}" if args.marker
                                                else ""))

    watch = args.watch or [os.path.expanduser("~"), "/tmp"]
    if args.repo:
        watch = [args.repo] + watch
    findings, notes = postflight(args.private_dir, args.marker, watch=watch,
                                 shm_dir=args.shm_dir, sdk=args.sdk, nix=args.nix,
                                 repo=args.repo, git=args.git, optional=args.optional_watch)
    excluded = sum(1 for note in notes if note.startswith(EXCLUDED))
    ok_message = "no file written outside the private folder in the watched places"
    if excluded:
        ok_message += (f", except {excluded} folder(s) excluded from the watched scope (see "
                       "the notes)")
    return report(findings, notes, ok_message=ok_message)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

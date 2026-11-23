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

These checks cover the declared destinations and the watched places only. They do not
prove that nothing was written anywhere else (docs/J2_PREREQUISITES.md section 6.1).

Exit status: 0 when nothing is found, 1 when a finding is reported, 2 on usage error.
Only the Python standard library is used. Run it with `python3 -I`.
"""

import argparse
import os
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


def canonical(path):
    return os.path.realpath(path)


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


def shm_objects(shm_dir):
    try:
        return sorted(name for name in os.listdir(shm_dir) if name.startswith(SHM_PREFIX))
    except OSError:
        return []


def process_settings():
    """Current umask, effective uid and soft core size limit of this process. A guarded
    command started from the same shell inherits them."""
    mask = os.umask(0o077)
    os.umask(mask)
    return {"umask": mask, "euid": os.geteuid(),
            "core": resource.getrlimit(resource.RLIMIT_CORE)[0]}


def preflight(private, dests=(), cwd=None, env=None, settings=None, repo=None, git="git",
              sdk_bin=None, game_root=None, allow_xexp=False, allowed_settings=(),
              shm_dir="/dev/shm", home=None):
    """CP-4, before an invocation. Returns the list of findings."""
    env = os.environ if env is None else env
    settings = process_settings() if settings is None else settings
    findings = check_dir(private, repo=repo, git=git, home=home)
    if findings and not (private and os.path.isabs(private) and os.path.isdir(private)):
        return findings
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
    for name in shm_objects(shm_dir):
        findings.append(f"guest memory object left in {shm_dir}: {name}")
    return findings


def write_marker(private, marker):
    if not within(marker, private):
        raise ValueError(f"the marker must be in the private folder: {marker}")
    with open(marker, "w") as f:
        f.write("fifa2010wc private_guard marker\n")
    return os.stat(marker).st_mtime_ns


def changed_since(top, marker_ns, private):
    """Files and symbolic links under `top`, on the same file system, outside the private
    folder, whose modification or status change time is after the marker. Returns
    (changed, unreadable_folders)."""
    changed, unreadable = [], []
    try:
        top_dev = os.lstat(top).st_dev
    except OSError:
        return changed, unreadable
    private = canonical(private)

    def on_error(error):
        unreadable.append(error.filename)

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
            if st.st_dev != top_dev or within(path, private):
                continue
            keep.append(name)
        dirs[:] = keep
        for name in files:
            path = os.path.join(root, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if within(path, private):
                continue
            if max(st.st_mtime_ns, st.st_ctime_ns) > marker_ns:
                changed.append(path)
    return sorted(changed), unreadable


def postflight(private, marker, watch=(), shm_dir="/dev/shm", sdk=None, nix="nix", repo=None,
               git="git"):
    """CP-4, after an invocation. Returns (findings, notes)."""
    findings, notes = [], []
    try:
        marker_ns = os.stat(marker).st_mtime_ns
    except OSError:
        return [f"marker not found: {marker} (run preflight --marker first)"], notes
    for top in watch:
        if not os.path.isdir(top):
            notes.append(f"watched folder absent: {top}")
            continue
        changed, unreadable = changed_since(top, marker_ns, private)
        for path in changed:
            finding = f"file written outside the private folder: {path}"
            if finding not in findings:
                findings.append(finding)
        if unreadable:
            notes.append(f"{len(unreadable)} unreadable folder(s) skipped under {top}")
    for name in shm_objects(shm_dir):
        findings.append(f"guest memory object left in {shm_dir}: {name}")
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
                     help="a folder or file the command will write (repeatable)")
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
                      help="a folder to search for new files (repeatable; default: the "
                           "home folder and /tmp)")
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
                             shm_dir=args.shm_dir)
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
                                 repo=args.repo, git=args.git)
    return report(findings, notes, ok_message="no file written outside the private folder "
                                              "in the watched places")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Sets up and checks the ReXGlue codegen project in the private folder (J2 step A5).

Commands:
  template  checks the manifest template of the repository as it would be installed in
            <private folder>/project/: the rules of `check`, plus the pinned SDK version and
            only the keys a template may hold, so no address of the game (CP-7).
  init      copies the template into $WC2010_PRIVATE_DIR/project/ and creates the output
            folders it names. A manifest already there is never overwritten.
  check     checks the manifest of the private folder: every host path is relative and
            resolves inside the private folder, both XEX files lie under game_root, and
            every output folder is a dedicated folder under generated/, shared with no
            other binary. Keys added in phase B (addresses) are allowed here.

It reads no XEX and runs no ReXGlue command. Only `init` writes, in two phases:

1. Checks, with no write: the private folder passes CP-1 (private_guard check-dir); the
   template file is read once, and that parsed content passes the template rules and the
   rules of `check` as installed under project/; project/, the manifest and every existing
   folder on the way to an output folder are real folders and files, not symbolic links.
   Any finding stops init before it writes anything. Phase 2 writes the bytes read here.
2. Writes, anchored to the private folder: every folder below its root is opened with
   O_NOFOLLOW from the descriptor of its parent, folders are created relative to that
   descriptor, and the manifest is created with O_CREAT | O_EXCL | O_NOFOLLOW. A link put
   in place between the two phases makes the open fail, and init stops: it cannot write
   through a link below the root of the private folder.

The root itself is resolved once, by its real path; CP-1 checks that it belongs to the
user and is closed to group and others. A link put in place below the root while init
runs makes it stop half way. Not covered: a process of the same user that renames, while
init runs, a real folder init has already opened to a place outside the private folder;
a descriptor does not pin where its folder is.

Exit status: 0 when nothing is found, 1 when something is found, 2 on bad usage.
"""

import argparse
import importlib.util
import os
import re
import stat
import sys
import tomllib

SDK_VERSION = "0.11.0"
PROJECT_DIR = "project"
MANIFEST_NAME = "wc2010_manifest.toml"
GENERATED_DIR = "generated"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(HERE), "config", "private-template",
                                MANIFEST_NAME)
DEFAULT_GUARD = os.path.join(HERE, "private_guard.py")
# Root of the virtual private folder in which `template` places the template. Paths are
# only computed under it, never looked up.
VIRTUAL_PRIVATE = "/fifa2010wc-virtual-private-folder"

# Keys a template may hold. Anything else (function starts, pointers, setjmp, hooks,
# function_table_base, analysis tables) belongs to the private copy only.
TEMPLATE_PROJECT_KEYS = {"name", "sdk_version", "game_root", "hook_sources"}
TEMPLATE_BINARY_KEYS = {"file_path", "out_directory_path", "includes"}
TEMPLATE_MODULE_KEYS = TEMPLATE_BINARY_KEYS | {"guest_path"}
TEMPLATE_TOP_KEYS = {"project", "entrypoint", "modules"}

PROJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def canonical(path):
    """Real path when it exists, so that links are followed; normalised path otherwise."""
    return os.path.realpath(path)


def inside(path, folder):
    """Path comparison only: both must already be resolved."""
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def within(path, folder):
    return inside(canonical(path), canonical(folder))


def load_manifest(path):
    """Returns (table, findings)."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle), []
    except OSError as error:
        return None, [f"cannot read the manifest {path}: {error.strerror}"]
    except tomllib.TOMLDecodeError as error:
        return None, [f"the manifest {path} is not valid TOML: {error}"]


def load_template(path):
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        return data, tomllib.loads(data.decode("utf-8")), []
    except OSError as error:
        return None, None, [f"cannot read the template {path}: {error.strerror}"]
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return None, None, [f"the template {path} is not valid TOML: {error}"]


def host_path_findings(label, value):
    """A host path of the manifest must be a relative POSIX string; returns its findings."""
    if not isinstance(value, str) or not value:
        return [f"{label} must be a non empty string"]
    if os.path.isabs(value) or value.startswith("~") or re.match(r"^[A-Za-z]:", value) \
            or "\\" in value:
        return [f"{label} is not a relative POSIX path: {value}"]
    return []


def binaries(table):
    """Yields (label, binary table) for the entrypoint and each module."""
    entry = table.get("entrypoint")
    if isinstance(entry, dict):
        yield "[entrypoint]", entry
    modules = table.get("modules", [])
    if isinstance(modules, list):
        for index, module in enumerate(modules):
            if isinstance(module, dict):
                yield f"[[modules]] #{index}", module


def check_table(table, base, private, resolve_path=canonical):
    """The path rules of `check` on a parsed manifest whose folder is base.

    resolve_path turns base + relative value into a resolved path: the real path for a
    manifest on disk, a plain normalised path for the template placed in the virtual
    private folder. Returns (findings, resolved paths by label).
    """
    findings = []
    resolved = {}
    private = resolve_path(private)

    def resolve(label, value):
        problems = host_path_findings(label, value)
        if problems:
            findings.extend(problems)
            return None
        path = resolve_path(os.path.join(base, value))
        resolved[label] = path
        if not inside(path, private):
            findings.append(f"{label} resolves outside the private folder: {path}")
            return None
        return path

    project = table.get("project")
    if not isinstance(project, dict):
        return findings + ["missing [project] table"], resolved
    name = project.get("name")
    if not isinstance(name, str) or not PROJECT_NAME.match(name):
        findings.append(f"[project].name must be an identifier (letters, digits, _): {name!r}")
    game_root = None
    if "game_root" not in project:
        findings.append("[project].game_root is missing: the private layout names it")
    else:
        game_root = resolve("[project].game_root", project["game_root"])
    hook_sources = project.get("hook_sources", [])
    if not isinstance(hook_sources, list):
        findings.append("[project].hook_sources must be an array")
    else:
        for index, folder in enumerate(hook_sources):
            resolve(f"[project].hook_sources #{index}", folder)

    if not isinstance(table.get("entrypoint"), dict):
        findings.append("missing [entrypoint] table")
    if "modules" in table and not isinstance(table["modules"], list):
        findings.append("modules must be an array of tables ([[modules]])")

    generated = os.path.join(private, GENERATED_DIR)
    outputs = []
    guest_paths = set()
    for label, binary in binaries(table):
        xex = resolve(f"{label}.file_path", binary.get("file_path"))
        if xex and game_root and (xex == game_root or not inside(xex, game_root)):
            findings.append(f"{label}.file_path is not under game_root: ReXGlue refuses it")
        out = resolve(f"{label}.out_directory_path", binary.get("out_directory_path"))
        if out:
            if not inside(out, generated) or out == generated:
                findings.append(f"{label}.out_directory_path must be a folder inside "
                                f"{GENERATED_DIR}/, one per binary: {out}")
            if game_root and (inside(out, game_root) or inside(game_root, out)):
                findings.append(f"{label}.out_directory_path overlaps game_root")
            outputs.append((label, out))
        includes = binary.get("includes", [])
        if not isinstance(includes, list):
            findings.append(f"{label}.includes must be an array")
        else:
            for index, include in enumerate(includes):
                resolve(f"{label}.includes #{index}", include)
        if label.startswith("[[modules]]"):
            guest = binary.get("guest_path")
            if not isinstance(guest, str) or not guest:
                findings.append(f"{label}.guest_path is missing")
            elif normalize_guest_path(guest) in guest_paths:
                findings.append(f"{label}.guest_path is used twice: {guest}")
            else:
                guest_paths.add(normalize_guest_path(guest))
    for index, (label, out) in enumerate(outputs):
        for other_label, other in outputs[index + 1:]:
            if inside(out, other) or inside(other, out):
                findings.append(f"{label} and {other_label} share an output folder: codegen "
                                "deletes the outputs it did not write")
    return findings, resolved


def link_findings(private, relative_parts, label):
    """Every existing component below the private root must be a real folder (the last one
    may be a file): no symbolic link. Stops at the first missing component."""
    findings = []
    path = canonical(private)
    for index, part in enumerate(relative_parts):
        path = os.path.join(path, part)
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            break
        except OSError as error:
            findings.append(f"{label}: cannot inspect {path}: {error.strerror}")
            break
        last = index == len(relative_parts) - 1
        if stat.S_ISLNK(mode):
            findings.append(f"{label}: {path} is a symbolic link; init and check follow none")
            break
        if not last and not stat.S_ISDIR(mode):
            findings.append(f"{label}: {path} is not a folder")
            break
    return findings


def output_parts(private, project_base, value):
    """The components of an output folder below the private root, or None if it leaves it."""
    target = os.path.normpath(os.path.join(project_base, value))
    rel = os.path.relpath(target, canonical(private))
    parts = rel.split(os.sep)
    if rel == os.curdir or parts[0] == os.pardir:
        return None
    return parts


def check_manifest(manifest_path, private):
    """The rules of `check` on the manifest file. Returns (findings, resolved)."""
    findings = []
    path = os.path.abspath(manifest_path)
    for candidate in (path, os.path.dirname(path)):
        if os.path.islink(candidate):
            findings.append(f"manifest: {candidate} is a symbolic link; init and check "
                            "follow none")
    if findings:
        return findings, {}
    table, load = load_manifest(manifest_path)
    if table is None:
        return load, {}
    base = os.path.dirname(os.path.abspath(manifest_path))
    found, resolved = check_table(table, base, private)
    return found, resolved


def check_template(template_path, sdk_version=SDK_VERSION):
    """Reads the template file once and checks it (the `template` command)."""
    _, table, findings = load_template(template_path)
    if table is None:
        return findings
    return check_template_table(table, sdk_version)


def check_template_table(table, sdk_version=SDK_VERSION):
    """The template, already parsed, as installed in <private folder>/project/: the rules of
    `check` in a virtual private folder, plus the template only rules (keys, SDK)."""
    findings = []
    base = os.path.join(VIRTUAL_PRIVATE, PROJECT_DIR)
    found, _ = check_table(table, base, VIRTUAL_PRIVATE, resolve_path=os.path.normpath)
    findings += [finding.replace(VIRTUAL_PRIVATE, "<private folder>") for finding in found]
    for key in table:
        if key not in TEMPLATE_TOP_KEYS:
            findings.append(f"the template holds [{key}]: game data belongs to the private "
                            "copy only (CP-7)")
    project = table.get("project", {})
    if isinstance(project, dict):
        for key in project:
            if key not in TEMPLATE_PROJECT_KEYS:
                findings.append(f"the template holds [project].{key}: not a template key")
        if project.get("sdk_version") != sdk_version:
            findings.append(f"[project].sdk_version is {project.get('sdk_version')!r}, the "
                            f"pinned SDK is {sdk_version!r}")
    for label, binary in binaries(table):
        keys = TEMPLATE_MODULE_KEYS if label.startswith("[[modules]]") else TEMPLATE_BINARY_KEYS
        for key in binary:
            if key not in keys:
                findings.append(f"the template holds {label}.{key}: game data belongs to the "
                                "private copy only (CP-7)")
        for key in ("file_path", "out_directory_path"):
            value = binary.get(key)
            if isinstance(value, str) and not value.startswith("../"):
                findings.append(f"{label}.{key} must point out of project/ into the private "
                                f"folder: {value}")
    return findings


def normalize_guest_path(path):
    """Port of rex::string::NormalizeGuestPath (src/base/path.cpp:254-270): separators to
    `/`, a prefix up to `:/` removed (`game:/`, `d:/`), `.` and `..` resolved, leading `/`
    removed, lower case. Used to compare guest paths only."""
    text = path.replace("\\", "/")
    colon = text.find(":")
    if colon != -1 and text[colon + 1:colon + 2] == "/":
        text = text[colon + 2:]
    parts = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts).lower()


def load_guard(guard_path):
    spec = importlib.util.spec_from_file_location("private_guard", guard_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def open_below(root_fd, parts, create):
    """Opens the folder root/parts[0]/.../parts[-1] without following any link, creating the
    missing folders (mode 0700) relative to their parent's descriptor when create is set.
    Returns a descriptor; raises OSError (ELOOP for a link, ENOTDIR, ...) otherwise."""
    fd = os.dup(root_fd)
    try:
        for part in parts:
            try:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def init(private, template, guard_path, repo=None, git="git", before_writes=None):
    """Returns (findings, notes). before_writes, for tests only, runs between the two
    phases."""
    # Phase 1: checks, no write.
    guard = load_guard(guard_path)
    findings = [f"CP-1: {finding}" for finding in guard.check_dir(private, repo=repo, git=git)]
    if findings:
        return findings + ["nothing was written: fix the private folder first "
                           "(private_guard check-dir)"], []
    # The template is read once: the bytes written in phase 2 are the bytes parsed here, and
    # every rule (keys, SDK version, paths) is checked on this same parsed table.
    data, table, load = load_template(template)
    if table is None:
        return [f"template: {finding}" for finding in load] + ["nothing was written"], []
    findings += [f"template: {finding}" for finding in check_template_table(table)]
    real_private = canonical(private)
    project_base = os.path.join(real_private, PROJECT_DIR)
    # Links first: with a link in place, the paths below would resolve through it.
    findings += link_findings(real_private, [PROJECT_DIR, MANIFEST_NAME], "manifest")
    outputs = []
    for label, binary in binaries(table):
        value = binary.get("out_directory_path")
        parts = output_parts(real_private, project_base, value) if isinstance(value, str) \
            else None
        if parts is None:
            continue
        findings += link_findings(real_private, parts, f"{label}.out_directory_path")
        outputs.append((label, parts))
    if not findings:
        installed, _ = check_table(table, project_base, real_private)
        findings += [f"template, installed: {finding}" for finding in installed]
    if findings:
        return findings + ["nothing was written"], []
    if before_writes:
        before_writes()

    # Phase 2: writes, anchored to the root of the private folder.
    notes = []
    manifest = os.path.join(project_base, MANIFEST_NAME)
    try:
        root_fd = os.open(real_private, DIR_FLAGS)
    except OSError as error:
        return [f"cannot open the private folder {real_private}: {error.strerror}"], notes
    try:
        try:
            project_fd = open_below(root_fd, [PROJECT_DIR], create=True)
        except OSError as error:
            return [f"{project_base} changed during init ({error.strerror}): stopped before "
                    "writing the manifest"], notes
        try:
            fd = os.open(MANIFEST_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                         | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=project_fd)
        except FileExistsError:
            notes.append(f"{manifest} already exists: left as it is")
        except OSError as error:
            return [f"cannot create {manifest} ({error.strerror}): stopped"], notes
        else:
            with os.fdopen(fd, "wb") as target:
                target.write(data)
            notes.append(f"wrote {manifest}")
        finally:
            os.close(project_fd)
        for label, parts in outputs:
            out = os.path.join(real_private, *parts)
            existed = os.path.lexists(out)
            try:
                os.close(open_below(root_fd, parts, create=True))
            except OSError as error:
                return [f"{label}: {out} changed during init ({error.strerror}): stopped"], notes
            if not existed:
                notes.append(f"created {out}")
    finally:
        os.close(root_fd)
    check, _ = check_manifest(manifest, private)
    return check, notes


def report(findings, notes=(), ok_message="nothing found"):
    for note in notes:
        print(f"note: {note}")
    for finding in findings:
        print(f"FOUND: {finding}")
    if findings:
        print(f"{len(findings)} finding(s)")
        return 1
    print(f"OK: {ok_message}")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(prog="private_project", description=__doc__.split("\n")[0])
    parser.add_argument("--private-dir", default=os.environ.get("WC2010_PRIVATE_DIR"),
                        help="the private folder (default: $WC2010_PRIVATE_DIR)")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="the manifest template")
    parser.add_argument("--guard", default=DEFAULT_GUARD, help="path of private_guard.py")
    parser.add_argument("--repo", default=None, help="the repository, refused as private folder")
    parser.add_argument("--git", default="git", help="the git command")
    sub = parser.add_subparsers(dest="command", required=True)
    tpl = sub.add_parser("template", help="check the template of the repository")
    tpl.add_argument("--sdk-version", default=SDK_VERSION)
    sub.add_parser("init", help="copy the template into the private folder")
    chk = sub.add_parser("check", help="check the manifest of the private folder")
    chk.add_argument("--manifest", default=None,
                     help=f"default: <private folder>/{PROJECT_DIR}/{MANIFEST_NAME}")
    args = parser.parse_args(argv)

    if args.command == "template":
        return report(check_template(args.template, args.sdk_version),
                      ok_message="the template holds relative paths and no game data")
    if not args.private_dir:
        print("error: WC2010_PRIVATE_DIR is not set and --private-dir is not given")
        return 2
    if not os.path.isabs(args.private_dir):
        print(f"error: the private folder is not an absolute path: {args.private_dir}")
        return 2
    if args.command == "init":
        findings, notes = init(args.private_dir, args.template, args.guard, repo=args.repo,
                               git=args.git)
        return report(findings, notes, ok_message="the project is ready in the private folder")
    manifest = args.manifest or os.path.join(args.private_dir, PROJECT_DIR, MANIFEST_NAME)
    findings, resolved = check_manifest(manifest, args.private_dir)
    notes = [f"{label} -> {path}" for label, path in resolved.items()]
    return report(findings, notes, ok_message="every path resolves inside the private folder")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

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
  stage-config
            copies the test configuration of B2 (option C-a, D-021) from a local clone of
            project A into <private folder>/project/config/, and names it in the includes
            of the private manifest: at the pinned commit, the files project A's manifest
            includes for each binary, and their includes, transitively, without its C++
            fixes. Only git objects of that commit are read (no working tree, no hook).
            A file is copied byte for byte and never overwritten, with one exception, the
            derogation G-3 to C-a (D-021): config/default.toml is the pinned file without
            its one top-level function_table_base line, so that option F-a holds; the
            pinned original is kept intact in config/original/default.toml, which nothing
            includes. Any other case (no such line, several, another form, another file
            that sets the key) is refused.

It reads no XEX and runs no ReXGlue command. Only `init` and `stage-config` write, in two
phases:

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
import posixpath
import re
import stat
import subprocess
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

# Option C-a of B2 (D-021, docs/J2_B2_COMPATIBILITY.md §11.1): project A
# (CalinGraphics/fifa-world-cup-2010-recompiled) at the commit of the audit
# (docs/audit/EXISTING_PROJECTS.md). Its manifest is at pc/ and includes config/... for each
# binary: the same relative paths work from project/ of the private folder.
PROJECT_A_COMMIT = "498d18ae09175d4991b24b633a9a5f2e0e1cc73e"
PROJECT_A_MANIFEST = "pc/fifawc10_manifest.toml"
PROJECT_A_CONFIG = "pc/config"
CONFIG_DIR = "config"
MAX_INCLUDE_DEPTH = 32  # ReXGlue v0.11.0, src/codegen/config.cpp:24
# Option F-a: no value of function_table_base is imposed. A 0 does not undo an inherited
# value (MergeScalar, src/codegen/config.cpp:40-41): any occurrence is a conflict.
TABLE_BASE_KEY = "function_table_base"
# Derogation G-3 to C-a (D-021): the only change to the pinned configuration. The test copy
# of default.toml lacks its one top-level function_table_base line; the original is kept,
# intact, where no include reaches it.
G3_FILE = "default.toml"
G3_ORIGINAL = "original/default.toml"
G3_LINE = re.compile(rb"^function_table_base[ \t]*=[ \t]*(0[xX][0-9A-Fa-f]+|[0-9]+)[ \t]*$")


def g3_derive(data):
    """Derogation G-3: the test copy of the pinned default.toml, that is its bytes without
    the one line that sets function_table_base at the top level, and nothing else. Refused:
    no such line, the key named more than once (ambiguous), a line of another form, or a
    removal that changes the parsed table otherwise than by that key. Returns (copy, line
    number, problems)."""
    lines = data.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if TABLE_BASE_KEY.encode() in line]
    if not hits:
        return None, None, [f"G-3: {G3_FILE} names no {TABLE_BASE_KEY}: it is not the file "
                            "the derogation was decided on"]
    if len(hits) > 1:
        return None, None, [f"G-3: {G3_FILE} names {TABLE_BASE_KEY} {len(hits)} times: "
                            "ambiguous"]
    index = hits[0]
    if not G3_LINE.match(lines[index].rstrip(b"\r\n")):
        return None, None, [f"G-3: line {index + 1} of {G3_FILE} is not a plain "
                            f"`{TABLE_BASE_KEY} = <integer>` line"]
    copy = b"".join(lines[:index] + lines[index + 1:])
    try:
        original = tomllib.loads(data.decode("utf-8"))
        derived = tomllib.loads(copy.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return None, None, [f"G-3: {G3_FILE} is not TOML ({type(error).__name__})"]
    expected = {k: v for k, v in original.items() if k != TABLE_BASE_KEY}
    if TABLE_BASE_KEY not in original or derived != expected:
        return None, None, [f"G-3: removing line {index + 1} of {G3_FILE} changes more than "
                            f"its top-level {TABLE_BASE_KEY}"]
    return copy, index + 1, []


def g3_check(original, staged):
    """The problems of a staged default.toml against the kept original: it must be exactly
    g3_derive(original), byte for byte."""
    copy, _, problems = g3_derive(original)
    if problems:
        return problems
    if staged != copy:
        return [f"G-3: {CONFIG_DIR}/{G3_FILE} is not the original less its {TABLE_BASE_KEY} "
                "line: another change"]
    return []


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


class StageError(Exception):
    pass


def git_objects(git, source):
    """A reader of the git objects of a local clone: plumbing commands only, which run no
    hook and do not touch the working tree; system and global settings ignored."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0")

    def run(*args):
        try:
            result = subprocess.run([git, "-C", source, "-c", "core.fsmonitor=false",
                                     "-c", "core.hooksPath=" + os.devnull, *args],
                                    capture_output=True, env=env, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise StageError(f"git {args[0]}: {error}") from None
        if result.returncode != 0:
            text = result.stderr.decode("utf-8", "replace").strip().splitlines()
            raise StageError(f"git {args[0]}: {text[0] if text else result.returncode}")
        return result.stdout
    return run


def project_a_inputs(git, source, commit):
    """At `commit` of a local clone of project A: the files its manifest includes for each
    binary, and their includes, transitively (relative to the including file, at most 32
    levels, no loop), each a regular file (mode 100644) under pc/config/. Returns (files,
    includes, findings, notes): files maps a path relative to pc/config/ to its bytes;
    includes maps the XEX name of each binary to its includes, as project A writes them."""
    run = git_objects(git, source)
    findings, notes, files, includes = [], [], {}, {}
    try:
        resolved = run("rev-parse", "--verify", "--end-of-options",
                       commit + "^{commit}").decode().strip()
    except StageError as error:
        return {}, {}, [f"project A: commit {commit} not found in {source} ({error})"], []
    if resolved != commit:
        return {}, {}, [f"project A: {commit} resolves to {resolved}: give the full commit "
                        "id of option C-a"], []

    def blob(path):
        listed = run("ls-tree", "-z", "--full-tree", commit, "--", path)
        if not listed:
            raise StageError(f"{path} is not in commit {commit}")
        meta = listed.rstrip(b"\0").split(b"\t", 1)[0].decode().split()
        if meta[0] != "100644" or meta[1] != "blob":
            raise StageError(f"{path} has mode {meta[0]}: not a regular file")
        return run("cat-file", "blob", meta[2])

    def parse(path, data):
        try:
            return tomllib.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise StageError(f"{path}: not TOML ({type(error).__name__})") from None

    def visit(path, depth, chain):
        if depth > MAX_INCLUDE_DEPTH:
            raise StageError(f"{path}: includes deeper than {MAX_INCLUDE_DEPTH} levels")
        if not path.startswith(PROJECT_A_CONFIG + "/"):
            raise StageError(f"{path}: outside {PROJECT_A_CONFIG}/, not part of option C-a")
        if path in chain:
            raise StageError(f"{path}: circular include")
        rel = posixpath.relpath(path, PROJECT_A_CONFIG)
        data = files.get(rel)
        if data is None:
            data = files[rel] = blob(path)
        table = parse(path, data)
        for include in names(table, path):
            visit(posixpath.normpath(posixpath.join(posixpath.dirname(path), include)),
                  depth + 1, chain + [path])

    def names(table, label):
        value = table.get("includes", [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v and
                                                  not v.startswith("/") for v in value):
            raise StageError(f"{label}: includes is not a list of relative paths")
        return value

    try:
        manifest = parse(PROJECT_A_MANIFEST, blob(PROJECT_A_MANIFEST))
        if "includes" in manifest:
            raise StageError(f"{PROJECT_A_MANIFEST}: includes at the top level, not covered "
                             "by option C-a")
        if manifest.get("project", {}).get("hook_sources"):
            notes.append("project A names hook sources: not staged (option C-a, without "
                         "its C++ fixes)")
        binaries = [manifest.get("entrypoint")] + list(manifest.get("modules", []) or [])
        for index, binary in enumerate(binaries):
            if not isinstance(binary, dict):
                continue
            label = f"{PROJECT_A_MANIFEST} binary #{index}"
            xex = posixpath.basename(str(binary.get("file_path", ""))).lower()
            includes[xex] = names(binary, label)
            for include in includes[xex]:
                visit(posixpath.normpath(posixpath.join(posixpath.dirname(
                    PROJECT_A_MANIFEST), include)), 1, [])
    except StageError as error:
        return {}, {}, [f"project A: {error}"], notes
    return files, includes, findings, notes


def set_includes(text, plan):
    """The manifest text with `includes = []` replaced, in the table of each binary, by
    the includes of `plan` (one list per binary, in manifest order), or None if a binary
    table does not hold exactly one `includes = []` line."""
    lines = text.split("\n")
    tables, current = [], None
    for index, line in enumerate(lines):
        head = line.strip()
        if head.startswith("["):
            current = len(tables) if head in ("[entrypoint]", "[[modules]]") else None
            if current is not None:
                tables.append([])
        elif current is not None and head.replace(" ", "") == "includes=[]":
            tables[current].append(index)
    if len(tables) != len(plan) or any(len(found) != 1 for found in tables):
        return None
    for found, values in zip(tables, plan):
        lines[found[0]] = "includes = [" + ", ".join(
            '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
            for value in values) + "]"
    return "\n".join(lines)


def stage_config(private, source, guard_path, repo=None, git="git",
                 commit=PROJECT_A_COMMIT):
    """Option C-a (D-021): copies the test configuration of project A into project/config/
    and names it in the private manifest. Two phases, as init. Returns (findings, notes)."""
    guard = load_guard(guard_path)
    findings = [f"CP-1: {finding}" for finding in guard.check_dir(private, repo=repo, git=git)]
    if findings:
        return findings + ["nothing was written: fix the private folder first"], []
    real_private = canonical(private)
    manifest = os.path.join(real_private, PROJECT_DIR, MANIFEST_NAME)
    findings += link_findings(real_private, [PROJECT_DIR, MANIFEST_NAME], "manifest")
    if findings:
        return findings + ["nothing was written"], []
    try:
        with open(manifest, "rb") as handle:
            data = handle.read()
        text = data.decode("utf-8")
        table = tomllib.loads(text)
    except FileNotFoundError:
        return [f"{manifest} is missing: run init first", "nothing was written"], []
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        return [f"{manifest}: {type(error).__name__}", "nothing was written"], []
    files, includes, found, notes = project_a_inputs(git, source, commit)
    findings += found
    plan = []
    for label, binary in binaries(table):
        xex = os.path.basename(str(binary.get("file_path", ""))).lower()
        if binary.get("includes", []) != []:
            findings.append(f"{label}.includes is already set: stage-config writes only "
                            "into a copy with no include")
        if xex not in includes:
            findings.append(f"{label}: project A has no binary for {xex or 'this file'}")
        plan.append(includes.get(xex, []))
    staged = None if findings else set_includes(text, plan)
    if not findings and staged is None:
        findings.append(f"{manifest}: each binary table must hold one `includes = []` line")
    for rel in files:
        parts = [PROJECT_DIR, CONFIG_DIR] + rel.split("/")
        findings += link_findings(real_private, parts, f"{CONFIG_DIR}/{rel}")
        if os.path.lexists(os.path.join(real_private, *parts)):
            findings.append(f"{PROJECT_DIR}/{CONFIG_DIR}/{rel} exists: never overwritten")
    if not findings:
        # G-3: the one derogation; any other value of the key would still be inherited.
        if G3_FILE not in files:
            findings.append(f"G-3: project A includes no {G3_FILE}")
        else:
            copy, line, problems = g3_derive(files[G3_FILE])
            findings += problems
        for rel, content in files.items():
            if rel != G3_FILE and TABLE_BASE_KEY in tomllib.loads(content.decode("utf-8")):
                findings.append(f"{CONFIG_DIR}/{rel} sets {TABLE_BASE_KEY}: another inherited "
                                "value, not covered by G-3")
        parts = [PROJECT_DIR, CONFIG_DIR] + G3_ORIGINAL.split("/")
        findings += link_findings(real_private, parts, f"{CONFIG_DIR}/{G3_ORIGINAL}")
        if os.path.lexists(os.path.join(real_private, *parts)):
            findings.append(f"{PROJECT_DIR}/{CONFIG_DIR}/{G3_ORIGINAL} exists: never "
                            "overwritten")
    if findings:
        return findings + ["nothing was written"], notes
    writes = dict(files)
    writes[G3_ORIGINAL] = files[G3_FILE]
    writes[G3_FILE] = copy

    root_fd = os.open(real_private, DIR_FLAGS)
    try:
        for rel, content in writes.items():
            *folders, name = rel.split("/")
            folder_fd = open_below(root_fd, [PROJECT_DIR, CONFIG_DIR] + folders, create=True)
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                             getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=folder_fd)
                with os.fdopen(fd, "wb") as target:
                    target.write(content)
            except OSError as error:
                return [f"{CONFIG_DIR}/{rel}: {error.strerror}: stopped"], notes
            finally:
                os.close(folder_fd)
        project_fd = open_below(root_fd, [PROJECT_DIR], create=False)
        temporary = "." + MANIFEST_NAME + ".stage"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                         getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=project_fd)
            with os.fdopen(fd, "wb") as target:
                target.write(staged.encode("utf-8"))
            os.rename(temporary, MANIFEST_NAME, src_dir_fd=project_fd, dst_dir_fd=project_fd)
        except OSError as error:
            return [f"{manifest}: {error.strerror}: stopped"], notes
        finally:
            os.close(project_fd)
    finally:
        os.close(root_fd)
    notes.append(f"project A at {commit}: {len(files)} files copied into "
                 f"{PROJECT_DIR}/{CONFIG_DIR}/, unmodified but one")
    notes.append(f"G-3: {CONFIG_DIR}/{G3_FILE} is the pinned file without its line {line} "
                 f"({TABLE_BASE_KEY}); the original is kept in {CONFIG_DIR}/{G3_ORIGINAL}, "
                 "included by nothing")
    for label, values in zip([label for label, _ in binaries(table)], plan):
        notes.append(f"{label}.includes = {values}")
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
    stg = sub.add_parser("stage-config", help="copy the test configuration of project A "
                                              "(option C-a, D-021) into project/config/")
    stg.add_argument("--source", required=True, help="a local clone of project A")
    stg.add_argument("--commit", default=PROJECT_A_COMMIT,
                     help="the full commit id (default: that of option C-a)")
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
    if args.command == "stage-config":
        findings, notes = stage_config(args.private_dir, args.source, args.guard,
                                       repo=args.repo, git=args.git, commit=args.commit)
        return report(findings, notes, ok_message="the test configuration is staged")
    manifest = args.manifest or os.path.join(args.private_dir, PROJECT_DIR, MANIFEST_NAME)
    findings, resolved = check_manifest(manifest, args.private_dir)
    notes = [f"{label} -> {path}" for label, path in resolved.items()]
    return report(findings, notes, ok_message="every path resolves inside the private folder")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

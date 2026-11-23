#!/usr/bin/env python3
"""Sets up and checks the ReXGlue codegen project in the private folder (J2 step A5).

Commands:
  template  checks the manifest template of the repository: the rules of `check`, plus
            the pinned SDK version and only the keys a template may hold, so no address of
            the game (CP-7).
  init      copies the template into $WC2010_PRIVATE_DIR/project/ and creates the output
            folders it names. The private folder must pass CP-1 (private_guard check-dir)
            first. A manifest already there is never overwritten.
  check     checks the manifest of the private folder: every host path is relative and
            resolves inside the private folder, both XEX files lie under game_root, and
            every output folder is a dedicated folder under generated/, shared with no
            other binary. Keys added in phase B (addresses) are allowed here.

It reads no XEX and runs no ReXGlue command. `init` writes only in the private folder.
Paths that exist are resolved with their symbolic links, so a link that leaves the private
folder is refused.

Exit status: 0 when nothing is found, 1 when something is found, 2 on bad usage.
"""

import argparse
import importlib.util
import os
import re
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


def within(path, folder):
    path, folder = canonical(path), canonical(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def load_manifest(path):
    """Returns (table, findings)."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle), []
    except OSError as error:
        return None, [f"cannot read the manifest {path}: {error.strerror}"]
    except tomllib.TOMLDecodeError as error:
        return None, [f"the manifest {path} is not valid TOML: {error}"]


def host_path_findings(label, value):
    """A host path of the manifest must be a relative string; returns its findings."""
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


def check_manifest(manifest_path, private):
    """The rules of `check`. Returns (findings, resolved) with resolved paths by label."""
    table, findings = load_manifest(manifest_path)
    if table is None:
        return findings, {}
    base = os.path.dirname(os.path.abspath(manifest_path))
    resolved = {}

    def resolve(label, value):
        problems = host_path_findings(label, value)
        if problems:
            findings.extend(problems)
            return None
        path = canonical(os.path.join(base, value))
        resolved[label] = path
        if private and not within(path, private):
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

    generated = os.path.join(canonical(private), GENERATED_DIR) if private else None
    outputs = []
    guest_paths = set()
    for label, binary in binaries(table):
        xex = resolve(f"{label}.file_path", binary.get("file_path"))
        if xex and game_root and (xex == game_root or not within(xex, game_root)):
            findings.append(f"{label}.file_path is not under game_root: ReXGlue refuses it")
        out = resolve(f"{label}.out_directory_path", binary.get("out_directory_path"))
        if out:
            if generated and (not within(out, generated) or out == generated):
                findings.append(f"{label}.out_directory_path must be a folder inside "
                                f"{GENERATED_DIR}/, one per binary: {out}")
            if game_root and (within(out, game_root) or within(game_root, out)):
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
            if within(out, other) or within(other, out):
                findings.append(f"{label} and {other_label} share an output folder: codegen "
                                "deletes the outputs it did not write")
    return findings, resolved


def check_template(template_path, sdk_version=SDK_VERSION):
    """The rules of `check` without a private folder, plus the template only rules."""
    findings, _ = check_manifest(template_path, private=None)
    table, _ = load_manifest(template_path)
    if table is None:
        return findings
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


def init(private, template, guard_path, repo=None, git="git"):
    """Returns (findings, notes)."""
    guard = load_guard(guard_path)
    findings = guard.check_dir(private, repo=repo, git=git)
    if findings:
        return [f"CP-1: {finding}" for finding in findings] + \
            ["nothing was written: fix the private folder first (private_guard check-dir)"], []
    template_findings = check_template(template)
    if template_findings:
        return [f"template: {finding}" for finding in template_findings], []
    notes = []
    private = canonical(private)
    project = os.path.join(private, PROJECT_DIR)
    os.makedirs(project, mode=0o700, exist_ok=True)
    manifest = os.path.join(project, MANIFEST_NAME)
    if os.path.lexists(manifest):
        notes.append(f"{manifest} already exists: left as it is")
    else:
        with open(template, "rb") as source:
            data = source.read()
        fd = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as target:
            target.write(data)
        notes.append(f"wrote {manifest}")
    table, _ = load_manifest(manifest)
    if table is not None:
        for label, binary in binaries(table):
            value = binary.get("out_directory_path")
            if isinstance(value, str) and not host_path_findings(label, value):
                out = os.path.normpath(os.path.join(project, value))
                if within(out, os.path.join(private, GENERATED_DIR)) and not os.path.lexists(out):
                    os.makedirs(out, mode=0o700)
                    notes.append(f"created {out}")
    check_findings, _ = check_manifest(manifest, private)
    return check_findings, notes


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

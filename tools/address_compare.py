#!/usr/bin/env python3
"""Compares ReXGlue address lists and diagnostics with configured entries (J2 step A8-bis).

Method M1 of docs/J2_A8_ADDRESS_VALIDATION.md, strictly analytic: the tool reads lists of
addresses, a codegen log and a record of manual examinations. It reads no image, no XEX,
no generated code body and no game data, and it never writes outside the private folder.

Inputs, all inside $WC2010_PRIVATE_DIR:
  --entries KIND=PATH   ReXGlue configuration (TOML) whose [functions] entries are of one
                        kind: `function` (function starts, autofix seeds) or `pointer`
                        (code pointers). setjmp_address and longjmp_address found there are
                        kind `crt`. Repeatable.
  --mappings-with PATH  the generated <prefix>_init.cpp of the run WITH the entries
  --mappings-without PATH  the same file of a run WITHOUT them (optional)
  --log PATH            the log of the run with the entries: its diagnostics
  --claims PATH         a TOML record of manual N2 examinations (hooks, data references)
  --out PATH            the detailed report (JSON), written only inside the private folder

Evidence levels (docs/J2_A8_ADDRESS_VALIDATION.md section 3):
  N0  read without configuration error;
  N1  no diagnostic for the entry, and a function generated at that address;
  N2  instruction reference examined (manual record only: see the limits);
  N3  data value or content, never verified: every data value and every code pointer
      stays "not verified in the data".
It fails closed: anything it cannot establish stays at the lower level, and an element
that needs a level it does not reach is a STOP. It never concludes that addresses are
validated, nor that the image is identical to project A's.

Limit: the generated code comments each instruction (`// mnemonic operands`) without its
address, and two fused instructions share one comment (src/codegen/function_graph.cpp
641-712), so instruction addresses cannot be recovered reliably from it. N2 is therefore
not computed: it comes from a manual examination record, checked for consistency.

Guarantees: every path is checked before any file is read; claim fields have exact types
(a string "false" or the integer 1 is no boolean, true is no address); the standard output
holds no address (messages cite no line content, STOP lines name claims by their index, and
a last redaction replaces any address left); the report is created anchored to the private
root, every folder opened with O_NOFOLLOW from its parent's descriptor.

Exit status: 0 report written, no STOP; 1 report written, with STOP; 2 refused (bad usage,
unknown or partial format, badly typed claim, path outside the private folder): nothing is
written.
"""

import argparse
import json
import os
import re
import stat
import sys
import tomllib

KINDS = ("function", "pointer")
REQUIRED = {"function": "N1", "pointer": "N1", "crt": "N2", "hook": "N2", "data": "N2"}
LEVELS = ("refused", "N0", "N1", "N2")
ADDRESS_KEY = re.compile(r"^0[xX][0-9A-Fa-f]{1,8}$")

# kPPCFuncMappings, resources/templates/codegen/init_cpp.inja:34-37.
MAPPINGS_START = "const PPCFuncMapping kPPCFuncMappings[] = {"
MAPPING_LINE = re.compile(r"^\t\{ 0x([0-9A-F]{1,8}), ([A-Za-z_][A-Za-z0-9_]*) \},$")
MAPPINGS_END = "\t{ 0, nullptr }"

# Diagnostics about entries. The message text is searched anywhere in a log line, so the
# logger's prefix does not matter.
HEX = r"0x([0-9A-Fa-f]{8})"
DIAGNOSTICS = [
    # src/codegen/phase_validate.cpp:57,61,78
    ("not_entry_point", re.compile(r"functions " + HEX + r" is not a function entry point$")),
    ("outranked", re.compile(r"functions " + HEX + r" outranked by \S+$")),
    ("split", re.compile(r"functions " + HEX + r" size 0x[0-9A-Fa-f]+ split by \S+ entry "
                         r"point 0x[0-9A-Fa-f]{8}$")),
    # src/codegen/phase_discover.cpp:78,94
    ("no_code_region", re.compile(r"Analyze: function " + HEX + r" not in any code region$")),
    ("no_blocks", re.compile(r"Analyze: no blocks found for function " + HEX + r"$")),
    # src/codegen/config.cpp:227-262
    ("config_error", re.compile(r"Invalid \[functions\] entry at " + HEX + r": .+$")),
    ("config_error", re.compile(r"Function " + HEX + r": .+$")),
]
# src/codegen/phase_validate.cpp:131,167,178, printed by AnalysisErrorLog::PrintReport as
# "  0xTARGET from 0xSITE: <message>" (src/codegen/analyze.cpp:103-129). The run fails and
# writes nothing.
ERRORS = [
    ("unresolved_call", re.compile(r"(?:bl|b) " + HEX + r" from " + HEX + r" (?:has a target "
                                   r"in no function|in \S+ has no CallEdge)$")),
    ("millicode", re.compile(r"(?:bl|b) " + HEX + r" from " + HEX + r" is inside a millicode "
                             r"run, off its entries$")),
]
FAILED_RUN = re.compile(r"Validation failed: (\d+) unresolved calls, (\d+) millicode errors")
INVALID_KEY = re.compile(r"Invalid function address key: (\S+)")
# A line that talks about an entry but matches none of the patterns above is an unknown
# format: refused rather than ignored.
SUSPECT = re.compile(r"functions 0x|Analyze: (function|no blocks)|\[functions\]| from 0x"
                     r"[0-9A-Fa-f]{8}")


class Refused(Exception):
    """Unknown or partial input format, or a path outside the private folder."""


def read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise Refused(f"cannot read {path}: {error}") from None


def parse_mappings(path):
    """The addresses of kPPCFuncMappings. Refuses a missing, partial or unknown list, and an
    address listed twice."""
    lines = read_text(path).split("\n")
    try:
        start = lines.index(MAPPINGS_START)
    except ValueError:
        raise Refused(f"{path}: no kPPCFuncMappings list") from None
    addresses = {}
    for number, line in enumerate(lines[start + 1:], start + 2):
        if line == MAPPINGS_END:
            if number >= len(lines) or lines[number] != "};":
                raise Refused(f"{path}:{number}: kPPCFuncMappings does not end with '}};'")
            return addresses
        match = MAPPING_LINE.match(line)
        if not match:
            raise Refused(f"{path}:{number}: unknown kPPCFuncMappings line")
        address = int(match.group(1), 16)
        if address in addresses:
            raise Refused(f"{path}:{number}: a function is listed twice")
        addresses[address] = match.group(2)
    raise Refused(f"{path}: kPPCFuncMappings has no '{{ 0, nullptr }}' terminator")


def parse_log(path):
    """Diagnostics by address, errors and whether the run failed. An empty log, or a line
    about an entry in no known format, is refused."""
    text = read_text(path)
    if not text.strip():
        raise Refused(f"{path}: the log is empty: no diagnostic to rely on")
    diagnostics, errors, failed = {}, [], None
    for number, line in enumerate(text.split("\n"), 1):
        line = line.rstrip()
        summary = FAILED_RUN.search(line)
        if summary:
            counts = (int(summary.group(1)), int(summary.group(2)))
            if failed is not None and failed != counts:
                raise Refused(f"{path}:{number}: two different failure summaries")
            failed = counts
            continue
        if INVALID_KEY.search(line):
            raise Refused(f"{path}:{number}: ReXGlue refused a [functions] key: fix the "
                          "configuration first")
        found = False
        for kind, pattern in ERRORS:
            match = pattern.search(line)
            if match:
                errors.append((kind, int(match.group(1), 16), int(match.group(2), 16)))
                found = True
                break
        if found:
            continue
        for kind, pattern in DIAGNOSTICS:
            match = pattern.search(line)
            if match:
                diagnostics.setdefault(int(match.group(1), 16), []).append(kind)
                found = True
                break
        if not found and SUSPECT.search(line):
            raise Refused(f"{path}:{number}: diagnostic in an unknown format")
    if failed is None:
        if errors:
            raise Refused(f"{path}: errors without the 'Validation failed' summary: partial log")
        return diagnostics, errors, False
    found = (sum(1 for k, _, _ in errors if k == "unresolved_call"),
             sum(1 for k, _, _ in errors if k == "millicode"))
    if found != failed:
        raise Refused(f"{path}: the summary counts {failed[0]} unresolved calls and {failed[1]} "
                      f"millicode errors, the log lists {found[0]} and {found[1]}: partial log")
    return diagnostics, errors, True


def parse_entries(path, kind):
    """(address, kind) pairs of a ReXGlue configuration: [functions] keys of the given kind,
    setjmp_address and longjmp_address as `crt`."""
    try:
        table = tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as error:
        raise Refused(f"{path}: not valid TOML: {error}") from None
    entries = []
    functions = table.get("functions", {})
    if not isinstance(functions, dict):
        raise Refused(f"{path}: [functions] is not a table")
    for key, value in functions.items():
        if not ADDRESS_KEY.match(key):
            raise Refused(f"{path}: a [functions] key is not a 0x address")
        if not isinstance(value, dict):
            raise Refused(f"{path}: a [functions] entry is not a table")
        address = int(key, 16)
        if address % 4:
            raise Refused(f"{path}: a [functions] key is not 4 byte aligned")
        entries.append((address, kind, f"[functions].{key}"))
    for key in ("setjmp_address", "longjmp_address"):
        if key in table:
            value = table[key]
            if type(value) is not int or value < 0 or value > 0xFFFFFFFF or value % 4:
                raise Refused(f"{path}: {key} is not an aligned 32 bit address")
            entries.append((value, "crt", key))
    return entries


def parse_claims(path):
    """Manual N2 examination records: [[claim]] tables."""
    try:
        table = tomllib.loads(read_text(path))
    except tomllib.TOMLDecodeError as error:
        raise Refused(f"{path}: not valid TOML: {error}") from None
    claims = table.get("claim", [])
    if not isinstance(claims, list) or set(table) - {"claim"}:
        raise Refused(f"{path}: only [[claim]] tables are expected")
    out = []
    for index, claim in enumerate(claims):
        label = f"{path} [[claim]] #{index}"
        if not isinstance(claim, dict):
            raise Refused(f"{label}: not a table")
        unknown = set(claim) - {"name", "kind", "address", "offset", "referenced_by",
                                "examined", "boot_critical", "expected", "observed"}
        if unknown:
            raise Refused(f"{label}: unknown keys {sorted(unknown)}")
        if claim.get("kind") not in ("crt", "hook", "data"):
            raise Refused(f"{label}: kind must be crt, hook or data")
        if not isinstance(claim.get("name"), str) or not claim["name"].strip():
            raise Refused(f"{label}: name is missing")
        # Exact types: a TOML string "false" is not false, and true is not the integer 1.
        address = claim.get("address")
        if type(address) is not int or not 0 <= address <= 0xFFFFFFFF:
            raise Refused(f"{label}: address is not a 32 bit integer")
        for key in ("offset", "referenced_by"):
            if key in claim and type(claim[key]) is not int:
                raise Refused(f"{label}: {key} is not an integer")
        for key in ("examined", "boot_critical"):
            if key in claim and type(claim[key]) is not bool:
                raise Refused(f"{label}: {key} must be true or false")
        for key in ("expected", "observed"):
            if key in claim and (not isinstance(claim[key], str) or not claim[key].strip()):
                raise Refused(f"{label}: {key} must be a non empty instruction sequence")
        if claim.get("examined") is True and not ("expected" in claim and "observed" in claim):
            raise Refused(f"{label}: an examined claim needs both expected and observed")
        out.append(claim)
    return out


def same_sequence(claim):
    """Expected and observed sequences, as text, equal once their spacing is normalised."""
    return " ".join(claim["expected"].split()) == " ".join(claim["observed"].split())


def evaluate(entries, mappings_with, mappings_without, log, claims):
    """Levels, notes and STOP reasons. Returns the report dictionary."""
    diagnostics, errors, failed = log
    results = []
    stops = []
    by_address = {}
    for address, kind, origin in entries:
        by_address.setdefault(address, []).append((kind, origin))

    for address, kind, origin in entries:
        notes = []
        level = "N0"
        kinds_here = {k for k, _ in by_address[address]}
        if len(kinds_here) > 1 or len(by_address[address]) > 1:
            notes.append("collision: the address is configured more than once"
                         f" ({', '.join(sorted(o for _, o in by_address[address]))})")
        found = diagnostics.get(address, [])
        if "config_error" in found:
            level = "refused"
            notes.append("ReXGlue reported a configuration error for the entry")
        elif failed:
            notes.append("the run failed (unresolved calls or millicode errors): nothing is "
                         "established beyond N0")
        elif found:
            notes.append("ReXGlue diagnostics: " + ", ".join(sorted(set(found))))
            if {"outranked", "split"} & set(found):
                notes.append("collision with another function")
        elif notes and notes[0].startswith("collision"):
            pass
        elif address in mappings_with:
            level = "N1"
        elif mappings_without is not None and address in mappings_without:
            level = "N1"
            notes.append("discovered by the run without the entries")
        else:
            notes.append("present in the configuration only: no function generated at this "
                         "address, and no diagnostic")
        if kind == "pointer":
            notes.append("pointer not verified in the data (N3)")
        if kind == "crt":
            notes.append("N2 needs a manual examination record (crt claim)")
        results.append({"address": f"0x{address:08X}", "kind": kind, "origin": origin,
                        "level": level, "required": REQUIRED[kind], "notes": notes})

    known_functions = set(mappings_with)
    claim_results = []
    for claim in claims:
        notes = []
        address = claim["address"]
        kind = claim["kind"]
        level = "N0"
        if claim.get("examined") is not True:
            notes.append("not examined: no instruction reference established")
        elif kind in ("crt", "hook"):
            if address not in known_functions:
                notes.append("the examined function is not in kPPCFuncMappings: inconsistent "
                             "reference")
            elif failed or diagnostics.get(address):
                notes.append("ReXGlue diagnostics or a failed run for this function")
            elif not same_sequence(claim):
                notes.append("the observed sequence differs from the expected one")
            else:
                level = "N2"
        else:  # data
            ref = claim.get("referenced_by")
            offset = claim.get("offset", 0)
            if type(offset) is not int or not -0x8000 <= offset <= 0x7FFF:
                notes.append("invalid data offset: not a signed 16 bit displacement")
            elif type(ref) is not int or ref not in known_functions:
                notes.append("the referencing function is not in kPPCFuncMappings: "
                             "inconsistent reference")
            elif not same_sequence(claim):
                notes.append("the observed reference differs from the expected one")
            else:
                level = "N2"
            notes.append("data value not verified (N3)")
        claim_results.append({"name": claim["name"], "kind": kind,
                              "address": f"0x{address:08X}", "level": level,
                              "required": "N2",
                              "boot_critical": claim.get("boot_critical") is True,
                              "notes": notes})

    # A crt entry reaches N2 only through a crt claim examined at the same address.
    crt_claimed = {c["address"] for c in claim_results if c["kind"] == "crt" and
                   c["level"] == "N2"}
    for result in results:
        if result["kind"] == "crt" and result["level"] == "N1" and \
                result["address"] in crt_claimed:
            result["level"] = "N2"
            result["notes"] = [n for n in result["notes"] if not n.startswith("N2 needs")]
    # STOP cases (docs/J2_A8_ADDRESS_VALIDATION.md section 4). A function start or a pointer
    # below N1 is set aside and analysed again (M3), not a stop.
    for result in results:
        if result["kind"] == "crt" and result["level"] != "N2":
            stops.append(f"{result['origin']} below N2 (PB-2 stop)")
    for index, claim in enumerate(claim_results):
        if claim["level"] != "N2" and (claim["boot_critical"] or claim["kind"] == "crt"):
            stops.append(f"claim #{index} ({claim['kind']}) below N2: see the report")
    if failed:
        stops.append(f"the generation failed: {len(errors)} unresolved call or millicode "
                     "error(s); add seeds and generate again")

    summary = {}
    for item in results + claim_results:
        bucket = summary.setdefault(item["kind"], {level: 0 for level in LEVELS})
        bucket[item["level"]] += 1
    return {
        "method": "M1 (docs/J2_A8_ADDRESS_VALIDATION.md): N0 to N2 at best; data values and "
                  "code pointers stay N3, not verified in the data. This is not a validation "
                  "of all addresses, nor a proof of identity with project A.",
        "summary": summary,
        "stops": stops,
        "errors": [{"kind": k, "target": f"0x{t:08X}", "site": f"0x{s:08X}"}
                   for k, t, s in errors],
        "entries": results,
        "claims": claim_results,
    }


def within(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def report_parts(private, out):
    """The components of the report path below the private root, taken from the path as
    given (no link followed), or None if it is not below it."""
    target = os.path.normpath(out)
    for root in (os.path.normpath(os.path.abspath(private)), os.path.realpath(private)):
        rel = os.path.relpath(target, root)
        parts = rel.split(os.sep)
        if rel != os.curdir and parts[0] != os.pardir:
            return parts
    return None


def check_paths(private, inputs, out):
    """Every path, before anything is read or written. Returns the report components."""
    if not private or not os.path.isabs(private) or not os.path.isdir(private):
        raise Refused("WC2010_PRIVATE_DIR must be an absolute path to an existing folder")
    if os.path.realpath(private).startswith("/nix/store/"):
        raise Refused("the private folder is in /nix/store")
    for path in inputs:
        if not os.path.isabs(path) or not within(path, private):
            raise Refused(f"input outside the private folder, or not absolute: {path}")
    if not os.path.isabs(out):
        raise Refused(f"the report path is not absolute: {out}")
    parts = report_parts(private, out)
    if parts is None or not within(os.path.dirname(out), private):
        raise Refused(f"report outside the private folder: {out}")
    return parts


DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
# Test hook, empty in normal use: runs between the path checks and the report creation.
BEFORE_REPORT_OPEN_FOR_TESTING = None


def write_report(private, parts, report):
    """Creates the report below the private root: every folder is opened with O_NOFOLLOW
    from its parent's descriptor, and the file with O_CREAT | O_EXCL | O_NOFOLLOW. A link
    put in place of a folder after the checks makes the creation fail; nothing is
    overwritten."""
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if BEFORE_REPORT_OPEN_FOR_TESTING:
        BEFORE_REPORT_OPEN_FOR_TESTING()
    try:
        fd = os.open(os.path.realpath(private), DIR_FLAGS)
    except OSError as error:
        raise Refused(f"cannot open the private folder: {error.strerror}") from None
    try:
        for part in parts[:-1]:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        out = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                      | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=fd)
    except OSError as error:
        raise Refused(f"cannot create the report: {error.strerror}") from None
    finally:
        os.close(fd)
    with os.fdopen(out, "w", encoding="utf-8") as handle:
        handle.write(data)


def run(args):
    # Every path is checked before any file is read (P-43).
    specs = []
    for spec in args.entries:
        kind, sep, path = spec.partition("=")
        if not sep or kind not in KINDS or not path:
            raise Refused(f"--entries takes KIND=PATH with KIND in {KINDS}")
        specs.append((kind, path))
    inputs = [path for _, path in specs]
    inputs += [p for p in (args.mappings_with, args.mappings_without, args.log, args.claims)
               if p]
    parts = check_paths(args.private_dir, inputs, args.out)
    if not specs and not args.claims:
        raise Refused("nothing to compare: give --entries or --claims")
    entries = []
    for kind, path in specs:
        entries += parse_entries(path, kind)
    mappings_with = parse_mappings(args.mappings_with)
    mappings_without = parse_mappings(args.mappings_without) if args.mappings_without else None
    log = parse_log(args.log)
    claims = parse_claims(args.claims) if args.claims else []
    report = evaluate(entries, mappings_with, mappings_without, log, claims)
    write_report(args.private_dir, parts, report)
    return report


# Defence in depth for the standard output: any hexadecimal address or 8 digit word left in
# a message is replaced (P-44). The report, in the private folder, keeps the details.
ADDRESS_LIKE = re.compile(r"0[xX][0-9A-Fa-f]+|\b[0-9A-Fa-f]{8}\b")


def redact(text):
    return ADDRESS_LIKE.sub("<address>", text)


def main(argv):
    parser = argparse.ArgumentParser(prog="address_compare", description=__doc__.split("\n")[0])
    parser.add_argument("--private-dir", default=os.environ.get("WC2010_PRIVATE_DIR"))
    parser.add_argument("--entries", action="append", default=[], metavar="KIND=PATH")
    parser.add_argument("--mappings-with", required=True)
    parser.add_argument("--mappings-without")
    parser.add_argument("--log", required=True, help="log of the run with the entries")
    parser.add_argument("--claims")
    parser.add_argument("--out", required=True, help="report (JSON), in the private folder")
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except Refused as error:
        print(f"REFUSED: {redact(str(error))}")
        print("nothing was written")
        return 2
    # Aggregated output only: counts by kind and level, and the stop reasons.
    print(report["method"])
    for kind in sorted(report["summary"]):
        counts = report["summary"][kind]
        print(f"{kind}: " + ", ".join(f"{level} {counts[level]}" for level in LEVELS))
    for stop in report["stops"]:
        print(f"STOP: {redact(stop)}")
    print(f"report: {args.out}")
    return 1 if report["stops"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

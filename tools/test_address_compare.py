#!/usr/bin/env python3
"""Tests of tools/address_compare.py (J2 step A8-bis), on synthetic fixtures only.

The fixtures are written by the tests in the formats of the ReXGlue v0.11.0 source
(kPPCFuncMappings template, diagnostic and error messages). Their addresses are synthetic
(0x8C01xxxx): no game address, no XEX, no image, no generated code body.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("address_compare",
                                              os.path.join(HERE, "address_compare.py"))
ac = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ac)

A, B, C, D = 0x8C010000, 0x8C010040, 0x8C010080, 0x8C0100C0
PREFIX = "[2026-01-01 00:00:00.000] [codegen] [warning] "


def mappings_text(addresses):
    lines = ["// generated", "const PPCFuncMapping kPPCFuncMappings[] = {"]
    lines += [f"\t{{ 0x{a:X}, sub_{a:08X} }}," for a in addresses]
    lines += ["\t{ 0, nullptr }", "};", ""]
    return "\n".join(lines)


def entries_text(addresses, extra=""):
    return extra + "[functions]\n" + "".join(f"0x{a:08X} = {{}}\n" for a in addresses)


class Folder(unittest.TestCase):
    def setUp(self):
        self.top = tempfile.mkdtemp(prefix="ac-test-")
        self.private = os.path.join(self.top, "private")
        os.mkdir(self.private, 0o700)

    def tearDown(self):
        shutil.rmtree(self.top, ignore_errors=True)

    def file(self, name, text):
        path = os.path.join(self.private, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def run_tool(self, entries=(), with_=(A, B), without=None, log=("info: done",),
                 claims=None, out="report.json", extra_args=()):
        argv = ["--private-dir", self.private]
        for kind, text in entries:
            argv += ["--entries", f"{kind}={self.file(kind + '.toml', text)}"]
        argv += ["--mappings-with", self.file("with_init.cpp", mappings_text(with_))]
        if without is not None:
            argv += ["--mappings-without", self.file("without_init.cpp", mappings_text(without))]
        argv += ["--log", self.file("codegen.log", "\n".join(log) + "\n")]
        if claims is not None:
            argv += ["--claims", self.file("claims.toml", claims)]
        out_path = out if os.path.isabs(out) else os.path.join(self.private, out)
        argv += ["--out", out_path] + list(extra_args)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = ac.main(argv)
        report = None
        if os.path.exists(out_path) and status != 2:
            with open(out_path, encoding="utf-8") as handle:
                report = json.load(handle)
        return status, stdout.getvalue(), report, out_path

    def entry(self, report, address):
        return next(e for e in report["entries"] if e["address"] == f"0x{address:08X}")


class LevelTests(Folder):
    def test_clean_entries_reach_n1(self):
        status, _, report, _ = self.run_tool(entries=[("function", entries_text([A, B]))])
        self.assertEqual(status, 0)
        self.assertEqual({e["level"] for e in report["entries"]}, {"N1"})
        self.assertEqual(report["stops"], [])

    def test_entry_in_configuration_only_stays_n0(self):
        # False positive 1: configured, accepted without warning, but never generated.
        status, _, report, _ = self.run_tool(entries=[("function", entries_text([A, C]))],
                                             with_=(A, B))
        self.assertEqual(status, 0)
        self.assertEqual(self.entry(report, C)["level"], "N0")
        self.assertIn("configuration only", " ".join(self.entry(report, C)["notes"]))

    def test_entry_discovered_without_the_entries_is_n1(self):
        _, _, report, _ = self.run_tool(entries=[("function", entries_text([C]))],
                                        with_=(A,), without=(A, C))
        self.assertEqual(self.entry(report, C)["level"], "N1")

    def test_each_diagnostic_keeps_the_entry_at_n0(self):
        messages = {
            "not_entry_point": f"functions 0x{C:08X} is not a function entry point",
            "outranked": f"functions 0x{C:08X} outranked by pdata",
            "split": f"functions 0x{C:08X} size 0x40 split by pdata entry point 0x{D:08X}",
            "no_code_region": f"Analyze: function 0x{C:08X} not in any code region",
            "no_blocks": f"Analyze: no blocks found for function 0x{C:08X}",
        }
        for kind, message in messages.items():
            with self.subTest(kind):
                for name in os.listdir(self.private):
                    os.remove(os.path.join(self.private, name))
                status, _, report, _ = self.run_tool(
                    entries=[("function", entries_text([C]))], with_=(A, C),
                    log=(PREFIX + message,))
                self.assertEqual(status, 0)
                self.assertEqual(self.entry(report, C)["level"], "N0")
                self.assertIn(kind, " ".join(self.entry(report, C)["notes"]))

    def test_function_collision_is_reported(self):
        # False positive 3: outranked or split by another function, or configured twice.
        _, _, report, _ = self.run_tool(
            entries=[("function", entries_text([C]))], with_=(A, C),
            log=(PREFIX + f"functions 0x{C:08X} outranked by pdata",))
        self.assertIn("collision", " ".join(self.entry(report, C)["notes"]))
        _, _, report, _ = self.run_tool(
            entries=[("function", entries_text([A])), ("pointer", entries_text([A]))],
            with_=(A,), out="report2.json")
        for result in report["entries"]:
            self.assertEqual(result["level"], "N0")
            self.assertIn("collision", " ".join(result["notes"]))

    def test_configuration_error_is_refused_level(self):
        _, _, report, _ = self.run_tool(
            entries=[("function", entries_text([C]))], with_=(A, C),
            log=(PREFIX + f"Function 0x{C:08X}: cannot specify both 'size' and 'end'",))
        self.assertEqual(self.entry(report, C)["level"], "refused")

    def test_pointer_is_never_verified_in_the_data(self):
        _, _, report, _ = self.run_tool(entries=[("pointer", entries_text([A]))])
        result = self.entry(report, A)
        self.assertEqual(result["level"], "N1")
        self.assertIn("pointer not verified in the data (N3)", result["notes"])

    def test_failed_run_establishes_nothing_and_stops(self):
        log = (PREFIX + "=== ANALYSIS ERRORS ===",
               PREFIX + "UnresolvedCall (1):",
               PREFIX + f"  0x{D:08X} from 0x{A:08X}: bl 0x{D:08X} from 0x{A:08X} has a "
                        "target in no function",
               PREFIX + "Total: 1 errors",
               "Failed: Validation failed: 1 unresolved calls, 0 millicode errors")
        status, _, report, _ = self.run_tool(entries=[("function", entries_text([A]))],
                                             log=log)
        self.assertEqual(status, 1)
        self.assertEqual(self.entry(report, A)["level"], "N0")
        self.assertTrue(any("generation failed" in s for s in report["stops"]))
        self.assertEqual(report["errors"][0]["target"], f"0x{D:08X}")


class FormatTests(Folder):
    def assertRefused(self, status, out_path, stdout):
        self.assertEqual(status, 2)
        self.assertIn("REFUSED", stdout)
        self.assertFalse(os.path.exists(out_path))

    def test_absent_diagnostics_are_refused(self):
        # False positive 4: an empty log gives no ground for N1.
        status, stdout, _, out = self.run_tool(entries=[("function", entries_text([A]))],
                                               log=("",))
        self.assertRefused(status, out, stdout)
        self.assertIn("no diagnostic", stdout)

    def test_unknown_or_partial_mappings_are_refused(self):
        # False positive 5: format errors in the output.
        good = mappings_text([A, B])
        cases = {
            "no list": good.replace("kPPCFuncMappings", "kOtherList"),
            "unknown line": good.replace(f"\t{{ 0x{B:X}, sub_{B:08X} }},",
                                         f"\t{{ 0x{B:x}, sub_{B:08X} }}, // lower case"),
            "no terminator": good.replace("\t{ 0, nullptr }\n", ""),
            "no closing": good.replace("\n};", "\n"),
            "listed twice": good.replace(f"\t{{ 0x{B:X}, sub_{B:08X} }},",
                                         f"\t{{ 0x{A:X}, other }},"),
        }
        for label, text in cases.items():
            with self.subTest(label):
                path = self.file("init.cpp", text)
                with self.assertRaises(ac.Refused):
                    ac.parse_mappings(path)

    def test_diagnostic_in_an_unknown_format_is_refused(self):
        status, stdout, _, out = self.run_tool(
            entries=[("function", entries_text([A]))],
            log=(PREFIX + f"functions 0x{A:08X} has a new kind of problem",))
        self.assertRefused(status, out, stdout)
        self.assertIn("unknown format", stdout)

    def test_partial_failed_log_is_refused(self):
        error = (PREFIX + f"  0x{D:08X} from 0x{A:08X}: bl 0x{D:08X} from 0x{A:08X} has a "
                          "target in no function")
        for log in ((error,),
                    (error, "Failed: Validation failed: 2 unresolved calls, 0 millicode errors")):
            with self.subTest(len(log)):
                for name in os.listdir(self.private):
                    os.remove(os.path.join(self.private, name))
                status, stdout, _, out = self.run_tool(entries=[("function", entries_text([A]))],
                                                       log=log)
                self.assertRefused(status, out, stdout)
                self.assertIn("partial log", stdout)

    def test_a_completed_log_must_be_whole(self):
        """B2 (docs/J2_B2_COMPATIBILITY.md section 6): after an exit status 0, a log with no
        `Codegen summary` line, cut in its last line, or with a failure summary is refused,
        even if it holds no error. Without `completed`, nothing changes."""
        info = "[2026-01-01 00:00:00.000] [rexglue] [info] "
        summary = (info + "Codegen summary: 12 written, 0 unchanged, 0 deleted, "
                   "0 module(s) up to date")
        failed = "Failed: Validation failed: 0 unresolved calls, 0 millicode errors"
        whole = info + "Recompiling wc2010\n" + summary + "\n"
        path = self.file("whole.log", whole)
        self.assertEqual(ac.parse_log(path, completed=True), ({}, [], False))
        self.assertEqual(ac.codegen_summary(whole), (12, 0, 0, 0))
        for label, text in (("no summary", info + "Recompiling wc2010\n"),
                            ("cut last line", whole.rstrip("\n")),
                            ("two summaries", whole + summary + "\n"),
                            ("failure summary", whole + failed + "\n"),
                            ("empty", "")):
            with self.subTest(label):
                path = self.file("cut.log", text)
                with self.assertRaises(ac.Refused):
                    ac.parse_log(path, completed=True)
        path = self.file("cut.log", info + "Recompiling wc2010\n")
        self.assertEqual(ac.parse_log(path), ({}, [], False))

    def test_bad_entries_are_refused(self):
        for text in ("[functions]\n82010000x = {}\n", "[functions]\n0x8C010002 = {}\n",
                     "[functions]\n0x8C010000 = 1\n", "setjmp_address = 0x8C010002\n"):
            with self.subTest(text):
                path = self.file("bad.toml", text)
                with self.assertRaises(ac.Refused):
                    ac.parse_entries(path, "function")

    def test_bad_claims_are_refused(self):
        for text in ('[[claim]]\nname = "x"\nkind = "code"\naddress = 0x8C010000\n',
                     '[[claim]]\nname = "x"\nkind = "hook"\naddress = 0x8C010000\nwho = 1\n',
                     '[other]\n'):
            with self.subTest(text):
                path = self.file("claims.toml", text)
                with self.assertRaises(ac.Refused):
                    ac.parse_claims(path)


class ClaimTests(Folder):
    def claim(self, **values):
        lines = ["[[claim]]"]
        for key, value in values.items():
            if isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            elif isinstance(value, int):
                lines.append(f"{key} = 0x{value:X}" if value >= 0 else f"{key} = {value}")
            else:
                lines.append(f"{key} = {json.dumps(value)}")
        return "\n".join(lines) + "\n"

    def test_crt_without_examination_stops(self):
        status, stdout, report, _ = self.run_tool(
            entries=[("function", entries_text([], f"setjmp_address = 0x{A:08X}\n"))])
        self.assertEqual(status, 1)
        self.assertTrue(any("setjmp_address below N2" in s for s in report["stops"]))
        self.assertIn("STOP:", stdout)

    def test_crt_examined_reaches_n2(self):
        claims = self.claim(name="setjmp", kind="crt", address=A, examined=True,
                            expected="form of find_setjmp", observed="form of find_setjmp")
        status, _, report, _ = self.run_tool(
            entries=[("function", entries_text([], f"setjmp_address = 0x{A:08X}\n"))],
            claims=claims)
        self.assertEqual(status, 0, report["stops"])
        crt = next(e for e in report["entries"] if e["kind"] == "crt")
        self.assertEqual(crt["level"], "N2")

    def test_absent_or_inconsistent_reference_stays_below_n2(self):
        cases = {
            "not examined": dict(examined=False),
            "function unknown": dict(examined=True, address=C, expected="s", observed="s"),
            "sequence differs": dict(examined=True, expected="s", observed="t"),
        }
        for label, values in cases.items():
            with self.subTest(label):
                for name in os.listdir(self.private):
                    os.remove(os.path.join(self.private, name))
                fields = dict(name="boot_hook", kind="hook", address=A, boot_critical=True)
                fields.update(values)
                status, _, report, _ = self.run_tool(claims=self.claim(**fields))
                self.assertEqual(status, 1)
                self.assertEqual(report["claims"][0]["level"], "N0")
                self.assertTrue(any(s.startswith("claim #0 (hook)") for s in report["stops"]))
                self.assertEqual(report["claims"][0]["name"], "boot_hook")

    def test_invalid_data_offset_stays_unverified(self):
        # False positive 2: a data offset that is no valid displacement.
        claims = self.claim(name="slot", kind="data", address=D, offset=0x10000,
                            referenced_by=A, examined=True, boot_critical=True,
                            expected="lwz r11,offset(r10)", observed="lwz r11,offset(r10)")
        status, _, report, _ = self.run_tool(claims=claims)
        self.assertEqual(status, 1)
        self.assertEqual(report["claims"][0]["level"], "N0")
        self.assertIn("invalid data offset", " ".join(report["claims"][0]["notes"]))

    def test_data_value_is_never_verified(self):
        claims = self.claim(name="register", kind="data", address=D, offset=0x64,
                            referenced_by=A, examined=True,
                            expected="lis r10,0x8C01 / lwz r11,0x64(r10)",
                            observed="lis r10,0x8C01 / lwz r11,0x64(r10)")
        status, _, report, _ = self.run_tool(claims=claims)
        self.assertEqual(status, 0)
        self.assertEqual(report["claims"][0]["level"], "N2")
        self.assertIn("data value not verified (N3)", report["claims"][0]["notes"])


class OutputTests(Folder):
    def test_report_never_claims_a_full_validation(self):
        _, stdout, report, _ = self.run_tool(entries=[("function", entries_text([A]))])
        self.assertIn("not a validation of all addresses", report["method"])
        self.assertIn("not a validation of all addresses", stdout)

    def test_standard_output_is_aggregated(self):
        _, stdout, _, _ = self.run_tool(entries=[("function", entries_text([A, C]))],
                                        with_=(A,))
        self.assertNotIn("0x", stdout)
        self.assertIn("function: refused 0, N0 1, N1 1, N2 0", stdout)

    def test_paths_outside_the_private_folder_are_refused(self):
        outside = os.path.join(self.top, "outside.json")
        status, stdout, _, _ = self.run_tool(entries=[("function", entries_text([A]))],
                                             out=outside)
        self.assertEqual(status, 2)
        self.assertFalse(os.path.exists(outside))
        status, stdout, _, _ = self.run_tool(entries=[("function", entries_text([A]))],
                                             out="relative.json",
                                             extra_args=["--out", "relative.json"])
        self.assertEqual(status, 2)
        other = os.path.join(self.top, "input.toml")
        with open(other, "w", encoding="utf-8") as handle:
            handle.write(entries_text([A]))
        argv = ["--private-dir", self.private, "--entries", f"function={other}",
                "--mappings-with", self.file("w.cpp", mappings_text([A])),
                "--log", self.file("l.log", "ok\n"),
                "--out", os.path.join(self.private, "r.json")]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ac.main(argv), 2)
        self.assertFalse(os.path.exists(os.path.join(self.private, "r.json")))

    def test_report_is_never_overwritten_nor_written_through_a_link(self):
        existing = self.file("report.json", "kept\n")
        status, _, _, _ = self.run_tool(entries=[("function", entries_text([A]))])
        self.assertEqual(status, 2)
        with open(existing, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "kept\n")
        os.remove(existing)
        target = os.path.join(self.top, "elsewhere.json")
        os.symlink(target, existing)
        status, _, _, _ = self.run_tool(entries=[("function", entries_text([A]))])
        self.assertEqual(status, 2)
        self.assertFalse(os.path.exists(target))


class ReviewTests(Folder):
    """Review comment 7127281995 on PR #24: P-43 to P-46."""

    def test_paths_are_checked_before_any_file_is_read(self):
        # P-43: an entries file outside the private folder is never opened.
        outside = os.path.join(self.top, "outside.toml")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write(entries_text([A]))
        read = []
        real = ac.read_text
        ac.read_text = lambda path: (read.append(path), real(path))[1]
        self.addCleanup(setattr, ac, "read_text", real)
        argv = ["--private-dir", self.private, "--entries", f"function={outside}",
                "--mappings-with", self.file("w.cpp", mappings_text([A])),
                "--log", self.file("l.log", "ok\n"),
                "--out", os.path.join(self.private, "r.json")]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ac.main(argv), 2)
        self.assertEqual(read, [])
        self.assertFalse(os.path.exists(os.path.join(self.private, "r.json")))

    def test_refusals_print_no_address(self):
        # P-44: the offending line holds an address; the standard output does not.
        bad = mappings_text([A]).replace(f"\t{{ 0x{A:X}, sub_{A:08X} }},",
                                         f"\t{{ 0x{A:x}, sub_{A:08X} }},")
        argv = ["--private-dir", self.private,
                "--entries", f"function={self.file('e.toml', entries_text([A]))}",
                "--mappings-with", self.file("w.cpp", bad),
                "--log", self.file("l.log", "ok\n"),
                "--out", os.path.join(self.private, "r.json")]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(ac.main(argv), 2)
        self.assertNotIn("8C010000", stdout.getvalue().upper())
        for text in ("[functions]\n0x8C010002 = {}\n", "[functions]\n0x8C010000 = 1\n"):
            with self.subTest(text):
                stdout = io.StringIO()
                argv[3] = f"function={self.file('e.toml', text)}"
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(ac.main(argv), 2)
                self.assertNotIn("8C01000", stdout.getvalue().upper())

    def test_stop_lines_print_no_address(self):
        # P-44: a claim name may hold an address; STOP lines name the claim by its index.
        claims = ('[[claim]]\nname = "hook_0x8C010000"\nkind = "hook"\naddress = 0x8C010000\n'
                  'boot_critical = true\n')
        status, stdout, report, _ = self.run_tool(claims=claims)
        self.assertEqual(status, 1)
        self.assertIn("STOP: claim #0 (hook) below N2", stdout)
        self.assertNotIn("8C010000", stdout.upper())
        self.assertEqual(report["claims"][0]["name"], "hook_0x8C010000")
        self.assertEqual(ac.redact("at 0x8C010000 and 8C010040, ok"), "at <address> and "
                         "<address>, ok")

    def test_badly_typed_claims_are_refused_and_cannot_lift_a_stop(self):
        # P-45: "false" is a string, 42 is no instruction sequence, true is no address.
        base = ('[[claim]]\nname = "setjmp"\nkind = "crt"\naddress = 0x8C010000\n')
        cases = {
            "examined string": base + 'examined = "false"\nexpected = "a"\nobserved = "a"\n',
            "examined integer": base + 'examined = 1\nexpected = "a"\nobserved = "a"\n',
            "sequences integers": base + 'examined = true\nexpected = 42\nobserved = 42\n',
            "sequence empty": base + 'examined = true\nexpected = " "\nobserved = " "\n',
            "sequence missing": base + 'examined = true\n',
            "address boolean": ('[[claim]]\nname = "s"\nkind = "crt"\naddress = true\n'),
            "boot_critical string": base + 'boot_critical = "yes"\n',
            "offset boolean": ('[[claim]]\nname = "d"\nkind = "data"\naddress = 0x8C010000\n'
                               'offset = true\n'),
        }
        entries = entries_text([], f"setjmp_address = 0x{A:08X}\n")
        for label, claims in cases.items():
            with self.subTest(label):
                for name in os.listdir(self.private):
                    os.remove(os.path.join(self.private, name))
                status, stdout, report, out = self.run_tool(entries=[("function", entries)],
                                                            claims=claims)
                self.assertEqual(status, 2, stdout)
                self.assertIsNone(report)
                self.assertFalse(os.path.exists(out))

    def test_setjmp_entry_must_be_an_integer(self):
        path = self.file("bad.toml", "setjmp_address = true\n")
        with self.assertRaises(ac.Refused):
            ac.parse_entries(path, "function")

    def test_report_parent_swapped_for_a_link_is_refused(self):
        # P-46: between the checks and the creation, the report folder becomes a link to a
        # folder outside the private one. The anchored creation refuses to follow it.
        reports = os.path.join(self.private, "reports")
        os.mkdir(reports, 0o700)
        outside = os.path.join(self.top, "outside")
        os.mkdir(outside)

        def swap():
            os.rename(reports, reports + ".old")
            os.symlink(outside, reports)

        ac.BEFORE_REPORT_OPEN_FOR_TESTING = swap
        self.addCleanup(setattr, ac, "BEFORE_REPORT_OPEN_FOR_TESTING", None)
        status, stdout, _, _ = self.run_tool(entries=[("function", entries_text([A]))],
                                             out=os.path.join(reports, "report.json"))
        self.assertEqual(status, 2, stdout)
        self.assertEqual(os.listdir(outside), [])
        self.assertEqual(os.listdir(reports + ".old"), [])

    def test_report_in_a_subfolder_is_written(self):
        reports = os.path.join(self.private, "reports")
        os.mkdir(reports, 0o700)
        status, _, report, out = self.run_tool(entries=[("function", entries_text([A]))],
                                               out=os.path.join(reports, "report.json"))
        self.assertEqual(status, 0)
        self.assertIsNotNone(report)
        self.assertEqual(os.stat(out).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)

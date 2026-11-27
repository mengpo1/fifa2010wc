#!/usr/bin/env python3
"""Tests of tools/private_project.py (J2 step A5), on synthetic private folders only.

No XEX, no game file and no ReXGlue command: the folders hold empty subfolders and the
manifests the tests write. The ReXGlue parser itself is exercised by the Nix check
private-project-selftest, on a synthetic folder without any XEX.
"""

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("private_project",
                                              os.path.join(HERE, "private_project.py"))
pp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pp)

TEMPLATE = pp.DEFAULT_TEMPLATE
GUARD = pp.DEFAULT_GUARD
SUBFOLDERS = ("iso", "game", "xex", "generated", "cache", "saves", "logs")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class Folder(unittest.TestCase):
    """A synthetic private folder, mode 0700, with the subfolders of CP-1."""

    def setUp(self):
        self.top = tempfile.mkdtemp(prefix="pp-test-")
        self.private = os.path.join(self.top, "private")
        os.mkdir(self.private, 0o700)
        os.chmod(self.private, 0o700)
        for name in SUBFOLDERS:
            os.mkdir(os.path.join(self.private, name), 0o700)
        self.template_text = read(TEMPLATE)

    def tearDown(self):
        shutil.rmtree(self.top, ignore_errors=True)

    def manifest_path(self):
        return os.path.join(self.private, pp.PROJECT_DIR, pp.MANIFEST_NAME)

    def write_manifest(self, text):
        os.makedirs(os.path.join(self.private, pp.PROJECT_DIR), mode=0o700, exist_ok=True)
        write(self.manifest_path(), text)

    def write_template(self, text):
        path = os.path.join(self.top, "template.toml")
        write(path, text)
        return path

    def check(self, text):
        self.write_manifest(text)
        findings, _ = pp.check_manifest(self.manifest_path(), self.private)
        return findings

    def assertFound(self, findings, fragment):
        self.assertTrue(any(fragment in finding for finding in findings),
                        f"no finding with {fragment!r} in {findings}")


class TemplateTests(Folder):
    def test_repository_template_passes(self):
        self.assertEqual(pp.check_template(TEMPLATE), [])

    def test_template_pins_the_sdk_version(self):
        self.assertIn('sdk_version = "0.11.0"', self.template_text)
        other = self.write_template(self.template_text.replace('"0.11.0"', '"0.10.0"'))
        self.assertFound(pp.check_template(other), "pinned SDK")

    def test_template_with_an_address_is_refused(self):
        cases = {
            "function_table_base": self.template_text.replace(
                'out_directory_path = "../generated/default"\n',
                'out_directory_path = "../generated/default"\nfunction_table_base = 0x8C000000\n'),
            "setjmp_address": self.template_text.replace(
                'out_directory_path = "../generated/fifadllzf"\n',
                'out_directory_path = "../generated/fifadllzf"\nsetjmp_address = 0x8C000000\n'),
            "[functions]": self.template_text + "\n[functions]\n0x8C000000 = {}\n",
            "[project].extra": self.template_text.replace(
                'name = "wc2010"\n', 'name = "wc2010"\nextra = 1\n'),
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.assertNotEqual(pp.check_template(self.write_template(text)), [])

    def test_template_with_an_absolute_or_foreign_path_is_refused(self):
        for value in ("/home/someone/game/default.xex", "~/game/default.xex",
                      "C:/game/default.xex", "..\\game\\default.xex"):
            with self.subTest(value):
                text = self.template_text.replace('file_path = "../game/default.xex"',
                                                  f'file_path = "{value}"'.replace("\\", "\\\\"))
                self.assertFound(pp.check_template(self.write_template(text)),
                                 "not a relative POSIX path")

    def test_template_paths_that_leave_the_private_root_are_refused_before_install(self):
        # P-41: the template is checked as installed in <private folder>/project/.
        cases = {
            "file_path": ('file_path = "../game/default.xex"',
                          'file_path = "../../game/default.xex"'),
            "out_directory_path": ('out_directory_path = "../generated/default"',
                                   'out_directory_path = "../../generated/default"'),
            "game_root": ('game_root = "../game"', 'game_root = "../.."'),
            "hook_sources": ('name = "wc2010"\n', 'name = "wc2010"\nhook_sources = ["../../h"]\n'),
            "includes": ('out_directory_path = "../generated/default"\nincludes = []',
                         'out_directory_path = "../generated/default"\nincludes = ["../../x.toml"]'),
        }
        for label, (old, new) in cases.items():
            with self.subTest(label):
                self.assertIn(old, self.template_text)
                findings = pp.check_template(self.write_template(self.template_text.replace(old, new)))
                self.assertFound(findings, "outside the private folder")

    def test_template_paths_leave_the_project_folder(self):
        text = self.template_text.replace('out_directory_path = "../generated/default"',
                                          'out_directory_path = "generated/default"')
        self.assertFound(pp.check_template(self.write_template(text)), "must point out of")

    def test_module_guest_path_matches_the_runtime_device_path(self):
        # A2 §3.1: the runtime joins the bare name to the device folder of default.xex.
        runtime = r"\Device\Harddisk0\Partition1" + "\\" + "fifadllzf.xex"
        self.assertIn(r'guest_path = "\\Device\\Harddisk0\\Partition1\\fifadllzf.xex"',
                      self.template_text)
        configured = "\\Device\\Harddisk0\\Partition1\\fifadllzf.xex"
        self.assertEqual(pp.normalize_guest_path(configured),
                         "device/harddisk0/partition1/fifadllzf.xex")
        self.assertEqual(pp.normalize_guest_path(configured), pp.normalize_guest_path(runtime))
        self.assertEqual(pp.normalize_guest_path("game:\\fifadllzf.xex"), "fifadllzf.xex")


class InitTests(Folder):
    def run_init(self, template=TEMPLATE, repo=None):
        return pp.init(self.private, template, GUARD, repo=repo)

    def test_init_writes_the_template_and_the_output_folders(self):
        findings, notes = self.run_init()
        self.assertEqual(findings, [])
        self.assertEqual(read(self.manifest_path()), self.template_text)
        self.assertEqual(os.stat(self.manifest_path()).st_mode & 0o777, 0o600)
        for name in ("default", "fifadllzf"):
            out = os.path.join(self.private, "generated", name)
            self.assertTrue(os.path.isdir(out))
            self.assertEqual(os.stat(out).st_mode & 0o777, 0o700)
        findings, resolved = pp.check_manifest(self.manifest_path(), self.private)
        self.assertEqual(findings, [])
        real = os.path.realpath(self.private)
        self.assertEqual(resolved["[project].game_root"], os.path.join(real, "game"))
        self.assertEqual(resolved["[entrypoint].file_path"],
                         os.path.join(real, "game", "default.xex"))
        self.assertEqual(resolved["[[modules]] #0.file_path"],
                         os.path.join(real, "game", "fifadllzf.xex"))
        self.assertEqual(resolved["[entrypoint].out_directory_path"],
                         os.path.join(real, "generated", "default"))
        self.assertTrue(any("wrote" in note for note in notes))

    def test_init_refuses_a_folder_that_fails_cp1_and_writes_nothing(self):
        os.chmod(self.private, 0o755)
        findings, _ = self.run_init()
        self.assertFound(findings, "CP-1")
        self.assertFound(findings, "nothing was written")
        self.assertFalse(os.path.exists(os.path.join(self.private, pp.PROJECT_DIR)))
        self.assertEqual(os.listdir(os.path.join(self.private, "generated")), [])

    def test_init_refuses_a_private_folder_inside_the_repository(self):
        findings, _ = self.run_init(repo=self.top)
        self.assertFound(findings, "overlap")
        self.assertFalse(os.path.exists(os.path.join(self.private, pp.PROJECT_DIR)))

    def test_init_never_overwrites_a_manifest(self):
        changed = self.template_text + "\n# phase B entries\n"
        self.write_manifest(changed)
        findings, notes = self.run_init()
        self.assertEqual(findings, [])
        self.assertEqual(read(self.manifest_path()), changed)
        self.assertTrue(any("left as it is" in note for note in notes))

    def outside(self):
        folder = os.path.join(self.top, "outside")
        os.mkdir(folder)
        return folder

    def assertNothingWritten(self, outside):
        self.assertEqual(os.listdir(outside), [])
        self.assertFalse(os.path.lexists(os.path.join(self.private, "generated", "default")))
        self.assertFalse(os.path.lexists(os.path.join(self.private, "generated", "fifadllzf")))

    def test_init_refuses_a_project_link_and_writes_nothing_outside(self):
        # P-40: project/ is a link to a folder outside the private folder.
        outside = self.outside()
        os.symlink(outside, os.path.join(self.private, pp.PROJECT_DIR))
        findings, _ = self.run_init()
        self.assertFound(findings, "symbolic link")
        self.assertFound(findings, "nothing was written")
        self.assertNothingWritten(outside)

    def test_init_refuses_a_generated_link_and_writes_nothing_outside(self):
        # CP-1 follows the link (generated/ is a folder for os.path.isdir); init does not.
        outside = self.outside()
        os.rmdir(os.path.join(self.private, "generated"))
        os.symlink(outside, os.path.join(self.private, "generated"))
        findings, _ = self.run_init()
        self.assertFound(findings, "symbolic link")
        self.assertEqual(os.listdir(outside), [])
        self.assertFalse(os.path.lexists(os.path.join(self.private, pp.PROJECT_DIR)))

    def test_init_refuses_an_output_folder_link_before_any_write(self):
        outside = self.outside()
        os.symlink(outside, os.path.join(self.private, "generated", "fifadllzf"))
        findings, _ = self.run_init()
        self.assertFound(findings, "symbolic link")
        self.assertEqual(os.listdir(outside), [])
        self.assertFalse(os.path.lexists(os.path.join(self.private, pp.PROJECT_DIR)))
        self.assertFalse(os.path.lexists(os.path.join(self.private, "generated", "default")))

    def test_init_refuses_a_manifest_link(self):
        outside = self.outside()
        os.mkdir(os.path.join(self.private, pp.PROJECT_DIR), 0o700)
        target = os.path.join(outside, "manifest.toml")
        os.symlink(target, self.manifest_path())
        findings, _ = self.run_init()
        self.assertFound(findings, "symbolic link")
        self.assertEqual(os.listdir(outside), [])

    def test_init_stops_on_a_link_put_in_place_during_init(self):
        # A link swapped in between the checks and the writes: the anchored writes refuse to
        # follow it, so nothing lands outside the private folder.
        outside = self.outside()

        def swap():
            os.symlink(outside, os.path.join(self.private, pp.PROJECT_DIR))

        findings, _ = pp.init(self.private, TEMPLATE, GUARD, before_writes=swap)
        self.assertFound(findings, "changed during init")
        self.assertEqual(os.listdir(outside), [])
        self.assertNothingWritten(outside)

    def test_init_stops_on_an_output_link_put_in_place_during_init(self):
        outside = self.outside()

        def swap():
            os.symlink(outside, os.path.join(self.private, "generated", "default"))

        findings, notes = pp.init(self.private, TEMPLATE, GUARD, before_writes=swap)
        self.assertFound(findings, "changed during init")
        self.assertEqual(os.listdir(outside), [])
        # The manifest, written before, is inside the private folder.
        self.assertTrue(os.path.isfile(self.manifest_path()))
        self.assertFalse(os.path.islink(self.manifest_path()))

    def swap_template_after_read(self, first, second):
        """The template file holds `first`; right after init reads it, it is replaced with
        `second`. Returns the path and restores load_template on cleanup."""
        path = self.write_template(first)
        real = pp.load_template
        reads = []

        def load_then_swap(template):
            result = real(template)
            reads.append(template)
            write(template, second)
            return result

        pp.load_template = load_then_swap
        self.addCleanup(setattr, pp, "load_template", real)
        return path, reads

    def test_init_refuses_a_template_replaced_by_a_clean_one_after_reading(self):
        # P-42: the bytes read hold an address (CP-7), the file is then made clean. init
        # checks the bytes it read, the ones it would copy, and refuses before writing.
        forbidden = self.template_text.replace(
            'out_directory_path = "../generated/default"\n',
            'out_directory_path = "../generated/default"\nfunction_table_base = 0x8C000000\n')
        path, reads = self.swap_template_after_read(forbidden, self.template_text)
        findings, _ = self.run_init(template=path)
        self.assertEqual(len(reads), 1)
        self.assertFound(findings, "function_table_base")
        self.assertFound(findings, "nothing was written")
        self.assertFalse(os.path.exists(os.path.join(self.private, pp.PROJECT_DIR)))

    def test_init_copies_only_the_content_it_checked(self):
        # The bytes read are clean, the file then gets an address: the copy holds the clean,
        # checked bytes, never the later content.
        forbidden = self.template_text + "\n[functions]\n0x8C000000 = {}\n"
        path, reads = self.swap_template_after_read(self.template_text, forbidden)
        findings, _ = self.run_init(template=path)
        self.assertEqual(findings, [])
        self.assertEqual(len(reads), 1)
        self.assertEqual(read(self.manifest_path()), self.template_text)
        self.assertNotIn("[functions]", read(self.manifest_path()))

    def test_init_with_a_bad_template_writes_nothing(self):
        bad = self.write_template(self.template_text.replace(
            'file_path = "../game/default.xex"', 'file_path = "/srv/default.xex"'))
        findings, _ = self.run_init(template=bad)
        self.assertFound(findings, "template:")
        self.assertFalse(os.path.exists(self.manifest_path()))


class CheckTests(Folder):
    def test_template_copy_passes(self):
        self.assertEqual(self.check(self.template_text), [])

    def test_path_out_of_the_private_folder_is_refused(self):
        text = self.template_text.replace('file_path = "../game/default.xex"',
                                          'file_path = "../../elsewhere/default.xex"')
        self.assertFound(self.check(text), "outside the private folder")

    def test_xex_outside_game_root_is_refused(self):
        text = self.template_text.replace('file_path = "../game/default.xex"',
                                          'file_path = "../xex/default.xex"')
        self.assertFound(self.check(text), "not under game_root")

    def test_output_folder_must_be_a_folder_inside_generated(self):
        for value in ("../cache/default", "../generated", "../game/out"):
            with self.subTest(value):
                text = self.template_text.replace('out_directory_path = "../generated/default"',
                                                  f'out_directory_path = "{value}"')
                self.assertFound(self.check(text), "inside generated/")

    def test_shared_or_nested_output_folders_are_refused(self):
        for value in ("../generated/default", "../generated/default/dll"):
            with self.subTest(value):
                text = self.template_text.replace(
                    'out_directory_path = "../generated/fifadllzf"',
                    f'out_directory_path = "{value}"')
                self.assertFound(self.check(text), "share an output folder")

    def test_link_out_of_the_private_folder_is_refused(self):
        outside = os.path.join(self.top, "outside")
        os.mkdir(outside)
        os.rmdir(os.path.join(self.private, "game"))
        os.symlink(outside, os.path.join(self.private, "game"))
        self.assertFound(self.check(self.template_text), "outside the private folder")

    def test_phase_b_addresses_are_accepted_in_the_private_copy(self):
        text = self.template_text.replace(
            'out_directory_path = "../generated/default"\n',
            'out_directory_path = "../generated/default"\nfunction_table_base = 0x8C000000\n')
        text += "\n[functions]\n0x8C000000 = {}\n"
        self.assertEqual(self.check(text), [])
        self.assertNotEqual(pp.check_template(self.write_template(text)), [])

    def test_duplicate_guest_path_is_refused(self):
        module = self.template_text[self.template_text.index("[[modules]]"):]
        second = module.replace("fifadllzf.xex\"", "FIFADLLZF.XEX\"", 1).replace(
            "../generated/fifadllzf", "../generated/second").replace(
            'file_path = "../game/FIFADLLZF.XEX"', 'file_path = "../game/fifadllzf.xex"')
        self.assertFound(self.check(self.template_text + "\n" + second), "used twice")

    def test_missing_game_root_or_bad_name_is_refused(self):
        self.assertFound(self.check(self.template_text.replace('game_root = "../game"\n', "")),
                         "game_root is missing")
        self.assertFound(self.check(self.template_text.replace('name = "wc2010"',
                                                               'name = "2010-wc"')),
                         "identifier")

    def test_check_refuses_a_project_or_manifest_link(self):
        outside = os.path.join(self.top, "outside")
        os.mkdir(outside)
        write(os.path.join(outside, pp.MANIFEST_NAME), self.template_text)
        os.symlink(outside, os.path.join(self.private, pp.PROJECT_DIR))
        findings, _ = pp.check_manifest(self.manifest_path(), self.private)
        self.assertFound(findings, "symbolic link")
        os.remove(os.path.join(self.private, pp.PROJECT_DIR))
        os.mkdir(os.path.join(self.private, pp.PROJECT_DIR), 0o700)
        os.symlink(os.path.join(outside, pp.MANIFEST_NAME), self.manifest_path())
        findings, _ = pp.check_manifest(self.manifest_path(), self.private)
        self.assertFound(findings, "symbolic link")

    def test_invalid_toml_is_reported(self):
        self.assertFound(self.check("[project\nname = 1\n"), "not valid TOML")


# A synthetic clone of "project A" for stage-config (option C-a, D-021): the layout of the
# audited commit (pc/fifawc10_manifest.toml, pc/config/), made-up addresses, no game data.
PROJECT_A_FILES = {
    "pc/fifawc10_manifest.toml": (
        '[project]\nname = "fifawc10"\nsdk_version = "0.10.0"\ngame_root = "../out/game-files"\n'
        '\n[entrypoint]\nfile_path = "../out/game-files/default.xex"\n'
        'out_directory_path = "generated/default"\n'
        'includes = ["config/codegen_options.toml", "config/default.toml", '
        '"config/default_pointers.toml"]\n'
        '\n[[modules]]\nguest_path = "fifadllzf.xex"\n'
        'file_path = "../out/game-files/fifadllzf.xex"\n'
        'out_directory_path = "generated/fifadllzf"\n'
        'includes = ["config/codegen_options.toml", "config/fifadllzf.toml", '
        '"config/fifadllzf_pointers.toml"]\n'),
    "pc/config/codegen_options.toml": "generate_exception_handlers = true\n",
    # As at the audited commit, default.toml sets function_table_base (here a made-up value):
    # the derogation G-3 removes that line, and only it, from the test copy.
    "pc/config/default.toml": ("# Synthetic overrides for default.xex.\n"
                               "function_table_base = 0x8C100000\n\n"
                               "[functions]\n0x8C010000 = {}\n"),
    "pc/config/default_pointers.toml": 'includes = ["more/extra.toml"]\n',
    "pc/config/more/extra.toml": "[functions]\n0x8C010040 = {}\n",
    "pc/config/fifadllzf.toml": "setjmp_address = 0x8C020000\nlongjmp_address = 0x8C020040\n",
    "pc/config/fifadllzf_pointers.toml": "[functions]\n0x8C020080 = {}\n",
    "pc/fixes/boot_fixes.cpp": "// synthetic fix, never staged\n",
}


class StageConfigTests(Folder):
    def setUp(self):
        super().setUp()
        findings, _ = pp.init(self.private, TEMPLATE, GUARD)
        self.assertEqual(findings, [])

    def project_a(self, changes=None, links=()):
        source = os.path.join(self.top, "project-a")
        shutil.rmtree(source, ignore_errors=True)
        files = dict(PROJECT_A_FILES, **(changes or {}))
        for rel, text in files.items():
            if text is None:
                continue
            os.makedirs(os.path.dirname(os.path.join(source, rel)), exist_ok=True)
            write(os.path.join(source, rel), text)
        for rel, target in links:
            path = os.path.join(source, rel)
            if os.path.exists(path):
                os.unlink(path)
            os.symlink(target, path)
        git = ["git", "-C", source, "-c", "user.name=test", "-c",
               "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", source], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "synthetic project A"], check=True)
        commit = subprocess.run(["git", "-C", source, "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True).stdout.strip()
        return source, commit

    def project_tree(self):
        found = {}
        for top, _, names in os.walk(os.path.join(self.private, pp.PROJECT_DIR)):
            for name in names:
                path = os.path.join(top, name)
                found[os.path.relpath(path, self.private)] = read(path)
        return found

    def test_stage_config_copies_the_pinned_files_and_names_them(self):
        source, commit = self.project_a()
        findings, notes = pp.stage_config(self.private, source, GUARD, commit=commit)
        self.assertEqual(findings, [])
        config = os.path.join(self.private, pp.PROJECT_DIR, pp.CONFIG_DIR)
        staged = sorted(os.path.relpath(os.path.join(top, n), config)
                        for top, _, names in os.walk(config) for n in names)
        self.assertEqual(staged, ["codegen_options.toml", "default.toml",
                                  "default_pointers.toml", "fifadllzf.toml",
                                  "fifadllzf_pointers.toml", "more/extra.toml",
                                  "original/default.toml"])
        for rel in staged:
            pinned = PROJECT_A_FILES["pc/config/" + rel.replace("original/", "")]
            expected = (pinned.replace("function_table_base = 0x8C100000\n", "")
                        if rel == "default.toml" else pinned)
            self.assertEqual(read(os.path.join(config, rel)), expected, rel)
            self.assertEqual(os.stat(os.path.join(config, rel)).st_mode & 0o777, 0o600)
        manifest = read(self.manifest_path())
        self.assertIn('includes = ["config/codegen_options.toml", "config/default.toml", '
                      '"config/default_pointers.toml"]', manifest)
        self.assertIn('includes = ["config/codegen_options.toml", "config/fifadllzf.toml", '
                      '"config/fifadllzf_pointers.toml"]', manifest)
        self.assertEqual(manifest.count("includes = []"), 0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.private, pp.PROJECT_DIR))),
                         [pp.CONFIG_DIR, pp.MANIFEST_NAME])
        self.assertEqual(pp.check_manifest(self.manifest_path(), self.private)[0], [])
        self.assertTrue(any(commit in note for note in notes))
        self.assertTrue(any("G-3: config/default.toml is the pinned file without its line 2"
                            in note for note in notes), notes)
        self.assertFalse(any("fixes" in note for note in notes))
        self.assertNotIn("original", manifest)

    def test_g3_removes_one_line_and_nothing_else(self):
        # G-3 (D-021), byte for byte: the copy is the original less one whole line; the
        # check refuses a copy with any other change, and accepts only that copy.
        original = PROJECT_A_FILES["pc/config/default.toml"].encode()
        copy, line, problems = pp.g3_derive(original)
        self.assertEqual(problems, [])
        self.assertEqual(line, 2)
        self.assertEqual(copy, original.replace(b"function_table_base = 0x8C100000\n", b""))
        self.assertEqual(pp.g3_check(original, copy), [])
        for label, staged in (("unchanged", original),
                              ("one more byte", copy + b"\n"),
                              ("another value", copy.replace(b"0x8C010000", b"0x8C010004")),
                              ("a line removed too", copy.replace(b"\n\n", b"\n", 1))):
            with self.subTest(label=label):
                self.assertTrue(pp.g3_check(original, staged))

    def test_g3_refuses_what_it_does_not_cover(self):
        # G-3 covers one top-level line of default.toml and nothing else; refused, with
        # nothing written: no such line, the key named twice, the key inside a table, a line
        # of another form, and the key in another staged file.
        line = "function_table_base = 0x8C100000\n"
        functions = "[functions]\n0x8C010000 = {}\n"
        cases = (
            ("line absent", {"pc/config/default.toml": functions}, "names no"),
            ("key named twice", {"pc/config/default.toml": line + "# function_table_base\n" +
                                 functions}, "2 times: ambiguous"),
            ("inside a table", {"pc/config/default.toml": functions + "[analysis]\n" + line},
             "changes more than"),
            ("another form", {"pc/config/default.toml":
                              "function_table_base = 0x8C100000 # moved\n" + functions},
             "not a plain"),
            ("a string value", {"pc/config/default.toml":
                                'function_table_base = "0x8C100000"\n' + functions},
             "not a plain"),
            ("another inherited value", {"pc/config/codegen_options.toml": line},
             "another inherited value"),
        )
        before = self.project_tree()
        for name, changes, fragment in cases:
            with self.subTest(name=name):
                source, commit = self.project_a(changes)
                findings, _ = pp.stage_config(self.private, source, GUARD, commit=commit)
                self.assertFound(findings, fragment)
                self.assertFound(findings, "nothing was written")
                self.assertEqual(self.project_tree(), before)

    def test_stage_config_refusals_write_nothing(self):
        cases = (
            ("short commit id", {}, (), lambda commit: commit[:7], "resolves to"),
            ("unknown commit", {}, (), lambda commit: "0" * 40, "not found"),
            ("a link in the commit", {}, (("pc/config/default.toml", "codegen_options.toml"),),
             None, "mode 120000"),
            ("an include outside pc/config/",
             {"pc/config/default_pointers.toml": 'includes = ["../fixes/boot.toml"]\n',
              "pc/fixes/boot.toml": "\n"}, (), None, "outside pc/config/"),
            ("a circular include",
             {"pc/config/default_pointers.toml": 'includes = ["default_pointers.toml"]\n'},
             (), None, "circular include"),
            ("a missing include", {"pc/config/more/extra.toml": None}, (), None,
             "is not in commit"),
            ("an include that is not a path",
             {"pc/config/default_pointers.toml": "includes = [1]\n"}, (), None,
             "not a list of relative paths"),
        )
        before = self.project_tree()
        for name, changes, links, pick, fragment in cases:
            with self.subTest(name=name):
                source, commit = self.project_a(changes, links)
                findings, _ = pp.stage_config(self.private, source, GUARD,
                                              commit=pick(commit) if pick else commit)
                self.assertFound(findings, fragment)
                self.assertFound(findings, "nothing was written")
                self.assertEqual(self.project_tree(), before)

    def test_stage_config_never_overwrites(self):
        source, commit = self.project_a()
        config = os.path.join(self.private, pp.PROJECT_DIR, pp.CONFIG_DIR)
        os.makedirs(os.path.join(config, "original"), 0o700)
        for rel in ("default.toml", "original/default.toml"):
            write(os.path.join(config, rel), "the owner's own file\n")
            before = self.project_tree()
            findings, _ = pp.stage_config(self.private, source, GUARD, commit=commit)
            self.assertFound(findings, f"{rel} exists: never overwritten")
            self.assertEqual(self.project_tree(), before)
            os.unlink(os.path.join(config, rel))
        self.assertEqual(pp.stage_config(self.private, source, GUARD, commit=commit)[0], [])
        # Staged once: a second run finds the includes set and the files there.
        before = self.project_tree()
        findings, _ = pp.stage_config(self.private, source, GUARD, commit=commit)
        self.assertFound(findings, "already set")
        self.assertEqual(self.project_tree(), before)

    def test_stage_config_needs_the_private_copy(self):
        os.unlink(self.manifest_path())
        source, commit = self.project_a()
        findings, _ = pp.stage_config(self.private, source, GUARD, commit=commit)
        self.assertFound(findings, "run init first")
        self.assertFalse(os.path.exists(os.path.join(self.private, pp.PROJECT_DIR,
                                                     pp.CONFIG_DIR)))

    def test_the_pinned_commit_is_the_audited_one(self):
        self.assertEqual(pp.PROJECT_A_COMMIT[:7], "498d18a")
        self.assertEqual(len(pp.PROJECT_A_COMMIT), 40)


class CommandLineTests(Folder):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = pp.main(list(argv))
        return status, out.getvalue()

    def test_command_line_exit_codes(self):
        self.assertEqual(self.run_main("template")[0], 0)
        self.assertEqual(self.run_main("--private-dir", "relative/path", "check")[0], 2)
        status, output = self.run_main("--private-dir", self.private, "--guard", GUARD, "init")
        self.assertEqual(status, 0, output)
        self.assertEqual(self.run_main("--private-dir", self.private, "check")[0], 0)
        write(self.manifest_path(), self.template_text.replace(
            'file_path = "../game/default.xex"', 'file_path = "../xex/default.xex"'))
        status, output = self.run_main("--private-dir", self.private, "check")
        self.assertEqual(status, 1)
        self.assertIn("FOUND:", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)

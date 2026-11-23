#!/usr/bin/env python3
"""Tests for private_guard.py (step A4 of docs/J2_PLAN.md).

Every folder is synthesized in a temporary folder at run time; no test reads, needs or
produces game data. Run with `python3 -I tools/test_private_guard.py`.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("private_guard",
                                              os.path.join(HERE, "private_guard.py"))
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

GIT = shutil.which("git")
SAFE = {"umask": 0o077, "euid": 1000, "core": 0}


def has(findings, text):
    return any(text in finding for finding in findings)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.private = os.path.join(self.root, "private")
        os.mkdir(self.private)
        os.chmod(self.private, 0o700)
        for name in guard.SUBFOLDERS:
            os.mkdir(os.path.join(self.private, name))
        self.home = os.path.join(self.root, "home")
        os.mkdir(self.home)
        self.shm = os.path.join(self.root, "shm")
        os.mkdir(self.shm)

    def tearDown(self):
        for root, dirs, files in os.walk(self.root):
            for name in dirs + files:
                try:
                    os.chmod(os.path.join(root, name), 0o700)
                except OSError:
                    pass
        self.tmp.cleanup()

    def env(self, **overrides):
        env = {name: os.path.join(self.private, "env", name.lower())
               for name in guard.REQUIRED_ENV}
        env.update(overrides)
        return {k: v for k, v in env.items() if v is not None}

    def check_dir(self, private=None, **kw):
        kw.setdefault("git", GIT or "git")
        kw.setdefault("home", self.home)
        return guard.check_dir(self.private if private is None else private, **kw)

    def preflight(self, **kw):
        if not kw.get("no_writes"):
            kw.setdefault("dests", [os.path.join(self.private, "generated")])
        kw.setdefault("cwd", self.private)
        kw.setdefault("env", self.env())
        kw.setdefault("settings", dict(SAFE))
        kw.setdefault("git", GIT or "git")
        kw.setdefault("shm_dir", self.shm)
        kw.setdefault("home", self.home)
        return guard.preflight(self.private, **kw)


@unittest.skipIf(GIT is None, "git is needed for the work tree check")
class CheckDirTest(Base):
    def test_valid_private_folder_passes(self):
        self.assertEqual(self.check_dir(), [])

    def test_unset_and_relative_paths_are_refused(self):
        self.assertTrue(has(guard.check_dir("", git=GIT), "not set"))
        self.assertTrue(has(guard.check_dir("private", git=GIT), "not an absolute path"))

    def test_missing_folder_is_refused(self):
        self.assertTrue(has(self.check_dir(os.path.join(self.root, "absent")),
                            "does not exist"))

    def test_open_mode_is_refused(self):
        os.chmod(self.private, 0o755)
        self.assertTrue(has(self.check_dir(), "mode 0755"))

    def test_another_owner_is_refused(self):
        self.assertTrue(has(self.check_dir(uid=os.geteuid() + 1), "another user"))

    def test_missing_subfolder_is_reported(self):
        os.rmdir(os.path.join(self.private, "logs"))
        self.assertTrue(has(self.check_dir(), "missing subfolder: logs/"))

    def test_writable_disc_image_is_reported(self):
        image = os.path.join(self.private, "iso", "image.iso")
        with open(image, "wb") as f:
            f.write(b"synthetic")
        os.chmod(image, 0o644)
        self.assertTrue(has(self.check_dir(), "writable file under iso/"))
        os.chmod(image, 0o444)
        self.assertEqual(self.check_dir(), [])

    def test_folder_inside_the_repository_is_refused(self):
        repo = os.path.join(self.root, "repo")
        os.mkdir(repo)
        subprocess.run([GIT, "init", "-q", repo], check=True)
        private = os.path.join(repo, "private")
        os.mkdir(private)
        os.chmod(private, 0o700)
        findings = guard.check_dir(private, repo=repo, git=GIT, home=self.home)
        self.assertTrue(has(findings, "overlap"))
        self.assertTrue(has(findings, "inside a git work tree"))

    def test_git_work_tree_is_detected_without_the_repo_option(self):
        subprocess.run([GIT, "init", "-q", self.root], check=True)
        self.assertTrue(has(self.check_dir(), "inside a git work tree"))

    def test_missing_git_fails_closed(self):
        findings = self.check_dir(git=os.path.join(self.root, "no-such-git"))
        self.assertTrue(has(findings, "cannot run"))

    def test_home_folder_itself_is_refused(self):
        os.chmod(self.home, 0o700)
        for name in guard.SUBFOLDERS:
            os.mkdir(os.path.join(self.home, name))
        self.assertTrue(has(guard.check_dir(self.home, git=GIT, home=self.home),
                            "dedicated folder"))

    def test_store_path_is_refused(self):
        store_dir = os.path.dirname(os.path.realpath(sys.executable))
        if not store_dir.startswith(guard.STORE + "/"):
            self.skipTest("the Python interpreter is not in /nix/store")
        self.assertTrue(has(guard.check_dir(store_dir, git=GIT, home=self.home),
                            "/nix/store"))


@unittest.skipIf(GIT is None, "git is needed for the work tree check")
class PreflightTest(Base):
    def test_safe_setup_passes(self):
        self.assertEqual(self.preflight(dests=[os.path.join(self.private, "generated")]), [])

    def test_destination_outside_is_refused(self):
        findings = self.preflight(dests=[os.path.join(self.root, "out")])
        self.assertTrue(has(findings, "write destination outside"))

    def test_destination_through_a_symlink_is_resolved(self):
        link = os.path.join(self.private, "generated", "link")
        os.symlink(self.root, link)
        findings = self.preflight(dests=[os.path.join(link, "out")])
        self.assertTrue(has(findings, "write destination outside"))

    def test_relative_dotdot_destination_is_resolved(self):
        findings = self.preflight(dests=[os.path.join(self.private, "..", "out")])
        self.assertTrue(has(findings, "write destination outside"))

    def test_working_folder_outside_is_refused(self):
        self.assertTrue(has(self.preflight(cwd=self.root), "working folder"))

    def test_root_is_refused(self):
        self.assertTrue(has(self.preflight(settings=dict(SAFE, euid=0)), "running as root"))

    def test_umask_and_core_dumps_are_checked(self):
        findings = self.preflight(settings=dict(SAFE, umask=0o022, core=-1))
        self.assertTrue(has(findings, "umask is 022"))
        self.assertTrue(has(findings, "core dumps are allowed"))

    def test_environment_must_point_into_the_private_folder(self):
        findings = self.preflight(env=self.env(REX_APP_ROOT=None,
                                               TMPDIR=os.path.join(self.root, "tmp"),
                                               XDG_CACHE_HOME="relative/cache",
                                               REX_APP_LOG_ROOT=os.path.join(self.root, "l")))
        self.assertTrue(has(findings, "REX_APP_ROOT is not set"))
        self.assertTrue(has(findings, "TMPDIR is outside"))
        self.assertTrue(has(findings, "XDG_CACHE_HOME is not an absolute path"))
        self.assertTrue(has(findings, "REX_APP_LOG_ROOT is outside"))

    def test_stray_settings_file_is_reported(self):
        env = self.env()
        folder = os.path.join(env["XDG_CONFIG_HOME"], "rexglue")
        os.makedirs(folder)
        settings_file = os.path.join(folder, "rexglue.toml")
        open(settings_file, "w").close()
        self.assertTrue(has(self.preflight(env=env), "settings file read before"))
        self.assertEqual(self.preflight(env=env, allowed_settings=[settings_file]), [])

    def test_settings_file_next_to_the_executable_is_reported(self):
        bin_dir = os.path.join(self.root, "bin")
        os.mkdir(bin_dir)
        open(os.path.join(bin_dir, "rexglue.toml"), "w").close()
        self.assertTrue(has(self.preflight(sdk_bin=bin_dir), "settings file read before"))

    def test_xexp_next_to_the_xex_is_reported(self):
        game = os.path.join(self.private, "game")
        open(os.path.join(game, "default.xexp"), "wb").close()
        self.assertTrue(has(self.preflight(game_root=game), "title update patch"))
        self.assertEqual(self.preflight(game_root=game, allow_xexp=True), [])

    def test_game_folder_outside_is_refused(self):
        game = os.path.join(self.root, "game")
        os.mkdir(game)
        self.assertTrue(has(self.preflight(game_root=game), "game folder is outside"))

    def test_left_guest_memory_object_is_reported(self):
        open(os.path.join(self.shm, "xenia_memory_123_0000abcd"), "w").close()
        open(os.path.join(self.shm, "unrelated"), "w").close()
        findings = self.preflight()
        self.assertTrue(has(findings, "xenia_memory_123_0000abcd"))
        self.assertFalse(has(findings, "unrelated"))

    def test_invalid_private_folder_stops_early(self):
        self.private = os.path.join(self.root, "absent")
        self.assertEqual(len(self.preflight()), 1)

    # P-34: the write destinations are required.
    def test_missing_destinations_are_a_finding(self):
        self.assertTrue(has(self.preflight(dests=[]), "no write destination declared"))

    def test_no_writes_replaces_the_destinations(self):
        self.assertEqual(self.preflight(no_writes=True), [])

    def test_no_writes_with_destinations_is_contradictory(self):
        findings = self.preflight(no_writes=True,
                                  dests=[os.path.join(self.private, "generated")])
        self.assertTrue(has(findings, "contradicts"))

    # P-32: /dev/shm that cannot be listed fails closed.
    def test_unlistable_shm_folder_is_a_finding(self):
        for shm in (os.path.join(self.root, "no-shm"), os.path.join(self.root, "shm-file")):
            if shm.endswith("file"):
                open(shm, "w").close()
            findings = self.preflight(shm_dir=shm)
            self.assertTrue(has(findings, f"incomplete check: cannot list {shm}"), shm)


class PostflightTest(Base):
    def marker(self):
        path = os.path.join(self.private, "logs", "marker")
        guard.write_marker(self.private, path)
        time.sleep(0.05)
        return path

    def write(self, path, data=b"x"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def test_marker_must_be_in_the_private_folder(self):
        with self.assertRaises(ValueError):
            guard.write_marker(self.private, os.path.join(self.root, "marker"))

    def test_missing_marker_is_a_finding(self):
        findings, _ = guard.postflight(self.private, os.path.join(self.private, "none"),
                                       watch=[self.home], shm_dir=self.shm)
        self.assertTrue(has(findings, "marker not found"))

    def test_new_file_outside_is_found_and_inside_is_not(self):
        old = os.path.join(self.home, "old.txt")
        self.write(old)
        marker = self.marker()
        self.write(os.path.join(self.home, ".config", "rexglue", "logs", "rexglue_001.log"))
        self.write(os.path.join(self.private, "generated", "out.cpp"))
        findings, _ = guard.postflight(self.private, marker, watch=[self.home, self.root],
                                       shm_dir=self.shm)
        self.assertTrue(has(findings, "rexglue_001.log"))
        self.assertFalse(has(findings, "out.cpp"))
        self.assertFalse(has(findings, "old.txt"))
        self.assertEqual(len([f for f in findings if "rexglue_001.log" in f]), 1)

    def test_file_moved_in_after_the_marker_is_found(self):
        src = os.path.join(self.root, "elsewhere", "moved.bin")
        self.write(src)
        marker = self.marker()
        os.rename(src, os.path.join(self.home, "moved.bin"))
        findings, _ = guard.postflight(self.private, marker, watch=[self.home],
                                       shm_dir=self.shm)
        self.assertTrue(has(findings, "moved.bin"))

    def test_nothing_new_passes(self):
        self.write(os.path.join(self.home, "old.txt"))
        marker = self.marker()
        findings, notes = guard.postflight(self.private, marker, watch=[self.home],
                                           shm_dir=self.shm)
        self.assertEqual(findings, [])
        self.assertEqual(notes, [])

    # P-33: a watched place that cannot be searched in full is a finding.
    def test_absent_required_watch_folder_is_a_finding(self):
        marker = self.marker()
        absent = os.path.join(self.root, "nope")
        findings, _ = guard.postflight(self.private, marker, watch=[self.home, absent],
                                       shm_dir=self.shm)
        self.assertTrue(has(findings, f"incomplete check: watched folder absent or not a "
                                      f"folder: {absent}"))

    def test_absent_optional_watch_folder_is_only_a_note(self):
        marker = self.marker()
        absent = os.path.join(self.root, "nope")
        findings, notes = guard.postflight(self.private, marker, watch=[self.home],
                                           shm_dir=self.shm, optional=[absent])
        self.assertEqual(findings, [])
        self.assertTrue(has(notes, "optional watched folder absent"))

    def test_present_optional_watch_folder_is_searched(self):
        extra = os.path.join(self.root, "extra")
        os.mkdir(extra)
        marker = self.marker()
        self.write(os.path.join(extra, "new.bin"))
        findings, _ = guard.postflight(self.private, marker, watch=[], shm_dir=self.shm,
                                       optional=[extra])
        self.assertTrue(has(findings, "new.bin"))

    def test_unreadable_subfolder_is_a_finding(self):
        locked = os.path.join(self.home, "locked")
        os.mkdir(locked)
        marker = self.marker()
        real_scandir = os.scandir

        def scandir(path="."):
            if os.fspath(path) == locked:
                raise PermissionError(13, "Permission denied", locked)
            return real_scandir(path)

        # Patched rather than chmod 000, which does not stop root.
        with mock.patch("os.scandir", scandir):
            findings, _ = guard.postflight(self.private, marker, watch=[self.home],
                                           shm_dir=self.shm)
        self.assertTrue(has(findings, "incomplete check: 1 location(s)"))
        self.assertTrue(has(findings, locked))

    def test_unreadable_file_status_is_a_finding(self):
        target = os.path.join(self.home, "unstatable.txt")
        self.write(target)
        marker = self.marker()
        real_lstat = os.lstat

        def lstat(path, *args, **kwargs):
            if os.fspath(path) == target:
                raise PermissionError(13, "Permission denied", target)
            return real_lstat(path, *args, **kwargs)

        with mock.patch("os.lstat", lstat):
            findings, _ = guard.postflight(self.private, marker, watch=[self.home],
                                           shm_dir=self.shm)
        self.assertTrue(has(findings, "incomplete check"))
        self.assertTrue(has(findings, target))

    # P-32 after the step as well.
    def test_unlistable_shm_folder_is_a_finding_after_the_step(self):
        marker = self.marker()
        findings, _ = guard.postflight(self.private, marker, watch=[],
                                       shm_dir=os.path.join(self.root, "no-shm"))
        self.assertTrue(has(findings, "incomplete check: cannot list"))

    def test_left_guest_memory_object_is_found(self):
        marker = self.marker()
        open(os.path.join(self.shm, "xenia_memory_42_deadbeef"), "w").close()
        findings, _ = guard.postflight(self.private, marker, watch=[], shm_dir=self.shm)
        self.assertTrue(has(findings, "xenia_memory_42_deadbeef"))

    def test_failed_store_verification_is_a_finding(self):
        marker = self.marker()
        fake_nix = os.path.join(self.root, "fake-nix")
        with open(fake_nix, "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(fake_nix, 0o755)
        findings, _ = guard.postflight(self.private, marker, watch=[], shm_dir=self.shm,
                                       sdk="/nix/store/x-sdk", nix=fake_nix)
        self.assertTrue(has(findings, "SDK store path was modified"))
        findings, _ = guard.postflight(self.private, marker, watch=[], shm_dir=self.shm,
                                       sdk="/nix/store/x-sdk",
                                       nix=os.path.join(self.root, "no-nix"))
        self.assertTrue(has(findings, "cannot run"))

    @unittest.skipIf(GIT is None, "git is needed")
    def test_repository_changes_are_findings(self):
        repo = os.path.join(self.root, "repo")
        subprocess.run([GIT, "init", "-q", repo], check=True)
        marker = self.marker()
        findings, _ = guard.postflight(self.private, marker, watch=[repo], shm_dir=self.shm,
                                       repo=repo, git=GIT)
        self.assertEqual(findings, [])
        self.write(os.path.join(repo, "generated.cpp"))
        findings, _ = guard.postflight(self.private, marker, watch=[repo], shm_dir=self.shm,
                                       repo=repo, git=GIT)
        self.assertTrue(has(findings, "repository changed"))
        self.assertTrue(has(findings, "file written outside the private folder"))
        # The .git folder itself is not searched: git status rewrites its index.
        self.assertFalse(any(os.sep + ".git" + os.sep in f for f in findings))


@unittest.skipIf(GIT is None, "git is needed for the work tree check")
class CommandLineTest(Base):
    def run_cli(self, *args, env=None):
        full_env = dict(os.environ if env is None else env)
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "private_guard.py"),
                               "--private-dir", self.private, "--git", GIT, *args],
                              capture_output=True, text=True, env=full_env, cwd=self.private)

    def test_check_dir_exit_codes(self):
        self.assertEqual(self.run_cli("check-dir").returncode, 0)
        os.chmod(self.private, 0o750)
        result = self.run_cli("check-dir")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FINDING:", result.stdout)

    def test_preflight_reports_the_unsafe_parent_environment(self):
        env = dict(os.environ)
        for name in guard.REQUIRED_ENV:
            env.pop(name, None)
        result = self.run_cli("preflight", "--shm-dir", self.shm, env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("REX_APP_ROOT is not set", result.stdout)

    def test_preflight_without_destination_fails(self):
        env = dict(os.environ, **self.env())
        result = subprocess.run(
            ["sh", "-c", "umask 077; ulimit -c 0; exec \"$@\"", "sh", sys.executable, "-I",
             os.path.join(HERE, "private_guard.py"), "--private-dir", self.private,
             "--git", GIT, "preflight", "--shm-dir", self.shm],
            capture_output=True, text=True, env=env, cwd=self.private)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no write destination declared", result.stdout)

    def test_postflight_with_absent_watch_folder_fails(self):
        marker = os.path.join(self.private, "logs", "marker")
        guard.write_marker(self.private, marker)
        result = self.run_cli("postflight", "--marker", marker, "--shm-dir", self.shm,
                              "--watch", os.path.join(self.root, "absent"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("incomplete check", result.stdout)

    def test_usage_error_exit_code(self):
        self.assertEqual(self.run_cli("no-such-command").returncode, 2)

    def test_full_cycle_with_the_command_line(self):
        env = dict(os.environ, **self.env())
        script = ("umask 077; ulimit -c 0; exec \"$@\"")
        cmd = ["sh", "-c", script, "sh", sys.executable, "-I",
               os.path.join(HERE, "private_guard.py"), "--private-dir", self.private,
               "--git", GIT]
        marker = os.path.join(self.private, "logs", "marker")
        pre = subprocess.run(cmd + ["preflight", "--shm-dir", self.shm, "--marker", marker,
                                    "--dest", os.path.join(self.private, "generated")],
                             capture_output=True, text=True, env=env, cwd=self.private)
        if os.geteuid() == 0:
            self.assertEqual(pre.returncode, 1)
            self.assertIn("running as root", pre.stdout)
            return
        self.assertEqual(pre.returncode, 0, pre.stdout)
        self.assertTrue(os.path.exists(marker))
        time.sleep(0.05)
        with open(os.path.join(self.home, "leak.log"), "w") as f:
            f.write("x")
        post = subprocess.run(cmd + ["postflight", "--marker", marker, "--shm-dir", self.shm,
                                     "--watch", self.home],
                              capture_output=True, text=True, env=env, cwd=self.private)
        self.assertEqual(post.returncode, 1)
        self.assertIn("leak.log", post.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Tests for private_guard.py (step A4 of docs/J2_PLAN.md).

Every folder is synthesized in a temporary folder at run time; no test reads, needs or
produces game data. Run with `python3 -I tools/test_private_guard.py`.
"""

import contextlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
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


def fake_stat(real, **changes):
    """A stat result with some attributes replaced, for owners and modes a test cannot set."""
    fields = {name: getattr(real, name) for name in (
        "st_mode", "st_ino", "st_dev", "st_nlink", "st_uid", "st_gid", "st_size",
        "st_atime_ns", "st_mtime_ns", "st_ctime_ns")}
    fields.update(changes)
    return types.SimpleNamespace(**fields)


ROOT_0700 = {"st_uid": 0, "st_gid": 0, "st_mode": stat.S_IFDIR | 0o700}


class SystemdPrivateTmpTest(Base):
    """#30: a verified systemd PrivateTmp folder under /tmp is a note, nothing else is.

    The service manager makes these folders root:root 0700, and only a process without
    privileges cannot read them. This container may run as root, and a test cannot chown a
    folder to root or make it unreadable to root. The tests therefore simulate, by patching
    os.lstat, os.open, os.scandir and os.geteuid, what an unprivileged process sees: the
    owner, the mode, the refusal to open, and changes during the check. The parent /tmp and
    the boot id file are replaced by synthetic ones. A real root-owned folder is not
    covered here; test_unprivileged_real_unreadable_own_folder_is_a_finding runs for real
    when the tests run without privileges, as in the Nix build sandbox."""

    # Built, not written out: the repository check refuses any 128-bit hexadecimal token.
    BOOT = "0123456789abcdef" * 2

    def setUp(self):
        super().setUp()
        self.boot_file = os.path.join(self.root, "boot_id")
        with open(self.boot_file, "w") as f:
            f.write("01234567-89ab-cdef-0123-456789abcdef\n")
        patch = mock.patch.object(guard, "BOOT_ID_PATH", self.boot_file)
        patch.start()
        self.addCleanup(patch.stop)
        self.cases = 0
        self.fresh_tmp()
        self.euid = 1000

    def fresh_tmp(self):
        """A new synthetic /tmp, so that each case of a loop is checked alone."""
        self.cases += 1
        self.tmpdir = os.path.join(self.root, f"tmp{self.cases}")
        os.mkdir(self.tmpdir)
        patch = mock.patch.object(guard, "SYSTEMD_TMP_PARENT", self.tmpdir)
        patch.start()
        self.addCleanup(patch.stop)
        self.fake = {}        # path -> attributes lstat reports
        self.on_open = {}     # path -> attributes lstat reports once open has been tried
        self.vanish = set()   # paths whose lstat fails once open has been tried
        self.locked = set()   # paths this process cannot open or list

    def name(self, unit="polkit.service", boot=None, suffix="AbC123"):
        return f"systemd-private-{boot or self.BOOT}-{unit}-{suffix}"

    def make(self, name, parent=None, **attributes):
        path = os.path.join(parent or self.tmpdir, name)
        os.makedirs(path)
        if attributes:
            self.fake[path] = attributes
            self.locked.add(path)
        return path

    def marker(self):
        path = os.path.join(self.private, "logs", "marker")
        guard.write_marker(self.private, path)
        time.sleep(0.05)
        return path

    @contextlib.contextmanager
    def unprivileged(self):
        real_lstat, real_open, real_scandir = os.lstat, os.open, os.scandir
        tried = set()

        def lstat(path, *args, **kwargs):
            key = os.fspath(path)
            if key in tried and key in self.vanish:
                raise FileNotFoundError(2, "No such file or directory", key)
            st = real_lstat(path, *args, **kwargs)
            if key in tried and key in self.on_open:
                return fake_stat(st, **self.on_open[key])
            if key in self.fake:
                return fake_stat(st, **self.fake[key])
            return st

        def open_(path, flags, *args, **kwargs):
            key = os.fspath(path)
            tried.add(key)
            if key in self.locked:
                raise PermissionError(13, "Permission denied", key)
            return real_open(path, flags, *args, **kwargs)

        def scandir(path="."):
            key = os.fspath(path)
            if key in self.locked:
                raise PermissionError(13, "Permission denied", key)
            return real_scandir(path)

        with mock.patch("os.lstat", lstat), mock.patch("os.open", open_), \
                mock.patch("os.scandir", scandir), mock.patch("os.geteuid", lambda: self.euid):
            yield

    def postflight(self, marker, watch=None, **kw):
        kw.setdefault("shm_dir", self.shm)
        with self.unprivileged():
            return guard.postflight(self.private, marker,
                                    watch=[self.tmpdir] if watch is None else watch, **kw)

    def assert_refused(self, findings, notes, path, reason=None):
        self.assertTrue(has(findings, "incomplete check"), findings)
        self.assertTrue(has(findings, path), findings)
        if reason:
            self.assertTrue(has(findings, reason), findings)
        self.assertFalse(has(notes, path), notes)

    # Accepted: the six folders of the user's NixOS machine (#30), and nothing is hidden.
    def test_verified_systemd_folder_is_a_note_not_a_finding(self):
        path = self.make(self.name(), **ROOT_0700)
        findings, notes = self.postflight(self.marker())
        self.assertEqual(findings, [])
        self.assertTrue(has(notes, f"{guard.EXCLUDED}: {path}"))
        self.assertTrue(has(notes, "polkit.service (root:root, mode 0700, this boot)"))
        self.assertTrue(has(notes, "does not search it"))

    def test_the_six_folders_seen_on_the_user_machine_are_notes(self):
        units = ("polkit.service", "systemd-logind.service", "wpa_supplicant.service",
                 "nscd.service", "bluetooth.service", "dbus-broker.service")
        paths = [self.make(self.name(unit, suffix=f"Ab{i}c{i}d"), **ROOT_0700)
                 for i, unit in enumerate(units)]
        findings, notes = self.postflight(self.marker())
        self.assertEqual(findings, [])
        for path in paths:
            self.assertTrue(has(notes, path))
        self.assertEqual(len(notes), 6)

    def test_writes_elsewhere_under_tmp_are_still_found(self):
        self.make(self.name(), **ROOT_0700)
        marker = self.marker()
        os.makedirs(os.path.join(self.tmpdir, "other"))
        with open(os.path.join(self.tmpdir, "other", "leak.log"), "w") as f:
            f.write("x")
        findings, notes = self.postflight(marker)
        self.assertTrue(has(findings, "leak.log"))
        self.assertEqual(len(notes), 1)

    def test_shm_check_still_runs_with_an_excluded_folder(self):
        self.make(self.name(), **ROOT_0700)
        marker = self.marker()
        open(os.path.join(self.shm, "xenia_memory_7_0000beef"), "w").close()
        findings, notes = self.postflight(marker)
        self.assertTrue(has(findings, "xenia_memory_7_0000beef"))
        self.assertEqual(len(notes), 1)

    def test_readable_folder_with_the_systemd_name_is_searched(self):
        path = self.make(self.name())  # owned by this process and readable
        marker = self.marker()
        with open(os.path.join(path, "inside.log"), "w") as f:
            f.write("x")
        findings, notes = self.postflight(marker)
        self.assertTrue(has(findings, os.path.join(path, "inside.log")))
        self.assertEqual(notes, [])

    # Refused: the owner, the group and the mode.
    def test_folder_owned_by_the_user_is_a_finding(self):
        path = self.make(self.name(), st_uid=1000, st_gid=1000,
                         st_mode=stat.S_IFDIR | 0o700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "owner 1000:1000, not root:root")

    def test_folder_of_another_group_is_a_finding(self):
        path = self.make(self.name(), st_uid=0, st_gid=100, st_mode=stat.S_IFDIR | 0o700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "owner 0:100")

    def test_other_modes_are_findings(self):
        for mode in (0o750, 0o755, 0o711, 0o701, 0o1700, 0o2700, 0o4700, 0o600, 0o000):
            with self.subTest(mode=f"{mode:04o}"):
                self.fresh_tmp()
                path = self.make(self.name(), st_uid=0, st_gid=0, st_mode=stat.S_IFDIR | mode)
                findings, notes = self.postflight(self.marker())
                self.assert_refused(findings, notes, path, f"mode {mode:04o}, not 0700")

    # Refused: names that only look like the systemd form.
    def test_near_names_are_ordinary_unreadable_folders(self):
        near = (
            self.name(boot=self.BOOT.upper()),          # upper case boot id
            self.name(boot=self.BOOT[:31]),             # 31 digits
            self.name(boot=self.BOOT + "0"),            # 33 digits
            self.name(unit="polkit"),                   # no unit type
            self.name(unit="multi-user.target"),        # a type without PrivateTmp=
            self.name(suffix="AbC12"),                  # five random characters
            self.name(suffix="AbC1234"),                # seven
            self.name(suffix="AbC_12"),                 # not a letter or digit
            self.name() + "-x",                         # something after the name
            "x" + self.name(),                          # something before
            "systemd-private-",
            f"systemd-private-{self.BOOT}-polkit.service",
            f"systemd-private-{self.BOOT}--AbC123",
        )
        for name in near:
            with self.subTest(name=name):
                self.fresh_tmp()
                path = self.make(name, **ROOT_0700)
                findings, notes = self.postflight(self.marker())
                self.assert_refused(findings, notes, path)
                # Refused by the name rule itself, before any other condition is looked at.
                self.assertFalse(has(findings, "not accepted as a systemd"), findings)

    def test_folder_of_another_boot_is_a_finding(self):
        path = self.make(self.name(boot="f" * 32), **ROOT_0700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "not named for the current boot")

    def test_unreadable_boot_id_is_a_finding(self):
        path = self.make(self.name(), **ROOT_0700)
        with mock.patch.object(guard, "BOOT_ID_PATH", os.path.join(self.root, "absent")):
            findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "the boot id cannot be read")

    def test_entry_that_is_not_a_folder_is_a_finding(self):
        for label, kind in (("file", stat.S_IFREG), ("socket", stat.S_IFSOCK),
                            ("fifo", stat.S_IFIFO), ("device", stat.S_IFBLK)):
            with self.subTest(kind=label):
                self.fresh_tmp()
                path = self.make(self.name(), st_uid=0, st_gid=0, st_mode=kind | 0o700)
                findings, notes = self.postflight(self.marker())
                self.assert_refused(findings, notes, path, "not a real folder")

    # Refused: the place.
    def test_nested_folder_is_a_finding(self):
        path = self.make(self.name(), parent=os.path.join(self.tmpdir, "sub"), **ROOT_0700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, f"not directly under {self.tmpdir}")

    def test_folder_inside_a_systemd_folder_is_a_finding(self):
        outer = self.make(self.name())  # readable, so searched
        path = self.make(self.name(suffix="Inner1"), parent=outer, **ROOT_0700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "not directly under")

    def test_folder_outside_tmp_is_a_finding(self):
        path = self.make(self.name(), parent=self.home, **ROOT_0700)
        findings, notes = self.postflight(self.marker(), watch=[self.home])
        self.assert_refused(findings, notes, path, "not directly under")

    # Refused: links.
    def test_link_with_the_systemd_name_is_never_excluded_nor_followed(self):
        target = os.path.join(self.root, "target")
        os.mkdir(target)
        link = os.path.join(self.tmpdir, self.name())
        os.symlink(target, link)
        marker = self.marker()
        with open(os.path.join(target, "behind-the-link.log"), "w") as f:
            f.write("x")
        findings, notes = self.postflight(marker)
        self.assertEqual(notes, [])
        self.assertFalse(has(findings, "behind-the-link.log"))
        self.assertEqual(findings, [])

    def test_new_link_with_the_systemd_name_is_a_finding(self):
        target = os.path.join(self.root, "target")
        os.mkdir(target)
        marker = self.marker()
        link = os.path.join(self.tmpdir, self.name())
        os.symlink(target, link)
        findings, notes = self.postflight(marker)
        self.assertTrue(has(findings, f"file written outside the private folder: {link}"))
        self.assertEqual(notes, [])

    # Refused: a change while the folder is checked.
    def test_change_during_the_check_is_a_finding(self):
        changes = {
            "owner": {"st_uid": 1000},
            "group": {"st_gid": 100},
            "mode": {"st_mode": stat.S_IFDIR | 0o755},
            "type": {"st_mode": stat.S_IFLNK | 0o700},
            "inode": {"st_ino": 1},
            "status change": {"st_ctime_ns": 1},
        }
        for label, change in changes.items():
            with self.subTest(change=label):
                self.fresh_tmp()
                path = self.make(self.name(), **ROOT_0700)
                self.on_open[path] = dict(ROOT_0700, **change)
                findings, notes = self.postflight(self.marker())
                self.assert_refused(findings, notes, path, "changed while it was checked")

    def test_folder_that_vanishes_during_the_check_is_a_finding(self):
        path = self.make(self.name(), **ROOT_0700)
        self.vanish.add(path)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "vanished while it was checked")

    # Refused: a check run as root, and unrelated folders.
    def test_check_run_as_root_excludes_nothing(self):
        self.euid = 0
        path = self.make(self.name(), **ROOT_0700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path, "this check runs as root")

    def test_unrelated_unreadable_folder_under_tmp_is_a_finding(self):
        path = self.make("some-root-tool", **ROOT_0700)
        findings, notes = self.postflight(self.marker())
        self.assert_refused(findings, notes, path)

    @unittest.skipIf(os.geteuid() == 0, "root can read any folder")
    def test_unprivileged_real_unreadable_own_folder_is_a_finding(self):
        # Not simulated: a folder of this process with mode 0000 and the systemd name.
        path = os.path.join(self.tmpdir, self.name())
        os.mkdir(path)
        os.chmod(path, 0o000)
        with mock.patch.object(guard, "BOOT_ID_PATH", self.boot_file):
            findings, notes = guard.postflight(self.private, self.marker(),
                                               watch=[self.tmpdir], shm_dir=self.shm)
        self.assert_refused(findings, notes, path, f"owner {os.geteuid()}:")

    @unittest.skipUnless(os.path.exists("/proc/sys/kernel/random/boot_id"), "not Linux")
    def test_boot_id_of_the_running_kernel_is_read(self):
        with mock.patch.object(guard, "BOOT_ID_PATH", "/proc/sys/kernel/random/boot_id"):
            value = guard.current_boot_id()
        self.assertRegex(value, r"^[0-9a-f]{32}$")

    def test_command_line_says_what_is_excluded(self):
        self.make(self.name(), **ROOT_0700)
        marker = self.marker()
        out = io.StringIO()
        with self.unprivileged(), contextlib.redirect_stdout(out):
            status = guard.main(["--private-dir", self.private, "postflight", "--marker",
                                 marker, "--shm-dir", self.shm, "--watch", self.tmpdir])
        self.assertEqual(status, 0, out.getvalue())
        self.assertIn(f"note: {guard.EXCLUDED}", out.getvalue())
        self.assertIn("except 1 folder(s) excluded from the watched scope", out.getvalue())


class ScopeNotesTest(PostflightTest):
    """Folders left out of the search are named, and links are never followed (#30)."""

    def test_folder_on_another_file_system_is_a_note(self):
        mount = os.path.join(self.home, "mnt")
        os.mkdir(mount)
        marker = self.marker()
        with open(os.path.join(mount, "inside.log"), "w") as f:
            f.write("x")
        real_lstat = os.lstat

        def lstat(path, *args, **kwargs):
            st = real_lstat(path, *args, **kwargs)
            if os.fspath(path) == mount:
                return fake_stat(st, st_dev=st.st_dev + 1)
            return st

        with mock.patch("os.lstat", lstat):
            findings, notes = guard.postflight(self.private, marker, watch=[self.home],
                                               shm_dir=self.shm)
        self.assertEqual(findings, [])
        self.assertTrue(has(notes, f"{guard.EXCLUDED}: {mount} is on another file system"))

    def test_new_link_to_a_folder_is_found(self):
        target = os.path.join(self.root, "elsewhere")
        os.mkdir(target)
        marker = self.marker()
        link = os.path.join(self.home, "link-to-folder")
        os.symlink(target, link)
        findings, _ = guard.postflight(self.private, marker, watch=[self.home],
                                       shm_dir=self.shm)
        self.assertTrue(has(findings, f"file written outside the private folder: {link}"))

    def test_new_link_into_the_private_folder_is_found(self):
        marker = self.marker()
        links = (os.path.join(self.home, "to-private-folder"),
                 os.path.join(self.home, "to-private-file"))
        os.symlink(os.path.join(self.private, "generated"), links[0])
        os.symlink(os.path.join(self.private, "logs", "marker"), links[1])
        findings, _ = guard.postflight(self.private, marker, watch=[self.home],
                                       shm_dir=self.shm)
        for link in links:
            self.assertTrue(has(findings, f"file written outside the private folder: {link}"),
                            findings)


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

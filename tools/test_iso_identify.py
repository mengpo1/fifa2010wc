#!/usr/bin/env python3
"""Tests for iso_identify.py.

Every disc image and XEX module is synthesized in a temporary folder at run time, from
the formats only: no game data is used and the repository holds no sample. The key and
signature fields of the synthetic modules are filled with marker bytes, and the tests
check that these bytes never reach a report.
Run with `python3 -I tools/test_iso_identify.py`.
"""

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "iso_identify.py")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


iso = load("iso_identify", TOOL)
checker = load("check_proprietary_data", os.path.join(HERE, "check_proprietary_data.py"))

# Marker bytes of the fields the tool must never read or report.
AES_KEY = bytes(range(0xA0, 0xB0))
LAN_KEY = bytes(range(0xC0, 0xD0))
MEDIA_ID_128 = bytes(range(0xE0, 0xF0))
RSA_SIGNATURE = bytes(range(0x30, 0x50)) * 8
SECRETS = (AES_KEY, LAN_KEY, MEDIA_ID_128, RSA_SIGNATURE)


def version(major, minor, build, qfe):
    return (major << 28) | (minor << 24) | (build << 8) | qfe


def pad4(data, fill=b"\0"):
    return data + fill * (-len(data) % 4)


def make_xex(title_id=0x454108E4, media_id=0x1234ABCD, module_flags=0x01,
             encryption=1, compression=2, region=0x00FF0000, magic=b"XEX2",
             pe_name=b"default.exe", broken_imports=False):
    """A synthetic XEX2 module: fixed header, optional headers, security info, data."""
    blocks = []  # (key, payload) stored at an offset
    inline = [(0x00010100, 0x82001000), (0x00010201, 0x82000000), (0x00030000, 0x00000400)]

    blocks.append((0x000003FF, struct.pack(">IHH", 0x24, encryption, compression)
                   + b"\0" * (0x24 - 8)))
    blocks.append((0x00040006, struct.pack(">IIII4BI", media_id, version(1, 0, 0, 0),
                                           version(0, 0, 0, 0), title_id, 0, 0, 1, 1,
                                           0x454108E4)))
    name = pad4(pe_name + b"\0")
    blocks.append((0x000183FF, struct.pack(">I", 4 + len(name)) + name))
    strings = pad4(b"xboxkrnl.exe\0") + pad4(b"xam.xex\0")
    libraries = b""
    for index, (v, vmin) in enumerate(((version(2, 0, 20871, 0), version(2, 0, 17559, 0)),
                                       (version(2, 0, 20871, 0), version(2, 0, 17489, 0)))):
        records = struct.pack(">II", 0x82100000 + index, 0x82100004 + index)
        libraries += struct.pack(">I", 0x28 + len(records)) + b"\x77" * 0x14 + \
            struct.pack(">IIIHH", index, v, vmin, 7 if broken_imports else index, 2) + records
    table = struct.pack(">II", len(strings), 2) + strings + libraries
    blocks.append((0x000103FF, struct.pack(">I", 4 + len(table)) + table))
    static = b"".join(n.ljust(8, b"\0") + struct.pack(">HHHBB", 2, 0, 9328, 2, 1)
                      for n in (b"XAPILIB", b"D3D9"))
    blocks.append((0x000200FF, struct.pack(">I", 4 + len(static)) + static))
    blocks.append((0x00018002, struct.pack(">II", 0, 1268000000)))
    blocks.append((0x000407FF, struct.pack(">II", 8, 0x45410000)))
    blocks.append((0x00040404, LAN_KEY))

    count = len(inline) + len(blocks)
    offset = 0x18 + 8 * count
    table_entries, data = b"", b""
    for key, value in inline:
        table_entries += struct.pack(">II", key, value)
    for key, payload in blocks:
        table_entries += struct.pack(">II", key, offset + len(data))
        data += pad4(payload)
    security_offset = offset + len(data)
    security = struct.pack(">II", 0, 0x200000) + RSA_SIGNATURE + struct.pack(
        ">III", 0x174, 0x10000008, 0x82000000) + b"\x11" * 0x14 + struct.pack(">I", 2) + \
        b"\x22" * 0x14 + MEDIA_ID_128 + AES_KEY + struct.pack(">I", 0) + b"\x33" * 0x14 + \
        struct.pack(">III", region, 0x00000002, 1) + struct.pack(">I", 0x10 | 1) + b"\x44" * 0x14
    header_size = security_offset + len(security)
    fixed = struct.pack(">4sIIIII", magic, module_flags, header_size, 0, security_offset, count)
    image_data = b"\xA5" * 512  # stands for the (encrypted) image data, never read
    return fixed + table_entries + data + security + image_data


def build_xdvdfs(tree, partition=0):
    """Chunks (offset, bytes) and size of an XDVDFS image of `tree`, a dict that maps a
    name to bytes (file) or to a dict (folder). Each folder table is a chain of entries
    linked by their right child, a valid but unbalanced XDVDFS tree."""
    chunks = []
    next_sector = [33]

    def allocate(size):
        sector = next_sector[0]
        next_sector[0] += max(1, -(-size // iso.SECTOR))
        return sector

    def table_layout(node):
        names = sorted(node, key=lambda n: n.upper())
        offsets, position = [], 0
        for name in names:
            offsets.append(position)
            position += -(-(iso.ENTRY_HEADER + len(name)) // 4) * 4
        return names, offsets, position

    def write_dir(node):
        names, offsets, size = table_layout(node)
        sector = allocate(size)
        table = bytearray()
        for i, name in enumerate(names):
            child = node[name]
            if isinstance(child, dict):
                if child:
                    child_sector, child_size = write_dir(child)
                else:
                    child_sector, child_size = 0, 0
                attributes = iso.ATTR_DIRECTORY
            else:
                child_sector, child_size = allocate(len(child)), len(child)
                chunks.append((partition + child_sector * iso.SECTOR, child))
                attributes = 0x20
            right = offsets[i + 1] // 4 if i + 1 < len(names) else 0
            entry = struct.pack("<HHIIBB", 0, right, child_sector, child_size, attributes,
                                len(name)) + name.encode("latin-1")
            table += entry + b"\xff" * (-len(entry) % 4)
        rounded = -(-len(table) // iso.SECTOR) * iso.SECTOR
        table += b"\xff" * (rounded - len(table))
        chunks.append((partition + sector * iso.SECTOR, bytes(table)))
        return sector, len(table)

    root_sector, root_size = write_dir(tree)
    volume = iso.XDVDFS_MAGIC + struct.pack("<IIQ", root_sector, root_size, 0)
    volume += b"\0" * (0x7EC - len(volume)) + iso.XDVDFS_MAGIC
    chunks.append((partition + iso.MAGIC_SECTOR * iso.SECTOR, volume))
    return chunks, partition + next_sector[0] * iso.SECTOR


def write_image(path, tree, partition=0, truncate_to=None):
    chunks, size = build_xdvdfs(tree, partition)
    with open(path, "wb") as f:
        for offset, data in chunks:
            f.seek(offset)
            f.write(data)
        f.truncate(size if truncate_to is None else truncate_to)


def write_folder(root, tree):
    for name, child in tree.items():
        path = os.path.join(root, name)
        if isinstance(child, dict):
            os.makedirs(path)
            write_folder(path, child)
        else:
            with open(path, "wb") as f:
                f.write(child)


def sample_tree():
    return {
        "default.xex": make_xex(),
        "fifadllzf.xex": make_xex(module_flags=0x08, pe_name=b"fifadllzf.dll"),
        "data": {"readme.txt": b"synthetic\n", "sub": {"a.txt": b"a" * 3000}},
        "$SystemUpdate": {},
    }


class IdentifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.image = os.path.join(self.dir, "disc.img")

    def tearDown(self):
        self.tmp.cleanup()

    def identify_image(self, tree=None, partition=0, image_hash=True, **kwargs):
        write_image(self.image, sample_tree() if tree is None else tree, partition, **kwargs)
        return iso.identify(self.image, image_hash=image_hash)

    def module(self, report, path):
        return next(m for m in report["modules"] if m["path"] == path)

    def test_image_is_identified(self):
        report = self.identify_image()
        self.assertEqual(report["disc"]["partition_offset"], "0x00000000")
        self.assertIn("xiso", report["disc"]["layout"])
        self.assertEqual(report["disc"]["files"], 4)
        self.assertEqual(report["disc"]["directories"], 3)
        self.assertEqual(report["disc"]["files_outside_image"], 0)
        with open(self.image, "rb") as f:
            self.assertEqual(report["source"]["sha256"], hashlib.sha256(f.read()).hexdigest())
        self.assertEqual(len(report["source"]["crc32"]), 8)
        top = {row["name"]: row for row in report["disc"]["top_level"]}
        self.assertEqual(top["data"], {"name": "data", "type": "directory", "files": 2,
                                       "bytes": 3010})
        self.assertEqual(top["$SystemUpdate"]["files"], 0)

        default = self.module(report, "default.xex")
        self.assertEqual(default["sha256"], hashlib.sha256(make_xex()).hexdigest())
        header = default["header"]
        self.assertEqual(header["anomalies"], [])
        self.assertEqual(header["execution"]["title_id"], "454108E4")
        self.assertEqual(header["execution"]["media_id"], "1234ABCD")
        self.assertEqual(header["execution"]["version"], "1.0.0.0")
        self.assertEqual(header["file_format"]["encryption"], "normal (AES)")
        self.assertTrue(header["file_format"]["encrypted"])
        self.assertEqual(header["file_format"]["compression"], "normale (LZX)")
        self.assertEqual(header["security"]["region"]["names"],
                         ["PAL (Europe, Australie et Nouvelle-Zélande) (complet)"])
        self.assertEqual(header["security"]["load_address"], "0x82000000")
        self.assertEqual(header["security"]["image_flags"]["names"],
                         ["XGD2MediaOnly", "PageSize4KB"])
        self.assertEqual(header["security"]["allowed_media"]["names"], ["DVDX2"])
        self.assertEqual(header["import_libraries"], [
            {"name": "xboxkrnl.exe", "version": "2.0.20871.0", "min_version": "2.0.17559.0"},
            {"name": "xam.xex", "version": "2.0.20871.0", "min_version": "2.0.17489.0"}])
        self.assertEqual([lib["name"] for lib in header["static_libraries"]], ["XAPILIB", "D3D9"])
        self.assertEqual(header["static_libraries"][0]["version"], "2.0.9328.1")
        self.assertEqual(header["original_pe_name"], "default.exe")
        self.assertEqual(header["build_timestamp"], "2010-03-07T22:13:20Z")
        self.assertEqual(header["alternate_title_ids"], ["45410000"])
        self.assertEqual(header["entry_point"], "0x82001000")
        self.assertEqual(header["system_flags"]["names"], ["PAL50Incompatible"])
        self.assertIn("LANKey", header["headers_present"])
        self.assertFalse(header["is_patch"])
        self.assertEqual(self.module(report, "fifadllzf.xex")["header"]["module_flags"]["names"],
                         ["DLLModule"])

        verdict = report["verdict"]
        self.assertTrue(verdict["identified"])
        self.assertTrue(verdict["title_id_matches"])
        self.assertFalse(verdict["project_a_europe_disc"])
        self.assertEqual(verdict["project_a_modules"],
                         {"default.xex": "différente", "fifadllzf.xex": "différente"})
        self.assertEqual(verdict["encrypted_modules"], ["default.xex", "fifadllzf.xex"])
        self.assertEqual(report["anomalies"], [])

    def test_partition_offsets(self):
        for partition, label in ((0x02080000, "XGD3"), (0x0FD90000, "XGD2")):
            with self.subTest(label=label):
                report = self.identify_image(partition=partition, image_hash=False)
                self.assertEqual(report["disc"]["layout"], label)
                self.assertEqual(report["disc"]["partition_offset"], f"0x{partition:08X}")
                self.assertTrue(report["verdict"]["identified"])
                self.assertNotIn("sha256", report["source"])

    def test_project_a_verdict(self):
        tree = sample_tree()
        hashes = {name: hashlib.sha256(tree[name]).hexdigest()
                  for name in ("default.xex", "fifadllzf.xex")}
        saved = dict(iso.PROJECT_A_SHA256)
        try:
            iso.PROJECT_A_SHA256.update(hashes)
            report = self.identify_image(tree)
            self.assertTrue(report["verdict"]["project_a_europe_disc"])
            iso.PROJECT_A_SHA256["fifadllzf.xex"] = "0" * 64
            report = self.identify_image(tree)
            self.assertFalse(report["verdict"]["project_a_europe_disc"])
            self.assertEqual(report["verdict"]["project_a_modules"],
                             {"default.xex": "identique", "fifadllzf.xex": "différente"})
            del tree["fifadllzf.xex"]
            report = self.identify_image(tree)
            self.assertEqual(report["verdict"]["project_a_modules"]["fifadllzf.xex"], "absent")
        finally:
            iso.PROJECT_A_SHA256.clear()
            iso.PROJECT_A_SHA256.update(saved)

    def test_key_and_signature_fields_never_reach_a_report(self):
        report = self.identify_image()
        texts = (iso.render_markdown(report), iso.render_json(report))
        for text in texts:
            for secret in SECRETS:
                for form in (secret.hex(), secret.hex().upper(), secret[:8].hex()):
                    self.assertNotIn(form, text)
                self.assertNotIn(secret.decode("latin-1"), text)
            self.assertIsNone(iso.HEX128_RE.search(text))
            iso.check_shareable(text)

    def test_report_passes_the_repository_data_check(self):
        report = self.identify_image()
        for name, text in (("report.md", iso.render_markdown(report)),
                           ("report.json", iso.render_json(report))):
            path = os.path.join(self.dir, "reports", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.assertEqual(checker.check_repo_file(self.dir, os.path.join("reports", name), []),
                             [])

    def test_token_pattern_is_the_checker_pattern(self):
        self.assertEqual(iso.HEX128_RE.pattern, checker.HEX128_RE.pattern.decode("ascii"))

    def test_128_bit_token_in_a_name_is_redacted(self):
        token = bytes(range(16)).hex()
        tree = sample_tree()
        tree[token + ".dat"] = b"x"
        report = self.identify_image(tree)
        text = iso.render_markdown(report) + iso.render_json(report)
        self.assertNotIn(token, text)
        self.assertIn(iso.REDACTED, text)
        self.assertTrue(any("128 bits" in a for a in report["anomalies"]))

    def test_no_xdvdfs_volume(self):
        with open(self.image, "wb") as f:
            f.write(b"\0" * (40 * iso.SECTOR))
        report = iso.identify(self.image)
        self.assertIsNone(report["disc"])
        self.assertFalse(report["verdict"]["identified"])
        self.assertTrue(any("XDVDFS" in a for a in report["anomalies"]))
        self.assertIn("## Anomalies", iso.render_markdown(report))

    def test_stfs_container_points_to_rexglue_vfs_dump(self):
        with open(self.image, "wb") as f:
            f.write(b"CON " + b"\0" * 0xA000)
        report = iso.identify(self.image)
        self.assertTrue(any("rexglue vfs dump" in a for a in report["anomalies"]))

    def test_truncated_image(self):
        tree = sample_tree()
        chunks, _ = build_xdvdfs(tree)
        default_offset = min(o for o, data in chunks if data == tree["default.xex"])
        report = self.identify_image(tree, truncate_to=default_offset + 100)
        self.assertGreaterEqual(report["disc"]["files_outside_image"], 1)
        self.assertIn("default.xex", report["disc"]["files_outside_image_sample"])
        self.assertIn("error", self.module(report, "default.xex"))
        self.assertFalse(report["verdict"]["identified"])

    def root_sector(self, tree):
        chunks, _ = build_xdvdfs(tree)
        volume = next(d for _, d in chunks if d.startswith(iso.XDVDFS_MAGIC))
        return struct.unpack_from("<I", volume, 20)[0]

    def test_child_outside_the_table_is_reported(self):
        tree = {"default.xex": make_xex()}
        write_image(self.image, tree)
        with open(self.image, "r+b") as f:
            f.seek(self.root_sector(tree) * iso.SECTOR + 2)
            f.write(struct.pack("<H", 0x3000))  # right child far past the 2 KiB table
        report = iso.identify(self.image)
        self.assertTrue(any("hors de la table" in a for a in report["anomalies"]))
        self.assertTrue(report["verdict"]["identified"])

    def test_self_referencing_entry_is_a_loop(self):
        tree = {"a.txt": b"a", "default.xex": make_xex()}
        write_image(self.image, tree)
        root_sector = self.root_sector(tree)
        second = -(-(14 + len("a.txt")) // 4)  # ordinal of the second entry
        with open(self.image, "r+b") as f:
            f.seek(root_sector * iso.SECTOR + second * 4 + 2)
            f.write(struct.pack("<H", second))  # right child of the second entry: itself
        report = iso.identify(self.image)
        self.assertTrue(any("boucle" in a for a in report["anomalies"]))
        self.assertTrue(report["verdict"]["identified"])

    def test_folder_matches_image(self):
        folder = os.path.join(self.dir, "game")
        os.makedirs(folder)
        write_folder(folder, sample_tree())
        from_folder = iso.identify(folder)
        from_image = self.identify_image()
        self.assertEqual(from_folder["source"]["kind"], "folder")
        self.assertEqual(from_folder["disc"]["files"], from_image["disc"]["files"])
        self.assertEqual(from_folder["disc"]["top_level"], from_image["disc"]["top_level"])
        for a, b in zip(from_folder["modules"], from_image["modules"]):
            self.assertEqual((a["path"], a["sha256"], a["header"]),
                             (b["path"], b["sha256"], b["header"]))
        self.assertEqual(from_folder["verdict"], from_image["verdict"])

    def test_not_an_xex2_module(self):
        tree = sample_tree()
        tree["default.xex"] = make_xex(magic=b"XEX1")
        report = self.identify_image(tree)
        header = self.module(report, "default.xex")["header"]
        self.assertEqual(header["magic"], "XEX1")
        self.assertIn("error", header)
        self.assertFalse(report["verdict"]["identified"])

    def test_corrupt_optional_header_is_reported(self):
        tree = sample_tree()
        tree["default.xex"] = make_xex(broken_imports=True)
        report = self.identify_image(tree)
        header = self.module(report, "default.xex")["header"]
        self.assertNotIn("import_libraries", header)
        self.assertTrue(any("missing string" in a for a in header["anomalies"]))
        self.assertTrue(any(a.startswith("`default.xex`") for a in report["anomalies"]))
        self.assertTrue(report["verdict"]["identified"])  # the rest of the header is read

    def test_unencrypted_module(self):
        tree = sample_tree()
        tree["default.xex"] = make_xex(encryption=0, compression=1, region=0xFFFFFFFF)
        report = self.identify_image(tree)
        header = self.module(report, "default.xex")["header"]
        self.assertFalse(header["file_format"]["encrypted"])
        self.assertEqual(header["security"]["region"]["names"], ["toutes les régions"])
        self.assertEqual(report["verdict"]["encrypted_modules"], ["fifadllzf.xex"])

    def test_nix_store_paths(self):
        self.assertTrue(iso.in_nix_store("/nix/store/abc-source/disc.iso"))
        self.assertTrue(iso.in_nix_store("/nix/store"))
        self.assertFalse(iso.in_nix_store("/nix/storefront/disc.iso"))
        self.assertFalse(iso.in_nix_store(self.image))


class ReXGlueFixtureTest(unittest.TestCase):
    """Cross-check with an image made by others: the synthetic GDFX fixture of ReXGlue
    v0.11.0 (tests/fixtures/filesystem/gdfx.iso, BSD 3-Clause), against the names and
    contents its own test expects (tests/unit/filesystem/providers_test.cpp). The Nix
    check sets REXGLUE_SRC to the pinned ReXGlue source; without it the test is skipped."""

    def test_rexglue_gdfx_fixture(self):
        source = os.environ.get("REXGLUE_SRC")
        if not source:
            self.skipTest("REXGLUE_SRC is not set")
        path = os.path.join(source, "tests", "fixtures", "filesystem", "gdfx.iso")
        image = iso.DiscImage(path)
        try:
            partition, _ = iso.find_partition(image)
            anomalies = []
            entries = {e.path: e for e in iso.walk_xdvdfs(image, partition, anomalies)}
            self.assertEqual(anomalies, [])
            self.assertEqual(sorted(entries), ["a.txt", "big.bin", "folder", "folder/c.txt"])
            self.assertTrue(entries["folder"].is_dir)

            def content(name):
                return iso.DiscImage.reader(image, entries[name])(0, entries[name].size)
            self.assertEqual(content("a.txt"), b"alpha\n")
            self.assertEqual(content("big.bin"), bytes(i % 251 for i in range(0x1800)))
            self.assertEqual(content("folder/c.txt"), b"charlie in folder\n")
        finally:
            image.close()
        report = iso.identify(path, image_hash=False)
        self.assertEqual(report["disc"]["files"], 3)
        self.assertFalse(report["verdict"]["identified"])  # no default.xex in the fixture


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.image = os.path.join(self.dir, "disc.img")
        write_image(self.image, sample_tree())

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", TOOL, *args], capture_output=True,
                              text=True)

    def test_reports_are_written(self):
        out_json = os.path.join(self.dir, "report.json")
        out_md = os.path.join(self.dir, "report.md")
        result = self.run_tool("--json", out_json, "--markdown", out_md, self.image)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("`454108E4`", result.stdout)
        with open(out_md, encoding="utf-8") as f:
            self.assertEqual(f.read(), result.stdout)
        with open(out_json, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["verdict"]["identified"])
        self.assertNotIn(self.dir, result.stdout)  # the local path is not reported

    def test_not_identified_exit_status(self):
        blank = os.path.join(self.dir, "blank.img")
        with open(blank, "wb") as f:
            f.write(b"\0" * 4096)
        self.assertEqual(self.run_tool(blank).returncode, 3)

    def test_refusals(self):
        result = self.run_tool("--json", "/nix/store/report.json", self.image)
        self.assertEqual(result.returncode, 2)
        self.assertIn("/nix/store", result.stderr)
        self.assertEqual(self.run_tool(os.path.join(self.dir, "missing.iso")).returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

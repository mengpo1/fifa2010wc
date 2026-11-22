#!/usr/bin/env python3
"""Identify an Xbox 360 disc image without decrypting anything (milestone J0).

From the user's own disc image, or from a folder extracted from it, the tool reads:
  - the disc layout (XDVDFS volume descriptor) and the file tree, without extracting it;
  - the SHA-256 and SHA-1 of the image and of every XEX module, computed in memory;
  - the plaintext header fields of each XEX module: execution info (title ID, media ID,
    version), file format info (encryption and compression types), security info
    (regions, media types, load address), import and static libraries.

It never decrypts anything. To hash a module, it reads all of its bytes, the image data
included (encrypted on retail discs); to read a header, it loads the whole header into
memory, key and signature fields included. From it, it picks out only the plaintext
fields listed above: the encrypted AES key, the LAN key, the 128-bit media ID, the RSA
signature and the digests are never selected, decoded or written to a report.
It writes nothing but the reports asked for, and never onto the source: a report path
that names the source image, or a file or folder of the source folder, under any name
(alias, symbolic link, hard link), is refused before the source is read (see main()).
A report holds hashes, file names and sizes, and header metadata, which D-007 allows to
share. MD5 is not computed: its 32 hexadecimal digits look like a 128-bit key to the
proprietary data check of the repository; SHA-1 and CRC32 cover the Redump comparison.

The formats follow ReXGlue v0.11.0: include/rex/kernel/types/xex.h (XEX2 headers),
src/filesystem/xex.cpp (import string table) and src/filesystem/gdfx.cpp (XDVDFS).
ReXGlue itself offers no command that prints these headers without decrypting the
module (`rexglue codegen` decrypts it) or that reads a file of a disc image without
extracting the whole image (`rexglue vfs dump`).

Usage: iso_identify.py [--no-image-hash] [--json FILE] [--markdown FILE] SOURCE
  SOURCE  the disc image file, or a folder that holds the extracted disc.
The Markdown report is printed on stdout; --json and --markdown also write it to files.
Exit status: 0 identified; 3 read but not identified (no XDVDFS volume, no default.xex,
or a default.xex header that cannot be read); 2 usage or input error, a refused path, or
a report refused by the last check (nothing is written then).
Only the Python standard library is used. Run it with `python3 -I`.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import zlib

TOOL_NAME = "iso_identify"
TOOL_VERSION = 1

# Identification references (docs/audit/ISO_REQUIREMENTS.md §3).
TITLE_ID_EXPECTED = 0x454108E4
# SHA-256 of the two modules of the Europe disc (En, Es, Nl) that project A supports.
PROJECT_A_SHA256 = {
    "default.xex": "d0df5465e077eaebeadda252c786d9322551ab13ef23aad461836e510971337d",
    "fifadllzf.xex": "462676f9fbab83530c2659e79aa43e3dbe81b43dc917db9299933c19fa34905d",
}

# Same pattern as HEX128_RE in check_proprietary_data.py (a test keeps them equal): a lone
# 32 digit hexadecimal token, the size of an AES-128 key, never goes into a report.
HEX128_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{32}(?![0-9A-Fa-f])")
REDACTED = "<128-bit-token-redacted>"

CHUNK = 8 * 1024 * 1024

# --- XDVDFS (src/filesystem/gdfx.cpp) ------------------------------------------------------
SECTOR = 2048
MAGIC_SECTOR = 32
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
# Offset of the game partition in the image. ReXGlue looks at the first five
# (kGameOffsets); XGD1 comes from tools/disc.py of project A.
GAME_PARTITIONS = (
    (0x00000000, "XDVDFS sans partition vidéo (image réduite, « xiso »)"),
    (0x0000FB20, "partition de jeu à 0xFB20 (décalage reconnu par ReXGlue)"),
    (0x00020600, "partition de jeu à 0x20600 (décalage reconnu par ReXGlue)"),
    (0x02080000, "XGD3"),
    (0x0FD90000, "XGD2"),
    (0x18300000, "XGD1 (Xbox d'origine)"),
)
MIN_ROOT_SIZE = 13
MAX_TABLE_SIZE = 32 * 1024 * 1024
ENTRY_HEADER = 14
ATTR_DIRECTORY = 0x10
NO_CHILD = (0, 0xFFFF)
STFS_MAGICS = (b"CON ", b"LIVE", b"PIRS")

# --- XEX2 (include/rex/kernel/types/xex.h) ---------------------------------------------------
XEX2_MAGIC = b"XEX2"
XEX_FIXED_HEADER = 0x18
MAX_XEX_HEADER = 64 * 1024 * 1024
# XEXSecurityInfoHeader: the only fields selected, and the size up to the page descriptors.
# rsa_signature (0x8), the digests, xgd2_media_id (0x140) and aes_key (0x150) are loaded
# with the rest of the header, but never selected, decoded or exported.
SEC_IMAGE_SIZE = 0x004
SEC_IMAGE_FLAGS = 0x10C
SEC_LOAD_ADDRESS = 0x110
SEC_REGION = 0x178
SEC_MEDIA_TYPES = 0x17C
SEC_FIXED_SIZE = 0x184

KEY_FILE_FORMAT = 0x000003FF
KEY_DELTA_PATCH = 0x000005FF
KEY_ENTRY_POINT = 0x00010100
KEY_IMAGE_BASE = 0x00010201
KEY_IMPORT_LIBRARIES = 0x000103FF
KEY_CHECKSUM_TIMESTAMP = 0x00018002
KEY_ORIGINAL_PE_NAME = 0x000183FF
KEY_STATIC_LIBRARIES = 0x000200FF
KEY_SYSTEM_FLAGS = 0x00030000
KEY_EXECUTION_INFO = 0x00040006
KEY_ALTERNATE_TITLE_IDS = 0x000407FF
# kXEXHeaderLANKey (0x00040404) holds a key: only its presence is reported.

HEADER_NAMES = {
    0x000002FF: "ResourceInfo", 0x000003FF: "FileFormatInfo",
    0x000005FF: "DeltaPatchDescriptor", 0x00000405: "BaseReference",
    0x000080FF: "BoundPath", 0x00008105: "DeviceId", 0x00010001: "OriginalBaseAddress",
    0x00010100: "EntryPoint", 0x00010201: "ImageBaseAddress", 0x000103FF: "ImportLibraries",
    0x00018002: "ChecksumTimestamp", 0x00018102: "EnabledForCallCap",
    0x00018200: "EnabledForFastCap", 0x000183FF: "OriginalPEName",
    0x000200FF: "StaticLibraries", 0x00020104: "TLSInfo", 0x00020200: "DefaultStackSize",
    0x00020301: "DefaultFilesystemCacheSize", 0x00020401: "DefaultHeapSize",
    0x00028002: "PageHeapSizeAndFlags", 0x00030000: "SystemFlags",
    0x00040006: "ExecutionInfo", 0x00040201: "TitleWorkspaceSize", 0x00040310: "GameRatings",
    0x00040404: "LANKey", 0x000405FF: "Xbox360Logo", 0x000406FF: "MultiDiscMediaIDs",
    0x000407FF: "AlternateTitleIDs", 0x00040801: "AdditionalTitleMemory",
    0x00E10402: "ExportsByName",
}
MODULE_FLAGS = {
    0x01: "Title", 0x02: "ExportsToTitle", 0x04: "SystemDebugger", 0x08: "DLLModule",
    0x10: "ModulePatch", 0x20: "PatchFull", 0x40: "PatchDelta", 0x80: "UserMode",
}
IMAGE_FLAGS = {
    0x00000002: "ManufacturingUtility", 0x00000004: "ManufacturingSupportTools",
    0x00000008: "XGD2MediaOnly", 0x00000100: "CardeaKey", 0x00000200: "XeikaKey",
    0x00000400: "UserModeTitle", 0x00000800: "UserModeSystem", 0x00001000: "Orange0",
    0x00002000: "Orange1", 0x00004000: "Orange2", 0x00010000: "IPTVSignupApplication",
    0x00020000: "IPTVTitleApplication", 0x04000000: "KeyVaultPrivilegesRequired",
    0x08000000: "OnlineActivationRequired", 0x10000000: "PageSize4KB",
    0x20000000: "RegionFree", 0x40000000: "RevocationCheckOptional",
    0x80000000: "RevocationCheckRequired",
}
MEDIA_FLAGS = {
    0x00000001: "HardDisk", 0x00000002: "DVDX2", 0x00000004: "DVDCD", 0x00000008: "DVD5",
    0x00000010: "DVD9", 0x00000020: "SystemFlash", 0x00000080: "MemoryUnit",
    0x00000100: "USBMassStorageDevice", 0x00000200: "Network", 0x00000400: "DirectFromMemory",
    0x00000800: "RAMDrive", 0x00001000: "SVOD", 0x01000000: "InsecurePackage",
    0x02000000: "SaveGamePackage", 0x04000000: "LocallySignedPackage",
    0x08000000: "LiveSignedPackage", 0x10000000: "XboxPackage",
}
SYSTEM_FLAGS = dict((1 << bit, name) for bit, name in enumerate((
    "NoForcedReboot", "ForegroundTasks", "NoODDMapping", "HandleMCEInput",
    "RestrictedHUDFeatures", "HandleGamepadDisconnect", "InsecureSockets",
    "Xbox1Interoperability", "DashContext", "UsesGameVoiceChannel", "PAL50Incompatible",
    "InsecureUtilityDrive", "XAMHooks", "AccessPII", "CrossPlatformSystemLink",
    "MultiDiscSwap", "MultiDiscInsecureMedia", "AP25Media", "NoConfirmExit",
    "AllowBackgroundDownload", "CreatePersistableRAMDrive", "InheritPersistentRAMDrive",
    "AllowHUDVibration", "AccessUtilityPartitions", "IPTVInputSupported",
    "PreferBigButtonInput", "AllowExtendedSystemReservation", "MultiDiscCrossTitle",
    "InstallIncompatible", "AllowAvatarGetMetadataByXUID", "AllowControllerSwapping",
    "DashExtensibilityModule")))
REGION_GROUPS = (
    (0x000000FF, "NTSC-U (Amérique du Nord)"),
    (0x0000FF00, "NTSC-J (Japon et Asie)"),
    (0x00FF0000, "PAL (Europe, Australie et Nouvelle-Zélande)"),
    (0xFF000000, "autres régions"),
)
ENCRYPTION_TYPES = {0: "aucun", 1: "normal (AES)"}
COMPRESSION_TYPES = {0: "aucune", 1: "basique", 2: "normale (LZX)", 3: "delta"}
APPROVAL_TYPES = {0: "unapproved", 1: "possible", 2: "approved", 3: "expired"}


class FormatError(Exception):
    """The data does not follow the expected format (corrupt or truncated input)."""


def in_nix_store(path):
    real = os.path.realpath(path)
    return real == "/nix/store" or real.startswith("/nix/store/")


def hex32(value):
    return f"{value:08X}"


def version_string(value):
    """XEXVersion: major in bits 28 to 31, minor 24 to 27, build 8 to 23, QFE 0 to 7."""
    return f"{value >> 28}.{(value >> 24) & 0xF}.{(value >> 8) & 0xFFFF}.{value & 0xFF}"


def flag_names(value, table):
    names = [name for bit, name in sorted(table.items()) if value & bit]
    unknown = value & ~sum(table)
    if unknown:
        names.append(f"0x{unknown:08X}")
    return names


def region_names(value):
    if value == 0xFFFFFFFF:
        return ["toutes les régions"]
    names = []
    for mask, name in REGION_GROUPS:
        bits = value & mask
        if bits == mask:
            names.append(f"{name} (complet)")
        elif bits:
            names.append(f"{name} (partiel : 0x{bits:08X})")
    return names


def ascii_z(data):
    return data.split(b"\0", 1)[0].decode("latin-1")


# --- Sources -------------------------------------------------------------------------------

class Entry:
    __slots__ = ("path", "size", "is_dir", "offset")

    def __init__(self, path, size, is_dir, offset=None):
        self.path, self.size, self.is_dir, self.offset = path, size, is_dir, offset


class DiscImage:
    """A disc image file, read at given offsets. Nothing is extracted."""

    kind = "image"

    def __init__(self, path):
        self.file = open(path, "rb")
        self.size = os.fstat(self.file.fileno()).st_size

    def close(self):
        self.file.close()

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.size:
            raise FormatError(f"read of {size} bytes at {offset:#x} is outside the image")
        self.file.seek(offset)
        data = self.file.read(size)
        if len(data) != size:
            raise FormatError(f"short read at {offset:#x}")
        return data

    def reader(self, entry):
        if entry.offset + entry.size > self.size:
            raise FormatError(f"{entry.path} extends past the end of the image")
        return lambda offset, size: self.read(entry.offset + offset, size)


class Folder:
    """A folder that holds an extracted disc."""

    kind = "folder"

    def __init__(self, path):
        self.root = path
        self.handles = []

    def close(self):
        for handle in self.handles:
            handle.close()

    def entries(self, anomalies):
        found = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames.sort()
            rel_dir = os.path.relpath(dirpath, self.root)
            prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/") + "/"
            for name in list(dirnames):
                if os.path.islink(os.path.join(dirpath, name)):
                    anomalies.append(f"lien symbolique ignoré : {prefix}{name}")
                    dirnames.remove(name)
                else:
                    found.append(Entry(prefix + name, 0, True))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or not os.path.isfile(full):
                    anomalies.append(f"fichier spécial ou lien ignoré : {prefix}{name}")
                    continue
                found.append(Entry(prefix + name, os.path.getsize(full), False))
        return found

    def reader(self, entry):
        handle = open(os.path.join(self.root, *entry.path.split("/")), "rb")
        self.handles.append(handle)

        def read(offset, size):
            if offset < 0 or size < 0 or offset + size > entry.size:
                raise FormatError(f"read of {size} bytes at {offset:#x} is outside {entry.path}")
            handle.seek(offset)
            data = handle.read(size)
            if len(data) != size:
                raise FormatError(f"short read in {entry.path}")
            return data
        return read


def find_partition(image):
    for offset, label in GAME_PARTITIONS:
        magic_at = offset + MAGIC_SECTOR * SECTOR
        if magic_at + len(XDVDFS_MAGIC) <= image.size and \
                image.read(magic_at, len(XDVDFS_MAGIC)) == XDVDFS_MAGIC:
            return offset, label
    return None


def walk_xdvdfs(image, partition, anomalies):
    """Every entry of the XDVDFS tree, read from the directory tables in place."""
    volume = partition + MAGIC_SECTOR * SECTOR
    root_sector, root_size = struct.unpack("<II", image.read(volume + 20, 8))
    if not MIN_ROOT_SIZE <= root_size <= MAX_TABLE_SIZE:
        raise FormatError(f"root directory table size {root_size} is out of range")
    entries = []
    tables = [(partition + root_sector * SECTOR, root_size, "")]
    seen_tables = set()
    while tables:
        table_offset, table_size, prefix = tables.pop()
        where = prefix or "/"
        if table_offset in seen_tables:
            anomalies.append(f"table de dossier répétée : {where}")
            continue
        seen_tables.add(table_offset)
        if table_size > MAX_TABLE_SIZE:
            anomalies.append(f"table de dossier trop grande : {where}")
            continue
        try:
            table = image.read(table_offset, table_size)
        except FormatError:
            anomalies.append(f"table de dossier hors de l'image : {where}")
            continue
        if table[:4] == b"\xff\xff\xff\xff":
            continue  # empty directory
        stack, seen = [0], set()
        while stack:
            ordinal = stack.pop()
            if ordinal in seen:
                anomalies.append(f"entrée répétée dans la table de {where} (boucle)")
                continue
            seen.add(ordinal)
            pos = ordinal * 4
            if pos + ENTRY_HEADER > table_size:
                anomalies.append(f"entrée hors de la table de {where}")
                continue
            left, right, sector, length, attributes, name_length = \
                struct.unpack_from("<HHIIBB", table, pos)
            if pos + ENTRY_HEADER + name_length > table_size or name_length == 0:
                anomalies.append(f"nom d'entrée invalide dans la table de {where}")
                continue
            name = table[pos + ENTRY_HEADER:pos + ENTRY_HEADER + name_length].decode("latin-1")
            for child in (right, left):
                if child not in NO_CHILD:
                    stack.append(child)
            data_offset = partition + sector * SECTOR
            if attributes & ATTR_DIRECTORY:
                entries.append(Entry(prefix + name, 0, True, data_offset))
                if length:
                    tables.append((data_offset, length, prefix + name + "/"))
            else:
                entries.append(Entry(prefix + name, length, False, data_offset))
    return entries


# --- XEX headers ---------------------------------------------------------------------------

def parse_xex(read, size):
    """Plaintext header fields of an XEX module. `read(offset, n)` reads the module."""
    info = {"anomalies": []}
    if size < XEX_FIXED_HEADER:
        info["error"] = "fichier trop court pour un en-tête XEX"
        return info
    magic, module_flags, header_size, _reserved, security_offset, count = \
        struct.unpack(">4sIIIII", read(0, XEX_FIXED_HEADER))
    printable = all(0x20 <= c < 0x7F for c in magic)
    info["magic"] = magic.decode("ascii") if printable else magic.hex().upper()
    if magic != XEX2_MAGIC:
        info["error"] = "pas un module XEX2"
        return info
    if not XEX_FIXED_HEADER + count * 8 <= header_size <= min(size, MAX_XEX_HEADER):
        info["error"] = f"taille d'en-tête incohérente ({header_size} octets)"
        return info
    header = read(0, header_size)
    info["file_size"] = size
    info["header_size"] = header_size
    info["module_flags"] = {"value": f"0x{module_flags:08X}",
                            "names": flag_names(module_flags, MODULE_FLAGS)}

    optional = {}
    for i in range(count):
        key, value = struct.unpack_from(">II", header, XEX_FIXED_HEADER + 8 * i)
        optional.setdefault(key, value)
    info["headers_present"] = [HEADER_NAMES.get(k, f"0x{k:08X}") for k in sorted(optional)]
    info["is_patch"] = KEY_DELTA_PATCH in optional

    def block(key):
        """Data of an optional header that is stored at an offset (low byte not 0 or 1)."""
        if key not in optional:
            return None
        offset = optional[key]
        if key & 0xFF == 0xFF:
            if offset + 4 > header_size:
                raise FormatError(f"{HEADER_NAMES[key]} is out of range")
            length = struct.unpack_from(">I", header, offset)[0]
        else:
            length = (key & 0xFF) * 4
        if length < 4 or offset + length > header_size:
            raise FormatError(f"{HEADER_NAMES[key]} is out of range")
        return header[offset:offset + length]

    def decode(name, function):
        try:
            value = function()
        except (FormatError, struct.error, IndexError) as e:
            info["anomalies"].append(f"{name} : {e}")
            return
        if value is not None:
            info[name] = value

    def execution_info():
        data = block(KEY_EXECUTION_INFO)
        if data is None:
            return None
        media_id, version, base_version, title_id = struct.unpack_from(">IIII", data)
        platform, executable_type, disc_number, disc_count = struct.unpack_from("4B", data, 16)
        savegame_id = struct.unpack_from(">I", data, 20)[0]
        return {"title_id": hex32(title_id), "media_id": hex32(media_id),
                "version": version_string(version),
                "base_version": version_string(base_version), "platform": platform,
                "executable_type": executable_type, "disc_number": disc_number,
                "disc_count": disc_count, "savegame_id": hex32(savegame_id)}

    def file_format():
        data = block(KEY_FILE_FORMAT)
        if data is None:
            return None
        _info_size, encryption, compression = struct.unpack_from(">IHH", data)
        return {"encryption_type": encryption,
                "encryption": ENCRYPTION_TYPES.get(encryption, "inconnu"),
                "encrypted": encryption != 0, "compression_type": compression,
                "compression": COMPRESSION_TYPES.get(compression, "inconnue")}

    def security_info():
        if security_offset + SEC_FIXED_SIZE > header_size:
            raise FormatError("security info is out of range")

        def u32(field):
            return struct.unpack_from(">I", header, security_offset + field)[0]
        image_flags, region, media = u32(SEC_IMAGE_FLAGS), u32(SEC_REGION), u32(SEC_MEDIA_TYPES)
        return {"image_size": u32(SEC_IMAGE_SIZE), "load_address": f"0x{u32(SEC_LOAD_ADDRESS):08X}",
                "image_flags": {"value": f"0x{image_flags:08X}",
                                "names": flag_names(image_flags, IMAGE_FLAGS)},
                "region": {"value": f"0x{region:08X}", "names": region_names(region)},
                "allowed_media": {"value": f"0x{media:08X}",
                                  "names": flag_names(media, MEDIA_FLAGS)}}

    def import_libraries():
        """Same reading as XEXImage::ReadImports in ReXGlue (src/filesystem/xex.cpp)."""
        data = block(KEY_IMPORT_LIBRARIES)
        if data is None:
            return None
        total = len(data)
        if total < 12:
            raise FormatError("import libraries are out of range")
        table_size, table_count = struct.unpack_from(">II", data, 4)
        if table_size + 12 > total:
            raise FormatError("import string table is out of range")
        strings = data[12:12 + table_size]
        names, i = [], 0
        while i < table_size and len(names) < table_count:
            end = strings.find(b"\0", i)
            length = (table_size if end < 0 else end) - i
            if length and strings[i] != 0xCD:
                names.append(strings[i:i + length].decode("latin-1"))
            i += max(length, 1)
            if i % 4:
                i += 4 - i % 4
        libraries, offset = [], table_size + 12
        for _ in range(table_count):
            if offset + 0x28 > total:
                raise FormatError("import library is out of range")
            library_size = struct.unpack_from(">I", data, offset)[0]
            version, version_min = struct.unpack_from(">II", data, offset + 0x1C)
            name_index, records = struct.unpack_from(">HH", data, offset + 0x24)
            if library_size < 0x28 or offset + library_size > total or \
                    0x28 + records * 4 > library_size:
                raise FormatError("import library is out of range")
            if name_index & 0xFF >= len(names):
                raise FormatError("import library names a missing string")
            libraries.append({"name": names[name_index & 0xFF],
                              "version": version_string(version),
                              "min_version": version_string(version_min)})
            offset += library_size
        return libraries

    def static_libraries():
        data = block(KEY_STATIC_LIBRARIES)
        if data is None:
            return None
        libraries = []
        for offset in range(4, len(data) - 15, 16):
            major, minor, build = struct.unpack_from(">HHH", data, offset + 8)
            approval, qfe = data[offset + 14], data[offset + 15]
            libraries.append({"name": ascii_z(data[offset:offset + 8]),
                              "version": f"{major}.{minor}.{build}.{qfe}",
                              "approval": APPROVAL_TYPES.get(approval, str(approval))})
        return libraries

    def original_pe_name():
        data = block(KEY_ORIGINAL_PE_NAME)
        return None if data is None else ascii_z(data[4:])

    def build_timestamp():
        data = block(KEY_CHECKSUM_TIMESTAMP)
        if data is None:
            return None
        timestamp = struct.unpack_from(">I", data, 4)[0]
        moment = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    def alternate_title_ids():
        data = block(KEY_ALTERNATE_TITLE_IDS)
        if data is None:
            return None
        return [hex32(v) for v in struct.unpack_from(f">{(len(data) - 4) // 4}I", data, 4)]

    def inline(key):
        return None if key not in optional else f"0x{optional[key]:08X}"

    decode("execution", execution_info)
    decode("file_format", file_format)
    decode("security", security_info)
    decode("import_libraries", import_libraries)
    decode("static_libraries", static_libraries)
    decode("original_pe_name", original_pe_name)
    decode("build_timestamp", build_timestamp)
    decode("alternate_title_ids", alternate_title_ids)
    decode("entry_point", lambda: inline(KEY_ENTRY_POINT))
    decode("image_base", lambda: inline(KEY_IMAGE_BASE))
    if KEY_SYSTEM_FLAGS in optional:
        flags = optional[KEY_SYSTEM_FLAGS]
        info["system_flags"] = {"value": f"0x{flags:08X}", "names": flag_names(flags, SYSTEM_FLAGS)}
    return info


# --- Report --------------------------------------------------------------------------------

def digests(read, size, crc=False, progress=None):
    sha256, sha1, crc32 = hashlib.sha256(), hashlib.sha1(), 0
    position = 0
    while position < size:
        data = read(position, min(CHUNK, size - position))
        sha256.update(data)
        sha1.update(data)
        if crc:
            crc32 = zlib.crc32(data, crc32)
        position += len(data)
        if progress:
            progress(position, size)
    result = {"sha256": sha256.hexdigest(), "sha1": sha1.hexdigest()}
    if crc:
        result["crc32"] = f"{crc32:08x}"
    return result


def top_level(entries):
    rows = {}
    for entry in entries:
        head, _, rest = entry.path.partition("/")
        row = rows.setdefault(head, {"name": head, "type": "file", "size": 0,
                                     "files": 0, "bytes": 0})
        if not rest:
            row["type"] = "directory" if entry.is_dir else "file"
            row["size"] = entry.size
        elif not entry.is_dir:
            row["files"] += 1
            row["bytes"] += entry.size
    result = []
    for row in sorted(rows.values(), key=lambda r: r["name"].lower()):
        if row["type"] == "file":
            result.append({"name": row["name"], "type": "file", "size": row["size"]})
        else:
            result.append({"name": row["name"], "type": "directory", "files": row["files"],
                           "bytes": row["bytes"]})
    return result


def redact(value, notes):
    """Remove any lone 128-bit hexadecimal token from the strings of the report."""
    if isinstance(value, dict):
        return {k: redact(v, notes) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, notes) for v in value]
    if isinstance(value, str) and HEX128_RE.search(value):
        notes.append(1)
        return HEX128_RE.sub(REDACTED, value)
    return value


def identify(source_path, image_hash=True, progress=None):
    """Build the report of a disc image file or of a folder holding an extracted disc."""
    anomalies = []
    report = {"tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
              "generated_at": datetime.datetime.now(datetime.timezone.utc)
              .strftime("%Y-%m-%dT%H:%M:%SZ")}
    source = Folder(source_path) if os.path.isdir(source_path) else DiscImage(source_path)
    try:
        if source.kind == "image":
            report["source"] = {"kind": "image", "size": source.size}
            if image_hash:
                report["source"].update(digests(source.read, source.size, crc=True,
                                                progress=progress))
            found = find_partition(source)
            if found is None:
                report["disc"] = None
                head = source.read(0, 4) if source.size >= 4 else b""
                if head in STFS_MAGICS:
                    anomalies.append(
                        "conteneur STFS (Games on Demand ?), pas une image de disque : "
                        "l'extraire dans le dossier privé avec `rexglue vfs dump`, puis "
                        "relancer l'outil sur ce dossier")
                else:
                    anomalies.append("aucun volume XDVDFS reconnu dans l'image")
                entries = []
            else:
                partition, label = found
                try:
                    entries = walk_xdvdfs(source, partition, anomalies)
                except FormatError as e:
                    anomalies.append(f"volume XDVDFS illisible : {e}")
                    entries = []
                outside = [e.path for e in entries
                           if not e.is_dir and e.offset + e.size > source.size]
                report["disc"] = {"layout": label, "partition_offset": f"0x{partition:08X}",
                                  "files_outside_image": len(outside),
                                  "files_outside_image_sample": sorted(outside)[:20]}
        else:
            entries = source.entries(anomalies)
            report["source"] = {"kind": "folder",
                                "size": sum(e.size for e in entries if not e.is_dir)}
            report["disc"] = {"layout": "dossier extrait"}

        entries.sort(key=lambda e: e.path.lower())
        files = [e for e in entries if not e.is_dir]
        if report["disc"] is not None:
            report["disc"].update({"files": len(files),
                                   "directories": len(entries) - len(files),
                                   "bytes": sum(e.size for e in files),
                                   "top_level": top_level(entries)})

        modules = []
        xex_files = [e for e in files if e.path.lower().endswith(".xex")]
        xex_files.sort(key=lambda e: (e.path.lower() != "default.xex", e.path.lower()))
        for entry in xex_files:
            module = {"path": entry.path, "size": entry.size}
            key = entry.path.lower()
            try:
                read = source.reader(entry)
                module.update(digests(read, entry.size))
                module["header"] = parse_xex(read, entry.size)
            except (FormatError, OSError) as e:
                module["error"] = str(e)
            if key in PROJECT_A_SHA256:
                module["project_a_reference"] = (
                    "absent" if "sha256" not in module else
                    "identique" if module["sha256"] == PROJECT_A_SHA256[key] else "différente")
            modules.append(module)
            for anomaly in module.get("header", {}).get("anomalies", []):
                anomalies.append(f"`{entry.path}` : {anomaly}")
        report["modules"] = modules
    finally:
        source.close()

    by_path = {m["path"].lower(): m for m in report["modules"]}
    default = by_path.get("default.xex", {})
    execution = default.get("header", {}).get("execution")
    title_id = execution["title_id"] if execution else None
    project_a = {name: by_path.get(name, {}).get("project_a_reference", "absent")
                 for name in PROJECT_A_SHA256}
    identified = execution is not None
    if not default:
        anomalies.append("default.xex absent de la racine")
    elif not identified:
        anomalies.append("en-tête de default.xex illisible ou sans ExecutionInfo")
    report["verdict"] = {
        "identified": identified,
        "title_id": title_id,
        "title_id_expected": hex32(TITLE_ID_EXPECTED),
        "title_id_matches": title_id == hex32(TITLE_ID_EXPECTED),
        "project_a_europe_disc": all(v == "identique" for v in project_a.values()),
        "project_a_modules": project_a,
        "encrypted_modules": [m["path"] for m in report["modules"]
                              if m.get("header", {}).get("file_format", {}).get("encrypted")],
    }
    report["anomalies"] = anomalies
    notes = []
    report = redact(report, notes)
    if notes:
        report["anomalies"].append(
            f"{len(notes)} valeur(s) contenai(en)t un jeton hexadécimal de 128 bits, masqué")
    return report


def number(n):
    return f"{n:,}".replace(",", " ")


def yes_no(flag):
    return "oui" if flag else "non"


def flags_cell(field):
    names = ", ".join(field["names"]) or "aucun"
    return f"`{field['value']}` : {names}"


def render_markdown(report):
    lines = []
    add = lines.append
    verdict = report["verdict"]
    add("# Identification de l'image du disque (J0)")
    add("")
    add(f"> Rapport produit localement par `tools/iso_identify.py` (version "
        f"{report['tool']['version']}), le {report['generated_at']}, en lecture seule.")
    add("> Aucun déchiffrement, aucune extraction. Les octets des modules XEX sont lus pour")
    add("> leurs empreintes et leurs en-têtes sont chargés en mémoire ; leurs champs de clé et")
    add("> de signature (clé AES chiffrée, clé LAN, identifiant de média de 128 bits,")
    add("> signature RSA) n'en sont ni extraits ni écrits ici. Contenu : empreintes, noms et")
    add("> tailles de fichiers, champs d'en-tête en clair (autorisés par D-007).")
    add("")
    add("## Verdict")
    add("")
    add("| Question | Réponse |")
    add("|---|---|")
    add(f"| Identification | {'complète' if verdict['identified'] else 'incomplète (voir anomalies)'} |")
    add(f"| Identifiant du titre `{verdict['title_id_expected']}` (attendu) | "
        f"{yes_no(verdict['title_id_matches'])} (lu : `{verdict['title_id'] or '—'}`) |")
    detail = ", ".join(f"`{k}` {v}" for k, v in verdict["project_a_modules"].items())
    add(f"| Disque Europe (En, Es, Nl) du projet A | "
        f"{yes_no(verdict['project_a_europe_disc'])} ({detail}) |")
    encrypted = ", ".join(f"`{p}`" for p in verdict["encrypted_modules"]) or "aucun"
    add(f"| Modules chiffrés d'après leur en-tête (D-008) | {encrypted} |")
    add("")

    source, disc = report["source"], report["disc"]
    add("## Image" if source["kind"] == "image" else "## Dossier extrait")
    add("")
    add("| Champ | Valeur |")
    add("|---|---|")
    add(f"| Taille | {number(source['size'])} octets |")
    for name, label in (("sha256", "SHA-256"), ("sha1", "SHA-1"), ("crc32", "CRC32")):
        if name in source:
            add(f"| {label} | `{source[name]}` |")
    if source["kind"] == "image" and "sha256" not in source:
        add("| Empreintes de l'image | non calculées (`--no-image-hash`) |")
    if disc is not None:
        add(f"| Format | {disc['layout']}"
            + (f" (partition de jeu à `{disc['partition_offset']}`)" if "partition_offset" in disc else "")
            + " |")
        add(f"| Arborescence | {number(disc['files'])} fichiers, {number(disc['directories'])} "
            f"dossiers, {number(disc['bytes'])} octets |")
        if "files_outside_image" in disc:
            add(f"| Fichiers au-delà de la fin de l'image | {disc['files_outside_image']} |")
        add("")
        add("### Racine")
        add("")
        add("| Nom | Type | Taille |")
        add("|---|---|---|")
        for row in disc["top_level"]:
            if row["type"] == "file":
                add(f"| `{row['name']}` | fichier | {number(row['size'])} octets |")
            else:
                add(f"| `{row['name']}` | dossier | {number(row['files'])} fichiers, "
                    f"{number(row['bytes'])} octets |")
    add("")

    add("## Modules XEX")
    add("")
    if not report["modules"]:
        add("Aucun fichier `.xex`.")
        add("")
    for module in report["modules"]:
        add(f"### `{module['path']}`")
        add("")
        add("| Champ | Valeur |")
        add("|---|---|")
        add(f"| Taille | {number(module['size'])} octets |")
        if "sha256" in module:
            add(f"| SHA-256 | `{module['sha256']}` |")
            add(f"| SHA-1 | `{module['sha1']}` |")
        if "project_a_reference" in module:
            add(f"| Empreinte du projet A (disque Europe) | {module['project_a_reference']} |")
        if "error" in module:
            add(f"| Erreur de lecture | {module['error']} |")
            add("")
            continue
        header = module["header"]
        add(f"| Magie | `{header.get('magic', '—')}` |")
        if "error" in header:
            add(f"| En-tête | {header['error']} |")
            add("")
            continue
        execution = header.get("execution")
        if execution:
            add(f"| Identifiant du titre | `{execution['title_id']}` |")
            add(f"| Identifiant du média | `{execution['media_id']}` |")
            add(f"| Version (version de base) | {execution['version']} ({execution['base_version']}) |")
            add(f"| Disque | {execution['disc_number']} sur {execution['disc_count']} |")
            add(f"| Plateforme, type d'exécutable | {execution['platform']}, "
                f"{execution['executable_type']} |")
            add(f"| Identifiant de sauvegarde | `{execution['savegame_id']}` |")
        file_format = header.get("file_format")
        if file_format:
            add(f"| Chiffrement | {file_format['encryption']}, type {file_format['encryption_type']} |")
            add(f"| Compression | {file_format['compression']}, type {file_format['compression_type']} |")
        security = header.get("security")
        if security:
            add(f"| Régions | `{security['region']['value']}` : "
                f"{', '.join(security['region']['names']) or 'aucune'} |")
            add(f"| Médias autorisés | {flags_cell(security['allowed_media'])} |")
            add(f"| Drapeaux de l'image | {flags_cell(security['image_flags'])} |")
            add(f"| Adresse de chargement | `{security['load_address']}` |")
            add(f"| Taille de l'image chargée | {number(security['image_size'])} octets |")
        add(f"| Drapeaux du module | {flags_cell(header['module_flags'])} |")
        if "system_flags" in header:
            add(f"| Drapeaux système | {flags_cell(header['system_flags'])} |")
        for key, label in (("entry_point", "Point d'entrée"), ("image_base", "Base de l'image")):
            if key in header:
                add(f"| {label} | `{header[key]}` |")
        if "original_pe_name" in header:
            add(f"| Nom PE d'origine | `{header['original_pe_name']}` |")
        if "build_timestamp" in header:
            add(f"| Horodatage de l'édition de liens | {header['build_timestamp']} |")
        if "alternate_title_ids" in header:
            add(f"| Identifiants de titre alternatifs | "
                f"{', '.join(f'`{t}`' for t in header['alternate_title_ids']) or 'aucun'} |")
        add(f"| Module correctif (delta) | {yes_no(header['is_patch'])} |")
        add(f"| En-têtes optionnels présents | {', '.join(header['headers_present'])} |")
        add("")
        if header.get("import_libraries"):
            add("Bibliothèques importées :")
            add("")
            add("| Bibliothèque | Version | Version minimale |")
            add("|---|---|---|")
            for library in header["import_libraries"]:
                add(f"| `{library['name']}` | {library['version']} | {library['min_version']} |")
            add("")
        if header.get("static_libraries"):
            add("Bibliothèques statiques :")
            add("")
            add("| Bibliothèque | Version | Approbation |")
            add("|---|---|---|")
            for library in header["static_libraries"]:
                add(f"| `{library['name']}` | {library['version']} | {library['approval']} |")
            add("")

    add("## Anomalies")
    add("")
    if report["anomalies"]:
        for anomaly in report["anomalies"]:
            add(f"- {anomaly}")
    else:
        add("Aucune.")
    add("")
    return "\n".join(lines)


def render_json(report):
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def check_shareable(text):
    """Last line of defence: a report never holds a lone 128-bit hexadecimal token."""
    if HEX128_RE.search(text):
        raise RuntimeError("internal error: a 128-bit token reached the report")


# --- Output safety (P-18) ------------------------------------------------------------------

def file_id(st):
    return (st.st_dev, st.st_ino)


def protected_ids(source):
    """Identity (device, inode) of the source and, for a folder, of everything under it.
    A report must never be one of these files or folders, whatever path names it: an
    alias, a symbolic link and a hard link all lead to the same identity."""
    ids = {file_id(os.stat(source))}
    if os.path.isdir(source):
        for dirpath, dirnames, filenames in os.walk(source):
            for name in dirnames + filenames:
                try:
                    ids.add(file_id(os.stat(os.path.join(dirpath, name))))
                except OSError:
                    pass  # dangling link: nothing to protect behind it
    return ids


def output_problem(output, protected):
    """Why the report must not be written to `output`, or None."""
    resolved = os.path.realpath(output)
    if in_nix_store(resolved):
        return "it is in /nix/store"
    if os.path.isdir(resolved):
        return "it is a folder"
    if os.path.exists(output) and file_id(os.stat(output)) in protected:
        return "it is the source itself, or a file of the source folder, under another name"
    folder = os.path.dirname(resolved)
    while True:
        try:
            if file_id(os.stat(folder)) in protected:
                return "it is inside the source folder"
        except OSError:
            pass  # a folder that does not exist yet cannot be the source
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def same_output(a, b):
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)


def check_outputs(outputs, protected):
    """Error messages for the report paths; empty when every path is safe."""
    problems = []
    for output in outputs:
        problem = output_problem(output, protected)
        if problem:
            problems.append(f"refusing to write the report to {output}: {problem}")
    if len(outputs) == 2 and same_output(*outputs):
        problems.append("--json and --markdown name the same file")
    return problems


def stdout_is_protected(protected):
    try:
        st = os.fstat(sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        return False
    return file_id(st) in protected


def write_report(path, text, protected):
    """Write to a new temporary file next to `path`, then rename it onto `path`. The
    rename replaces the directory entry: a symbolic or hard link at `path` is replaced,
    and the file it led to is never opened for writing."""
    problems = check_outputs([path], protected)  # again, just before writing
    if problems:
        raise OSError(problems[0])
    directory = os.path.dirname(os.path.abspath(path))
    fd, temporary = tempfile.mkstemp(prefix=".iso-identify-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main(argv):
    parser = argparse.ArgumentParser(
        prog="iso-identify", description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("source", help="disc image file, or folder holding the extracted disc")
    parser.add_argument("--no-image-hash", action="store_true",
                        help="skip the SHA-256, SHA-1 and CRC32 of the whole image")
    parser.add_argument("--json", metavar="FILE", help="also write the report as JSON")
    parser.add_argument("--markdown", metavar="FILE", help="also write the Markdown report")
    args = parser.parse_args(argv[1:])

    if not os.path.exists(args.source):
        print(f"error: {args.source} does not exist", file=sys.stderr)
        return 2
    if in_nix_store(args.source):
        print(f"error: {args.source} is in /nix/store, readable by every user of the "
              "machine and pushable to a binary cache (D-007). Remove it from the store "
              "with `nix-store --delete` and keep the disc in the private folder.",
              file=sys.stderr)
        return 2

    # Every check on the report paths runs before the source is read (P-18).
    protected = protected_ids(args.source)
    outputs = [path for path in (args.json, args.markdown) if path]
    problems = check_outputs(outputs, protected)
    if stdout_is_protected(protected):
        problems.append("the standard output is the source itself, or a file of the source "
                        "folder; use --markdown instead of a shell redirection")
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2

    progress = None
    if sys.stderr.isatty():
        def progress(done, total):
            print(f"\rhashing the image: {100 * done // total:3d} %", end="", file=sys.stderr)
            if done == total:
                print(file=sys.stderr)
    try:
        report = identify(args.source, image_hash=not args.no_image_hash, progress=progress)
    except (OSError, FormatError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    markdown = render_markdown(report)
    as_json = render_json(report)
    try:
        check_shareable(markdown)
        check_shareable(as_json)
    except RuntimeError as e:
        print(f"error: {e}; no report written", file=sys.stderr)
        return 2
    try:
        for output, text in ((args.json, as_json), (args.markdown, markdown)):
            if output:
                write_report(output, text, protected)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(markdown)
    return 0 if report["verdict"]["identified"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))

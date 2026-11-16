# -*- coding: utf-8 -*-
"""
Rose's own repair of one flaw LTK Manager's rules name and do not repair: a number
stored wider than the game reads.

Riot sometimes narrows a number property (StaticMaterialDef.type: 32 bits until patch
16.17, 8 bits since 16.18). A mod built before still stores the wide form, the game
drops the value, and LTK Manager's rule bin/property-type calls the mod unrepairable:
its repair only moves a number to a wider type, never to a narrower one, whatever the
number is (ltk-manager-problems v1.33.0). When the number itself fits the narrow type
nothing is lost, so Rose stores it the way the game reads it. A number that does not
fit is left alone, and LTK Manager's verdict on it stands.

This is Rose's own code on Rose's own bin and WAD readers; nothing of LTK Manager's is
in it. The list of narrowed properties is read off the game's type data.

First seen Nov 16, 2026: Travis Scott Zeri, 55 materials with `type: u32 = 3`. After
the repair LTK Manager's own rules call the mod healthy.
"""

import os
import uuid
import zipfile
from pathlib import Path
from typing import Tuple

from injection.baseskin import propbin
from injection.baseskin.wad import ModWad
from injection.tools.mod_checker import REPAIRABLE_SUFFIXES, REPAIR_TEMP_PREFIX
from utils.core.logging import get_logger

log = get_logger()

# (class, property) -> the type the game reads now. Every number property the game has narrowed up to
# patch 16.22, from LTK Manager's schema data (a class is listed with the classes that inherit from it).
# shortcut: a fixed list, so a number Riot narrows later is not repaired until its row is added here; LTK
# Manager's message "Meta property type mismatch" on a mod is the sign.
NARROWED = {
    (0xFF9D3409, 0x5127F14D): propbin.U8,   # StaticMaterialDef.type, patch 16.18
    (0x9B67E9F6, 0x2D790B62): propbin.U8,   # SkinCharacterDataProperties, two properties, patch 16.8
    (0x9B67E9F6, 0x46558F0E): propbin.U8,
    (0x56767442, 0x2D790B62): propbin.U8,   # TftSkinCharacterDataProperties inherits them
    (0x56767442, 0x46558F0E): propbin.U8,
    (0x92C8C778, 0x28C538E1): propbin.U16,  # a font's fontSize, patch 15.22
    (0x92C8C778, 0x2BF77ED0): propbin.U8,   # a font's FontWeight, patch 15.22
    (0xBB778E9B, 0x50A09EB9): propbin.U8,   # WEIGHT, patch 15.22
    (0x3B8D8B3F, 0x13BDDC7B): propbin.U32,  # itemID, patch 16.21
    (0x665C9FE7, 0xF3CA8ECE): propbin.U16,  # PhysicsSimGlobalSettings.ConstraintIterations, patch 16.7
    (0xBB109C9B, 0x0B860061): propbin.U8,   # AugmentSelectionViewController.MaxAugmentSlots, patch 16.7
}
_INTS = {propbin.I8: (1, True), propbin.U8: (1, False), propbin.I16: (2, True), propbin.U16: (2, False),
         propbin.I32: (4, True), propbin.U32: (4, False), propbin.I64: (8, True), propbin.U64: (8, False)}  # size, signed
_CLASSES = {owner for owner, _name in NARROWED}
# A class shows in a file's bytes as its hash: a file or an entry without one has nothing to narrow
_CLASS_BYTES = [owner.to_bytes(4, "little") for owner in _CLASSES]
_BIN_MAGICS = (b"PROP", b"PTCH")


def _narrow_fields(owner: int, fields) -> int:
    fixed = 0
    for field in fields:
        value, target = field.value, NARROWED.get((owner, field.name_hash))
        if target is not None and value.ty in _INTS and _INTS[value.ty][0] > _INTS[target][0]:
            number = int.from_bytes(value.v, "little", signed=_INTS[value.ty][1])
            size, signed = _INTS[target]
            if (-(1 << (8 * size - 1)) if signed else 0) <= number < (1 << (8 * size - (1 if signed else 0))):
                field.value = propbin.Value(target, number.to_bytes(size, "little", signed=signed))
                fixed += 1
        fixed += _narrow_value(field.value)
    return fixed


def _narrow_value(value) -> int:
    if value.ty in (propbin.POINTER, propbin.EMBED):
        return _narrow_fields(value.v.name_hash, value.v.fields) if value.v is not None else 0
    if value.ty in (propbin.LIST, propbin.LIST2):
        return sum(_narrow_value(item) for item in value.v)
    if value.ty == propbin.OPTION:
        return _narrow_value(value.v) if value.v is not None else 0
    if value.ty == propbin.MAP:
        return sum(_narrow_value(key) + _narrow_value(item) for key, item in value.v)
    return 0


def narrow_bin(data: bytes) -> Tuple[bytes, int]:
    """A bin file with its narrowed numbers stored as the game reads them, and how many were rewritten.
    The same bytes and 0 when there is nothing to do. Raises propbin.PropError on a file it cannot read."""
    if not any(mark in data for mark in _CLASS_BYTES):
        return data, 0
    parsed = propbin.Bin(data)
    fixed = 0
    # Bin's own find_entry reads the first entry of a type only, and an entry it has read is written back
    # from its values. So the entries are read here, and only one that changed is handed to Bin to write:
    # every other entry keeps its bytes. (propbin.py is the original project's file and stays as it is.)
    for index, (start, end) in enumerate(parsed._locate()):
        owner, body = parsed.types[index], data[start + 4:end]
        if owner not in _CLASSES and not any(mark in body for mark in _CLASS_BYTES):
            continue
        reader = propbin._Reader(body)
        entry = propbin.Entry(owner, reader.u32(), reader.fields(owner))
        count = _narrow_fields(owner, entry.fields)
        if count:
            parsed._parsed[index] = entry
            fixed += count
    return (parsed.write(), fixed) if fixed else (data, 0)


def _narrow_wad(data: bytes) -> Tuple[bytes, int]:
    wad = ModWad(data)
    fixed = 0
    for file in list(wad):
        raw = file.data
        if raw[:4] in _BIN_MAGICS:
            fresh, count = narrow_bin(raw)
            if count:
                wad.put(file.name_hash, fresh)
                fixed += count
    return (wad.to_bytes(), fixed) if fixed else (data, 0)


def _narrowed(source: zipfile.ZipFile):
    """(entry, its bytes with the numbers narrowed, how many were) for each entry of a mod archive"""
    for info in source.infolist():
        data = source.read(info)
        count = 0
        if info.filename.lower().endswith((".wad.client", ".wad")):
            data, count = _narrow_wad(data)
        elif data[:4] in _BIN_MAGICS:  # a bin of a mod kept as loose files
            data, count = narrow_bin(data)
        yield info, data, count


def narrowable(archive: Path) -> int:
    """How many numbers repair_archive would rewrite in this mod, without writing anything.
    0 also for a kind of file it does not repair and for one it cannot read."""
    archive = Path(archive)
    if archive.suffix.lower() not in REPAIRABLE_SUFFIXES:
        return 0
    try:
        with zipfile.ZipFile(archive) as source:
            return sum(count for _info, _data, count in _narrowed(source))
    except (OSError, ValueError, zipfile.BadZipFile):  # PropError and WadError are ValueErrors
        return 0


def repair_archive(archive: Path) -> int:
    """Store the narrowed numbers of one .fantome (or .zip) as the game reads them. Returns how many were
    rewritten; 0 leaves the file untouched (nothing to do, a kind of file this does not repair, or a file
    it cannot read: said in the log, never raised).

    The repaired copy is written beside the mod under the name mod_checker's repair uses and takes the
    mod's place in one rename, so the mod is never half written.
    """
    archive = Path(archive)
    if archive.suffix.lower() not in REPAIRABLE_SUFFIXES:
        return 0
    copy = archive.with_name(f"{REPAIR_TEMP_PREFIX}{uuid.uuid4().hex}.tmp")
    fixed = 0
    try:
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(copy, "w") as out:
            for info, data, count in _narrowed(source):
                fixed += count
                out.writestr(info, data)  # the entry's own name, date and compression
        if fixed:
            os.replace(copy, archive)
        return fixed
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        log.warning(f"[MODCHECK] Could not store the numbers of {archive.name} as the game reads them: {e}")
        return 0
    finally:
        copy.unlink(missing_ok=True)

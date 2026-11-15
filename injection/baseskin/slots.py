#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A skin under every other slot of its champion: what lets another player's champion show a skin the
user picked for them (injection/core/other_skins.py).

A skin Rose plays is written for slot 0 (skin0.bin, the base skin): the user's own champion is forced onto the
base skin, so that is the file the game reads. Another player keeps the skin they chose, and for them the game
reads skin<N>.bin. So the mod's skin0.bin is written again, small, under each other slot the champion has:
its skin entry and resource list under that slot's names, and a link to the bin they came from for everything
else they point at. It is how the skins Rose ships are built (two entries and a link to the skin's own bin),
with N in place of 0.

What names a slot, checked against the game's own files (Nov 14): skin<N>.bin holds the entry
Characters/<X>/Skins/Skin<N> and its Characters/<X>/Skins/Skin<N>/Resources; the entry links that resource
list (mResourceResolver) and repeats its own name in one field. A name that is another slot's (a shipped skin
keeps the names of the skin it shows) is left alone.

Never seen in a game: see docs/other-players-skins.md.
"""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional

from utils.core.logging import get_logger

from . import audio
from .package import WAD_SUFFIX, _Mod, character_names, split_wad_name
from .propbin import HASH, LINK, Bin, PropError, Value, build, fnv1a_lower
from .wad import GameWad, WadError, path_hash

log = get_logger()

SKIN_CLASS = audio.SKIN_DATA_CLASS
RESOURCES_CLASS = fnv1a_lower("ResourceResolver")
PROP_RESOURCES = fnv1a_lower("mResourceResolver")
PROP_OWN_NAME = 0x1D369C29  # the field of a skin entry that repeats the entry's name (its own name is in no hash list)
MAX_SLOTS = 1000  # a skin's id is its champion's id * 1000 + its slot


class BaseBin(NamedTuple):
    """A character's skin0.bin, and the champion WAD (its name without .wad.client) it belongs to."""
    stem: str
    character: str
    data: bytes


def skin_bin_path(character: str, slot: int) -> str:
    return f"data/characters/{character}/skins/skin{slot}.bin".lower()


def _names(character: str, slot: int) -> tuple:
    name = f"Characters/{character}/Skins/Skin{slot}"
    return fnv1a_lower(name), fnv1a_lower(f"{name}/Resources")


def _value_naming(entry, field_name: int, value_type: int, name: int) -> Optional[Value]:
    """The entry's field when it has this type and holds this name."""
    field = entry.find_field(field_name)
    if field is not None and field.value.ty == value_type and field.value.v == struct.pack("<I", name):
        return field.value
    return None


def slot_copies(data: bytes, character: str, targets: Iterable[int], source: int = 0) -> Dict[int, bytes]:
    """{slot: the skin of the bin *data* (written for slot *source* of *character*) as that slot reads it}.

    {} when the bin holds no skin of that slot, or does not read: nothing is then written for the champion,
    and the player keeps their own skin."""
    old_skin, old_resources = _names(character, source)
    try:
        file = Bin(data)
        skin = file.find_entry(SKIN_CLASS)
        if skin is None or skin.path_hash != old_skin:
            return {}
        entries = [skin]
        resources = file.find_entry(RESOURCES_CLASS)
        if resources is not None and resources.path_hash == old_resources:
            entries.append(resources)
        else:
            resources = None
        own_name = _value_naming(skin, PROP_OWN_NAME, HASH, old_skin)
        link = _value_naming(skin, PROP_RESOURCES, LINK, old_resources) if resources is not None else None
        # Everything else the entry points at (materials, particles, animations) is in the bin it came from
        # and the bins that one links: a bin of only these entries already links what it needs
        linked = list(file.linked)
        if len(file.types) > len(entries):
            linked = [f"DATA/Characters/{character}/Skins/Skin{source}.bin"]
        copies = {}
        for slot in targets:
            new_skin, new_resources = _names(character, slot)
            skin.path_hash = new_skin
            if own_name is not None:
                own_name.v = struct.pack("<I", new_skin)
            if resources is not None:
                resources.path_hash = new_resources
            if link is not None:
                link.v = struct.pack("<I", new_resources)
            copies[slot] = build(entries, file.version, linked)
        return copies
    except (PropError, struct.error) as e:
        log.info(f"[OTHERS] {character}'s skin does not read ({e}): it is not put on other slots")
        return {}


def game_wad(game_dir: Path, stem: str) -> Optional[GameWad]:
    """The game's own WAD of a champion (None when it is not there or does not read)."""
    try:
        return GameWad(Path(game_dir) / "DATA" / "FINAL" / "Champions" / f"{stem}{WAD_SUFFIX}")
    except (OSError, WadError):
        return None


def slots(wad: GameWad, character: str) -> List[int]:
    """The skin slots the game has for a character: its skins and their chromas."""
    return [slot for slot in range(MAX_SLOTS) if wad.has_path(skin_bin_path(character, slot))]


def mod_base_bins(mod_path: Path) -> List[BaseBin]:
    """The skin0.bin of each character a mod (an archive or a folder) gives a base skin, from its packed
    champion WADs; [] when it has none Rose can read (an unpacked WAD folder is not read, as in package.py)."""
    found: List[BaseBin] = []
    try:
        with _Mod(Path(mod_path)) as mod:
            for name in mod.names():
                parts = name.split("/")
                split = split_wad_name(parts[1]) if len(parts) == 2 and audio.same(parts[0], "WAD") else None
                if split is None or split[1] is not None:
                    continue  # not a WAD file, or a voice-over WAD
                wad = mod.wad(name)
                if wad is None:
                    continue
                for character in character_names(split[0]):
                    file = wad.get(path_hash(skin_bin_path(character, 0)))
                    if file is not None:
                        found.append(BaseBin(split[0], character, file.data))
    except (OSError, ValueError, zipfile.BadZipFile) as e:  # ValueError: a WAD (or a .modpkg) that does not read
        log.info(f"[OTHERS] {Path(mod_path).name} does not read ({e}): it is not put on other slots")
        return []
    return found


def game_base_bins(game_dir: Path, stem: str) -> List[BaseBin]:
    """The game's own skin0.bin of each character of a champion: the default look."""
    wad = game_wad(game_dir, stem)
    if wad is None:
        return []
    found = []
    for character in character_names(stem):
        try:
            data = wad.read_path(skin_bin_path(character, 0))
        except (OSError, WadError):
            data = None
        if data:
            found.append(BaseBin(stem, character, data))
    return found


def write_mod(game_dir: Path, target: Path, bins: List[BaseBin], skip: Iterable[int] = (), note: str = "") -> int:
    """Write the mod folder *target*: each base bin under every slot the game has for its character, but
    slot 0 (the bin's own) and *skip* (the slot of the skin a shipped skin shows: its bin is the one the copies
    link). Returns how many files were written; 0 leaves no folder."""
    skip = {0, *skip}
    target = Path(target)
    written = 0
    for stem, character, data in bins:
        wad = game_wad(game_dir, stem)
        if wad is None:
            continue
        copies = slot_copies(data, character, [slot for slot in slots(wad, character) if slot not in skip])
        for slot, copy in copies.items():
            file = target / "RAW" / skin_bin_path(character, slot)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(copy)
            written += 1
    if written:
        (target / "META").mkdir(parents=True, exist_ok=True)
        info = {"Author": "Rose", "Description": note, "Name": "Another player's skin", "Version": "1.0.0"}
        (target / "META" / "info.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return written

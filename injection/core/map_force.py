# -*- coding: utf-8 -*-
"""
A custom map under a season's map (the winter map): the season's files, with the standard
map drawn. AN EXPERIMENT, off unless this PC asks for it (mode()).

The game's map11.bin lists "map skins" (Default, Milkshake_SRS: winter, URF...), and the
server names the one a game loads. Each links a map container: Default links
Maps/MapGeometry/Map11/Base_SRX, the map every custom map is made for; the winter skin
links its own. Since patch 16.23 (Nov 18, 2026) every game is told to load the winter skin,
so no custom map shows.

A container is two files, <name>.mapgeo (what is drawn) and <name>.materials.bin (the
materials the geometry names, and the container itself with the map's placed objects: the
shops, and on the winter map a train). The server runs a winter game and names those
objects, so the winter container has to stay.

First try, Nov 18-19: link the winter skin to the standard container. The game quit the
moment it spawned the world, in every game: the standard container lacks the winter
objects. Dropped.

This try: leave the skin and the container alone and give the game, under the winter
container's file names,
- the standard map's geometry (the game's own base_srx.mapgeo, copied as it is stored), and
- the winter materials file plus the standard map's materials it lacks (on patch 16.23: 28
  of 192; the other 164 are in the winter file already, byte for byte).
The winter container, with every placed object, is untouched. Winter's decorations (snow,
lights) are placed objects too, so they still show, on the standard map.

Which season: the map skin the newest game log of this PC names. Only a skin with Default's
objects file and navigation grid and another container is ported.

Not ported in this version: a mod that says itself which map loads (its own declared edits
or map11.bin), and a mod that ships map geometry or map materials of its own.

Nothing but a game shows whether the game takes it. Until one has, it is made only when this
PC asks (mode()), and then only for a Practice Tool game.
"""

import json
import re
import shutil
import struct
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from injection.baseskin import propbin
from injection.baseskin.wad import FileSource, GameWad, ModWad, path_hash
from injection.mods.mod_files import ModFiles
from utils.core.logging import get_logger

log = get_logger()

FOLDER = "rose_map_force"
MAP_WAD = Path("DATA") / "FINAL" / "Maps" / "Shipping" / "Map11.wad.client"
MAP_BIN = "data/maps/shipping/map11/map11.bin"
SKIN_PREFIX = "Maps/Shipping/Map11/MapSkins/"
DEFAULT = "Default"
# This PC's switch: one word, "practice" (made for Practice Tool games only) or "on" (for every game).
# The file is in .git, which is never published and which an installed copy does not have: off there.
MODE_FILE = Path(__file__).resolve().parents[2] / ".git" / "rose-map-port.txt"
LOGS_LOOKED_AT = 10  # game logs read, newest first, for the last map skin of Summoner's Rift
_CONTAINER = propbin.fnv1a_lower("mMapContainerLink")
_NAME = propbin.fnv1a_lower("name")
_OBJECTS = propbin.fnv1a_lower("mMapObjectsCFG")
_NAV_GRID = 0x63242493  # the navigation grid file (the property's name is not known)
_MATERIAL = propbin.STATIC_MATERIAL_DEF
_EMPTY_WAD = b"RW\x03\x04" + bytes(264) + struct.pack("<I", 0)
_WAD_SUFFIX = ".wad.client"
_MAP_SKIN_LINE = re.compile(rb"mapskin = ([A-Za-z0-9_]+)")


class MapSkin(NamedTuple):
    name: str
    container: str    # "Maps/MapGeometry/Map11/Base_SRX"
    playfield: tuple  # (objects file, navigation grid)


def geometry_file(container: str) -> str:
    """The geometry file of a container: Maps/MapGeometry/Map11/Base_SRX -> data/.../base_srx.mapgeo"""
    return f"data/{container.lower()}.mapgeo"


def materials_file(container: str) -> str:
    """The materials file of a container, which also holds the container and its placed objects"""
    return f"data/{container.lower()}.materials.bin"


def _entries(data: bytes) -> Tuple[propbin.Bin, List[Tuple[int, int, bytes]]]:
    """A bin file and its entries as (class, name hash, the entry's bytes), in file order"""
    parsed = propbin.Bin(data)
    return parsed, [(parsed.types[index], struct.unpack_from("<I", data, start + 4)[0], data[start:end])
                    for index, (start, end) in enumerate(parsed._locate())]


def map_skins(data: bytes) -> List[MapSkin]:
    """The map skins of a map11.bin. Raises propbin.PropError on a file it cannot read."""
    mark = _CONTAINER.to_bytes(4, "little")
    skins = []
    for owner, _name_hash, raw in _entries(data)[1]:
        if mark not in raw:
            continue
        reader = propbin._Reader(raw[8:])
        strings = {field.name_hash: field.value.v for field in reader.fields(owner) if field.value.ty == propbin.STRING}
        if strings.get(_NAME) and strings.get(_CONTAINER):
            skins.append(MapSkin(strings[_NAME], strings[_CONTAINER], (strings.get(_OBJECTS), strings.get(_NAV_GRID))))
    return skins


def merge_materials(season: bytes, standard: bytes) -> Tuple[bytes, int]:
    """The season's materials file with the standard map's materials it lacks (or has otherwise), and how
    many those are. Entries are moved as bytes, none is read and written again: every entry of the season's
    file that is not a replaced material is byte for byte what it was. Raises propbin.PropError on a file it
    cannot read or that is not a plain PROP file of the season file's version."""
    if season[:4] != b"PROP" or standard[:4] != b"PROP":
        raise propbin.PropError("a materials file that is not a plain PROP file")
    parsed, entries = _entries(season)
    other, wanted = _entries(standard)
    if parsed.version != other.version:
        raise propbin.PropError("the two materials files are of different versions")
    at = {name_hash: index for index, (_owner, name_hash, _raw) in enumerate(entries)}
    added = 0
    for owner, name_hash, raw in wanted:
        if owner != _MATERIAL:
            continue
        if name_hash not in at:
            at[name_hash] = len(entries)
            entries.append((owner, name_hash, raw))
            added += 1
        elif entries[at[name_hash]][2] != raw:
            entries[at[name_hash]] = (owner, name_hash, raw)
            added += 1
    if not added:
        return season, 0
    count_at = parsed._head_end - 4 * len(parsed.types) - 4  # the header up to the number of entries stays
    return (season[:count_at] + struct.pack("<I", len(entries))
            + b"".join(struct.pack("<I", owner) for owner, _name_hash, _raw in entries)
            + b"".join(raw for _owner, _name_hash, raw in entries)), added


class ModView(NamedTuple):
    ships: Callable[[str], bool]  # whether the mod ships a game file, by the file's path
    map_bin: bool                 # whether it ships a map11.bin of its own


def mod_view(mod: Path) -> Optional[ModView]:
    """What Rose needs to know of the selected map mod. None when the mod declares game data edits of
    its own. Raises OSError or ValueError on a mod it cannot read."""
    names: set = set()
    hashes: set = set()
    with ModFiles(mod) as files:
        listed = files.files_under()
        lowered = [name.replace("\\", "/").lower() for name in listed]
        if any(name.startswith("meta/game_data/") or "game_data.y" in name for name in lowered):
            return None
        if "meta/info.json" in lowered:
            try:
                info = json.loads(files.read(listed[lowered.index("meta/info.json")]).decode("utf-8-sig"))
            except ValueError:
                info = {}
            layers = info.get("Layers") if isinstance(info, dict) else None
            if isinstance(layers, dict) and any(isinstance(layer, dict) and layer.get("GameData") for layer in layers.values()):
                return None
        for name, low in zip(listed, lowered):
            if low.endswith(_WAD_SUFFIX):  # a packed WAD: its table names the files by hash
                span = files.span(name)
                wad = ModWad(source=FileSource(*span)) if span is not None else ModWad(files.read(name))
                try:
                    hashes.update(file.name_hash for file in wad)
                finally:
                    wad.close()
            elif _WAD_SUFFIX + "/" in low:  # a WAD kept as loose files, named by path or by hash
                inner = low.split(_WAD_SUFFIX + "/", 1)[1]
                names.add(inner)
                stem = inner.rsplit("/", 1)[-1].split(".", 1)[0]
                if len(stem) == 16:
                    try:
                        hashes.add(int(stem, 16))
                    except ValueError:
                        pass
    ships = lambda path: path.lower() in names or path_hash(path) in hashes  # noqa: E731
    return ModView(ships, ships(MAP_BIN))


def last_map_skin(game_dir: Path, known) -> Optional[str]:
    """The map skin of Summoner's Rift the newest game log of this PC names (its "mapskin = ..." line),
    one of *known*; None when no log of the last few games names one."""
    logs = Path(game_dir).parent / "Logs" / "GameLogs"
    try:
        games = sorted((folder for folder in logs.iterdir() if folder.is_dir()), key=lambda folder: folder.name, reverse=True)
    except OSError:
        return None
    for game in games[:LOGS_LOOKED_AT]:
        for log_file in game.glob("*r3dlog.txt"):
            try:
                with open(log_file, "rb") as handle:
                    found = _MAP_SKIN_LINE.search(handle.read(65536))
            except OSError:
                continue
            name = found.group(1).decode("ascii") if found else ""
            if name in known:
                return name
    return None


def mode() -> str:
    """"off", "practice" or "on": this PC's word in MODE_FILE, "off" without one"""
    try:
        word = MODE_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return "off"
    return word if word in ("practice", "on") else "off"


_game_skins: Dict[tuple, List[MapSkin]] = {}  # (the game's map WAD, its date and size) -> its map skins


def game_map_skins(game_dir: Path) -> List[MapSkin]:
    """The map skins of the installed game's Summoner's Rift, read once per version of its map WAD."""
    wad_path = Path(game_dir) / MAP_WAD
    stat = wad_path.stat()
    key = (str(wad_path), stat.st_mtime_ns, stat.st_size)
    if key not in _game_skins:
        data = GameWad(wad_path).read_path(MAP_BIN)
        _game_skins.clear()
        _game_skins[key] = map_skins(data) if data else []
    return _game_skins[key]


def mod_archive(source) -> Optional[Path]:
    """Where a selected map mod's files are: Rose's own copy, or the archive LTK Manager's library keeps."""
    path = getattr(source, "path", None)
    if path is not None:
        return Path(path)
    ltk_id = getattr(source, "ltk_id", None)
    if ltk_id:
        from injection.overlay.ltk_data import read_library_index
        entry = (read_library_index() or {}).get(ltk_id)
        return entry.archive if entry is not None else None
    return None


def write_port(game_dir: Path, target: Path, standard: str, season: str) -> int:
    """Write the mod folder *target*: under the *season* container's file names, the *standard*
    container's geometry and the season's materials with the standard ones it lacks. Returns how many
    materials were added. Raises OSError or ValueError, leaving no folder."""
    wad_path = Path(game_dir) / MAP_WAD
    game = GameWad(wad_path)
    season_bin, standard_bin = game.read_path(materials_file(season)), game.read_path(materials_file(standard))
    if season_bin is None or standard_bin is None:
        raise ValueError("the game has no materials file for one of the two maps")
    merged, added = merge_materials(season_bin, standard_bin)
    shutil.rmtree(target, ignore_errors=True)
    (target / "WAD").mkdir(parents=True)
    handle = FileSource(wad_path)
    try:
        # the geometry as the game's WAD stores it (23 MB of 92), under the season's name: nothing is unpacked
        geometry = game.stored_file(geometry_file(standard), handle, path_hash(geometry_file(season)))
        if geometry is None:
            raise ValueError("the game has no geometry file for the standard map")
        wad = ModWad(_EMPTY_WAD)
        wad.add(geometry)
        wad.put_path(materials_file(season), merged)
        wad.files.sort(key=lambda file: file.name_hash)  # by hash, as the game's own WADs are
        with open(target / "WAD" / MAP_WAD.name, "wb") as out:
            wad.write_to(out)
        info = {"Author": "Rose", "Name": "Rose map port", "Version": "1.0.0",
                "Description": f"Made by Rose for this game: the standard map drawn under {season.rsplit('/', 1)[-1]}"}
        (target / "META").mkdir()
        (target / "META" / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        handle.close()
    return added


def prepare(injector, source, mods_dir: Optional[Path] = None, practice: bool = False) -> Optional[str]:
    """Write the port for the selected map mod *source* into *mods_dir* (the injector's by default) and
    return its folder name. *practice*: the game is a Practice Tool game. None when this PC has not asked
    for it (mode()), when there is nothing to port, or when anything fails: the map mod is injected either
    way, as before."""
    setting = mode()
    if setting == "off" or (setting == "practice" and not practice):
        return None
    mods_dir = Path(mods_dir) if mods_dir is not None else injector.mods_dir
    try:
        skins = {skin.name: skin for skin in game_map_skins(injector.game_dir)}
        default = skins.get(DEFAULT)
        season = skins.get(last_map_skin(injector.game_dir, skins) or "")
        if default is None or season is None or season.container == default.container or season.playfield != default.playfield:
            return None
        archive = mod_archive(source)
        if archive is not None and archive.exists():
            view = mod_view(archive)
            if view is None or view.map_bin:
                log.info("[MAP] The selected map says itself which map loads: nothing is ported")
                return None
            own = [file(container) for container in (default.container, season.container) for file in (geometry_file, materials_file)]
            if any(view.ships(path) for path in own):
                log.info("[MAP] The selected map ships map geometry or materials of its own: not ported in this version")
                return None
        added = write_port(injector.game_dir, mods_dir / FOLDER, default.container, season.container)
        log.info(f"[MAP] A custom map is selected and the game runs {season.name}: the standard map is drawn under it "
                 f"({added} material(s) added to the season's; mode {setting})")
        return FOLDER
    except (OSError, ValueError, zipfile.BadZipFile) as e:  # PropError, WadError and ModpkgError are ValueErrors
        log.warning(f"[MAP] Could not make the standard map for the season's: {e}")
        return None

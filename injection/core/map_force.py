# -*- coding: utf-8 -*-
"""
A custom map on a Summoner's Rift the game shows under another look (the winter map).

The game's map11.bin lists "map skins" (Default, Milkshake_SRS: winter, URF...), and the
server names the one a game loads. Each links a map container: Default links
Maps/MapGeometry/Map11/Base_SRX, the map every custom map replaces; the winter skin links
its own geometry, materials and textures, so a custom map never shows under it. Since
patch 16.23 (Nov 18, 2026) every game is told to load the winter skin.

With a custom map selected, Rose adds a small mod made on the spot that links such a skin
to Default's container instead, the way the community's "Map Forcer" mod does: an edit of
map11.bin declared in the mod's META/info.json, which LTK Manager applies when it builds
the overlay. The list is read from the game's own map11.bin at each game, so a new season
needs no new mod.

The rule: with a custom map selected, a game on a seasonal skin looks as a game on Default
does. Only a skin that is another look of Default's playfield is re-linked: the same
objects file and the same navigation grid. A mode with objects of its own (URF, Arcade)
keeps its map. Nothing is added when the selected map says itself which map a skin loads
(it declares its own edits), and a skin whose map the selected mod replaces itself is left
alone (a winter-map mod). A mod with a map11.bin of its own replaces the game's, so its
skins are read from that file.

Not re-linked in this version: what else the winter skin changes (the grass tint, the
winter looks of minions, towers and monsters).
"""

import json
import shutil
import struct
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional

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
PROP_CONTAINER = "mMapContainerLink"
_CONTAINER = propbin.fnv1a_lower(PROP_CONTAINER)
_NAME = propbin.fnv1a_lower("name")
_OBJECTS = propbin.fnv1a_lower("mMapObjectsCFG")
_NAV_GRID = 0x63242493  # the navigation grid file (the property's name is not known)
_EMPTY_WAD = b"RW\x03\x04" + bytes(264) + struct.pack("<I", 0)
_WAD_SUFFIX = ".wad.client"


class MapSkin(NamedTuple):
    name: str
    container: str   # "Maps/MapGeometry/Map11/Base_SRX"
    playfield: tuple  # (objects file, navigation grid): what makes two skins the same playfield
    addressable: bool  # whether its entry is named Maps/Shipping/Map11/MapSkins/<name>


def geometry_file(container: str) -> str:
    """The map geometry file a container loads: Maps/MapGeometry/Map11/Base_SRX -> data/.../base_srx.mapgeo"""
    return f"data/{container.lower()}.mapgeo"


def map_skins(data: bytes) -> List[MapSkin]:
    """The map skins of a map11.bin. Raises propbin.PropError on a file it cannot read."""
    parsed = propbin.Bin(data)
    mark = _CONTAINER.to_bytes(4, "little")
    skins = []
    # entries are read here, not through Bin.find_entry: that gives the first entry of a type only
    for index, (start, end) in enumerate(parsed._locate()):
        body = data[start + 4:end]
        if mark not in body:
            continue
        reader = propbin._Reader(body)
        entry_hash = reader.u32()
        strings = {field.name_hash: field.value.v for field in reader.fields(parsed.types[index]) if field.value.ty == propbin.STRING}
        name, container = strings.get(_NAME), strings.get(_CONTAINER)
        if name and container:
            skins.append(MapSkin(name, container, (strings.get(_OBJECTS), strings.get(_NAV_GRID)),
                                 propbin.fnv1a_lower(SKIN_PREFIX + name) == entry_hash))
    return skins


def forced(skins: List[MapSkin], ships: Callable[[str], bool] = lambda path: False) -> Dict[str, str]:
    """{map skin name: the container it is linked to instead}: every other look of Default's playfield,
    but one whose own map the selected mod replaces (*ships*(a file's path) tells). {} without a Default."""
    default = next((skin for skin in skins if skin.name == DEFAULT), None)
    if default is None:
        return {}
    return {
        skin.name: default.container for skin in skins
        if skin.addressable and skin.container != default.container and skin.playfield == default.playfield
        and not ships(geometry_file(skin.container))
    }


class ModView(NamedTuple):
    ships: Callable[[str], bool]  # whether the mod ships a game file, by the file's path
    map_bin: Optional[bytes]      # its own map11.bin, when it ships one: its map skins are the game's then


def mod_view(mod: Path) -> Optional[ModView]:
    """What Rose needs to know of the selected map mod. None when the mod declares game data edits of
    its own: it decides itself which map a skin loads, and Rose adds nothing. Raises OSError or
    ValueError on a mod it cannot read."""
    names: set = set()
    hashes: set = set()
    map_bin: Optional[bytes] = None
    bin_hash = path_hash(MAP_BIN)
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
                    own = wad.get(bin_hash)
                    if own is not None:
                        map_bin = own.data
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
                if inner == MAP_BIN or stem == f"{bin_hash:016x}":
                    map_bin = files.read(name)
    return ModView(lambda path: path.lower() in names or path_hash(path) in hashes, map_bin)


def write_mod(target: Path, links: Dict[str, str]) -> None:
    """Write the mod that links each map skin of *links* to its new container, as a mod folder."""
    edits = {SKIN_PREFIX + name: {PROP_CONTAINER: container} for name, container in sorted(links.items())}
    info = {
        "Author": "Rose",
        "Description": "Made by Rose for this game: a custom map shows on the map skins " + ", ".join(sorted(links)),
        "Name": "Rose map forcer",
        "Version": "1.0.0",
        "Layers": {"base": {"Name": "base", "Priority": 0, "GameData": {"version": 1, "modules": [{
            "target": MAP_BIN, "edits": [edits],
            # Where the module was declared, as LTK Manager's own tools write it. Required: without it LTK
            # Manager refuses the layer's declarations ("missing field `origin`", Nov 19) and the winter map stays
            "origin": {"manifest": "game_data.yaml", "source": None, "module": 0},
        }]}}},
    }
    shutil.rmtree(target, ignore_errors=True)
    (target / "META").mkdir(parents=True)
    (target / "META" / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    # An empty Map11 WAD, as the community's Map Forcer ships: the edit is of a file of that WAD
    (target / "WAD").mkdir()
    (target / "WAD" / "Map11.wad.client").write_bytes(_EMPTY_WAD)


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


def prepare(injector, source, mods_dir: Optional[Path] = None) -> Optional[str]:
    """Write the forcer for the selected map mod *source* into *mods_dir* (the injector's by default) and
    return its folder name. None when there is nothing to re-link, or anything fails: the map mod is
    injected either way, as before."""
    mods_dir = Path(mods_dir) if mods_dir is not None else injector.mods_dir
    try:
        archive = mod_archive(source)
        view: Optional[ModView] = ModView(lambda path: False, None)
        if archive is not None and archive.exists():
            view = mod_view(archive)
        if view is None:
            log.info("[MAP] The selected map says itself which map a skin loads: nothing is forced")
            return None
        # a mod with a map11.bin of its own replaces the game's: the skins to link are that file's
        skins = map_skins(view.map_bin) if view.map_bin else game_map_skins(injector.game_dir)
        links = forced(skins, view.ships)
        if not links:
            return None
        write_mod(mods_dir / FOLDER, links)
        log.info(f"[MAP] A custom map is selected: {', '.join(sorted(links))} linked to the standard map")
        return FOLDER
    except (OSError, ValueError, zipfile.BadZipFile) as e:  # PropError, WadError and ModpkgError are ValueErrors
        log.warning(f"[MAP] Could not link the season's map to the standard one: {e}")
        return None

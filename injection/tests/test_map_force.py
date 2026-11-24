"""A custom map under a season's map: the season's files with the standard map drawn (injection/core/map_force.py)."""

import json
import shutil
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from injection.baseskin.propbin import Bin, Entry, Field, PropError, Value, build, fnv1a_lower
from injection.baseskin.wad import GameWad, ModWad, path_hash
from injection.core import map_force
from injection.core.stage_plan import MapForceStep, ModStep, StagePlan, prepare_plan
from injection.mods.mod_source import RoseFile

H = fnv1a_lower
BASE = "Maps/MapGeometry/Map11/Base_SRX"
WINTER = "Maps/MapGeometry/Map11/Milkshake_SRS"
SRX = ("ASSETS/Maps/CFG/objectcfg_SRX.cfg", "ASSETS/Maps/NavGrid/AIPath_SRX.aimesh_ngrid")
MATERIAL = 0xFF9D3409


def skin(name: str, container: str, playfield=SRX) -> Entry:
    return Entry(H("MapSkin"), H(map_force.SKIN_PREFIX + name), [
        Field(H("name"), Value.string(name)),
        Field(H("mMapContainerLink"), Value.string(container)),
        Field(H("mMapObjectsCFG"), Value.string(playfield[0])),
        Field(0x63242493, Value.string(playfield[1])),
    ])


def map_bin(*skins: Entry) -> bytes:
    return build([Entry(H("Something"), H("else"), [Field(H("note"), Value.string("not a skin"))]), *skins])


GAME_BIN = map_bin(
    skin("Default", BASE),
    skin("Milkshake_SRS", WINTER),                                                              # winter: the same playfield
    skin("URF", "Maps/MapGeometry/Map11/URF", ("ASSETS/Maps/CFG/ObjectCFG_URF.cfg", SRX[1])),   # objects of its own
)


def material(name: str, texture: str) -> Entry:
    return Entry(MATERIAL, H(name), [Field(H("texture"), Value.string(texture))])


def container(name: str, *placed: str) -> Entry:
    return Entry(H("MapContainer"), H(name), [Field(H("mapPath"), Value.string(name)), *(Field(H(one), Value.string(one)) for one in placed)])


STANDARD_MATERIALS = build([container(BASE, "Shops"), material("Ground", "ground.tex"), material("Wall", "wall.tex"),
                            material("Spawn", "spawn.tex")])
WINTER_MATERIALS = build([container(WINTER, "Shops1", "Train"), Entry(H("Placed"), H("TrainChunk"), [Field(H("note"), Value.string("SRU_Train"))]),
                          material("Wall", "wall.tex"), material("Ground", "snow.tex"), material("Snow", "pile.tex")])
STANDARD_GEOMETRY, WINTER_GEOMETRY = b"OEGM standard " * 50, b"OEGM winter " * 50


def wad_bytes(files: dict) -> bytes:
    wad = ModWad(b"RW\x03\x04" + bytes(264) + struct.pack("<I", 0))
    for path, data in files.items():
        wad.put(path_hash(path), data)
    return wad.to_bytes()


def by_name(data: bytes) -> dict:
    """{name hash: the entry's bytes} of a bin file"""
    return {name_hash: raw for _owner, name_hash, raw in map_force._entries(data)[1]}


class MapSkinsTests(unittest.TestCase):
    def test_the_skins_of_a_map_file_are_read_with_what_they_link(self):
        skins = {one.name: one for one in map_force.map_skins(GAME_BIN)}

        self.assertEqual(sorted(skins), ["Default", "Milkshake_SRS", "URF"])
        self.assertEqual((skins["Default"].container, skins["Milkshake_SRS"].container), (BASE, WINTER))
        self.assertEqual(skins["Default"].playfield, skins["Milkshake_SRS"].playfield)
        self.assertNotEqual(skins["Default"].playfield, skins["URF"].playfield)

    def test_a_containers_two_files(self):
        self.assertEqual(map_force.geometry_file(WINTER), "data/maps/mapgeometry/map11/milkshake_srs.mapgeo")
        self.assertEqual(map_force.materials_file(BASE), "data/maps/mapgeometry/map11/base_srx.materials.bin")


class MergeMaterialsTests(unittest.TestCase):
    def test_the_seasons_file_gets_the_standard_materials_it_lacks_or_has_otherwise(self):
        merged, added = map_force.merge_materials(WINTER_MATERIALS, STANDARD_MATERIALS)

        winter, standard, result = by_name(WINTER_MATERIALS), by_name(STANDARD_MATERIALS), by_name(merged)
        self.assertEqual(added, 2, "Spawn is new, Ground is the standard one again; Wall was the same already")
        self.assertEqual(sorted(result), sorted(set(winter) | {H("Spawn")}))
        self.assertEqual((result[H("Spawn")], result[H("Ground")]), (standard[H("Spawn")], standard[H("Ground")]))
        for kept in (H(WINTER), H("TrainChunk"), H("Wall"), H("Snow")):
            self.assertEqual(result[kept], winter[kept], "the container, its placed objects and winter's own materials: byte for byte")
        self.assertNotIn(H(BASE), result, "the standard map's container is not brought along")
        self.assertEqual(len(Bin(merged).types), 6)

    def test_nothing_to_add_gives_the_same_file(self):
        merged, added = map_force.merge_materials(STANDARD_MATERIALS, STANDARD_MATERIALS)

        self.assertEqual((added, merged), (0, STANDARD_MATERIALS))

    def test_a_file_it_cannot_take_is_refused(self):
        with self.assertRaises(PropError):
            map_force.merge_materials(b"PTCH" + bytes(8) + WINTER_MATERIALS, STANDARD_MATERIALS)
        with self.assertRaises(PropError):
            map_force.merge_materials(WINTER_MATERIALS, b"not a bin")


class ModTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose_mapforce_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def mod(self, name: str, entries: dict) -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as out:
            for entry, data in entries.items():
                out.writestr(entry, data)
        return path


class ModViewTests(ModTestCase):
    WINTER_GEO = "data/maps/mapgeometry/map11/milkshake_srs.mapgeo"

    def test_a_packed_wad_is_asked_by_the_hash_of_a_path(self):
        view = map_force.mod_view(self.mod("Winter.fantome", {
            "META/info.json": '{"Name": "Winter"}',
            "WAD/Map11.wad.client": wad_bytes({self.WINTER_GEO: b"geometry", "assets/snow.tex": b"tex"}),
        }))

        self.assertEqual((view.ships(self.WINTER_GEO), view.ships("data/maps/mapgeometry/map11/base_srx.mapgeo")), (True, False))
        self.assertFalse(view.map_bin)

    def test_loose_files_are_asked_by_path_or_by_the_hash_in_their_name(self):
        named = map_force.mod_view(self.mod("Named.fantome", {f"WAD/map11.wad.client/{self.WINTER_GEO.upper()}": b"g"}))
        hashed = map_force.mod_view(self.mod("Hashed.fantome", {f"WAD/Map11.wad.client/{path_hash(self.WINTER_GEO):016x}.mapgeo": b"g"}))

        self.assertTrue(named.ships(self.WINTER_GEO) and hashed.ships(self.WINTER_GEO))
        self.assertFalse(named.ships("assets/other.tex") or hashed.ships("assets/other.tex"))

    def test_a_mod_that_declares_its_own_edits_is_told_apart(self):
        in_info = self.mod("Forcer.fantome", {"META/info.json": json.dumps({"Name": "Forcer", "Layers": {"base": {
            "GameData": {"version": 1, "modules": [{"target": map_force.MAP_BIN, "edits": [{}]}]}}}})})
        as_file = self.mod("Declares.fantome", {"META/info.json": "{}", "META/game_data/base/game_data.yaml": "version: 1\n"})

        self.assertIsNone(map_force.mod_view(in_info))
        self.assertIsNone(map_force.mod_view(as_file))

    def test_a_map_file_of_its_own_is_seen(self):
        packed = map_force.mod_view(self.mod("Packed.fantome", {"WAD/Map11.wad.client": wad_bytes({map_force.MAP_BIN: GAME_BIN})}))
        loose = map_force.mod_view(self.mod("Loose.fantome", {f"WAD/Map11.wad.client/{map_force.MAP_BIN}": GAME_BIN}))

        self.assertTrue(packed.map_bin and loose.map_bin)


class GameTestCase(ModTestCase):
    """A stand-in League folder: the game's map WAD, and the logs of its last games"""

    def setUp(self):
        super().setUp()
        self.game = self.root / "League" / "Game"
        (self.game / map_force.MAP_WAD).parent.mkdir(parents=True)
        (self.game / map_force.MAP_WAD).write_bytes(wad_bytes({
            map_force.MAP_BIN: GAME_BIN,
            map_force.geometry_file(BASE): STANDARD_GEOMETRY, map_force.materials_file(BASE): STANDARD_MATERIALS,
            map_force.geometry_file(WINTER): WINTER_GEOMETRY, map_force.materials_file(WINTER): WINTER_MATERIALS,
        }))
        self.played("2026-11-19T01-00-00", "Milkshake_SRS")

    def played(self, when: str, map_skin: str) -> None:
        folder = self.root / "League" / "Logs" / "GameLogs" / when
        folder.mkdir(parents=True)
        (folder / f"{when}_r3dlog.txt").write_text(f"000001.899| ALWAYS| GameStartInfo GPP match Id = made-up, mapskin = {map_skin}\n", encoding="utf-8")


class LastMapSkinTests(GameTestCase):
    def test_the_newest_game_log_names_the_season(self):
        self.played("2026-11-13T16-42-01", "Default")

        self.assertEqual(map_force.last_map_skin(self.game, {"Default", "Milkshake_SRS"}), "Milkshake_SRS")

    def test_a_game_on_another_map_is_looked_past(self):
        self.played("2026-11-19T02-00-00", "HowlingAbyss")

        self.assertEqual(map_force.last_map_skin(self.game, {"Default", "Milkshake_SRS"}), "Milkshake_SRS")

    def test_no_logs_name_no_season(self):
        self.assertIsNone(map_force.last_map_skin(self.root / "Nowhere" / "Game", {"Default"}))


class ModeTests(ModTestCase):
    def test_this_pc_has_to_ask_for_it(self):
        word = self.root / "rose-map-port.txt"
        with patch.object(map_force, "MODE_FILE", word), patch.object(map_force, "pc_mode_file", return_value=None):
            self.assertEqual(map_force.mode(), "off", "no file: off, as on a PC that installed Rose")
            for text, mode in (("practice", "practice"), ("ON\n", "on"), ("yes please", "off"), ("", "off")):
                word.write_text(text, encoding="utf-8")
                self.assertEqual(map_force.mode(), mode)

    def test_the_word_is_kept_where_nothing_is_published_from(self):
        self.assertEqual(map_force.MODE_FILE.parent.name, ".git")

    def test_an_installed_copy_asks_in_roses_data_folder(self):
        """It has no .git, and one made for the switch would end its updates"""
        data = self.root / "Rose data"
        data.mkdir()
        with patch.object(map_force, "MODE_FILE", self.root / "copy" / ".git" / "rose-map-port.txt"), \
                patch("utils.core.paths.get_user_data_dir", return_value=data):
            self.assertEqual(map_force.pc_mode_file(), data / "rose-map-port.txt")
            self.assertEqual(map_force.mode(), "off", "no file there either")
            for text, mode in (("on", "on"), ("Practice\r\n", "practice"), ("maybe", "off")):
                (data / "rose-map-port.txt").write_text(text, encoding="utf-8")
                self.assertEqual(map_force.mode(), mode)
            (data / "rose-map-port.txt").write_text("on", encoding="utf-8-sig")
            self.assertEqual(map_force.mode(), "on", "saved with a byte order mark, as some editors do")

    def test_the_developers_copy_says_it_when_both_files_are_there(self):
        developer, pc = self.root / "developer.txt", self.root / "pc.txt"
        developer.write_text("practice", encoding="utf-8")
        pc.write_text("on", encoding="utf-8")
        with patch.object(map_force, "MODE_FILE", developer), patch.object(map_force, "pc_mode_file", return_value=pc):
            self.assertEqual(map_force.mode(), "practice")
            developer.write_text("no", encoding="utf-8")
            self.assertEqual(map_force.mode(), "off", "a word it does not know is off, not the other file's turn")

    def test_a_data_folder_that_cannot_be_told_is_off(self):
        with patch.object(map_force, "MODE_FILE", self.root / "none.txt"), \
                patch("utils.core.paths.get_user_data_dir", side_effect=OSError("no profile")):
            self.assertIsNone(map_force.pc_mode_file())
            self.assertEqual(map_force.mode(), "off")


class PrepareTests(GameTestCase):
    def setUp(self):
        super().setUp()
        self.mods = self.root / "mods"
        self.mods.mkdir()
        self.injector = SimpleNamespace(game_dir=self.game, mods_dir=self.mods)
        self.plain = RoseFile(self.mod("Hexed Rift.fantome", {"META/info.json": '{"Name": "Hexed Rift"}',
                                                              "WAD/Map11.wad.client": wad_bytes({"assets/grass.tex": b"tex"})}), "Hexed Rift")
        self.mode = "on"
        asked = patch.object(map_force, "mode", side_effect=lambda: self.mode)
        asked.start()
        self.addCleanup(asked.stop)

    def made(self) -> ModWad:
        return ModWad((self.mods / "rose_map_force" / "WAD" / "Map11.wad.client").read_bytes())

    def test_the_standard_map_is_put_under_the_seasons_file_names(self):
        self.assertEqual(map_force.prepare(self.injector, self.plain), "rose_map_force")

        wad = self.made()
        self.assertEqual(sorted(file.name_hash for file in wad), sorted(path_hash(file(WINTER)) for file in (map_force.geometry_file, map_force.materials_file)))
        self.assertEqual(wad.get(path_hash(map_force.geometry_file(WINTER))).data, STANDARD_GEOMETRY, "the standard geometry, as the game has it")
        materials = by_name(wad.get(path_hash(map_force.materials_file(WINTER))).data)
        self.assertEqual(materials[H(WINTER)], by_name(WINTER_MATERIALS)[H(WINTER)], "the winter container with its placed objects")
        self.assertIn(H("Spawn"), materials)
        self.assertEqual(json.loads((self.mods / "rose_map_force" / "META" / "info.json").read_text(encoding="utf-8"))["Name"], "Rose map port")
        self.assertEqual(GameWad(self.game / map_force.MAP_WAD).read_path(map_force.geometry_file(WINTER)), WINTER_GEOMETRY, "the game's files are only read")

    def test_it_is_made_only_when_this_pc_asks_and_first_only_in_the_practice_tool(self):
        self.mode = "off"
        self.assertIsNone(map_force.prepare(self.injector, self.plain, practice=True))
        self.mode = "practice"
        self.assertIsNone(map_force.prepare(self.injector, self.plain), "a real game: nothing")
        self.assertFalse((self.mods / "rose_map_force").exists())
        self.assertEqual(map_force.prepare(self.injector, self.plain, practice=True), "rose_map_force")

    def test_a_game_on_the_standard_map_needs_nothing(self):
        self.played("2026-11-20T00-00-00", "Default")

        self.assertIsNone(map_force.prepare(self.injector, self.plain))

    def test_a_mode_with_objects_of_its_own_is_not_ported(self):
        self.played("2026-11-20T00-00-00", "URF")

        self.assertIsNone(map_force.prepare(self.injector, self.plain))

    def test_a_mod_that_says_itself_which_map_loads_or_ships_its_own_map_is_left_alone(self):
        mods = {
            "Forcer": {"META/info.json": json.dumps({"Layers": {"base": {"GameData": {"version": 1, "modules": []}}}})},
            "Noxus": {"WAD/Map11.wad.client": wad_bytes({map_force.MAP_BIN: GAME_BIN})},
            "Winter": {"WAD/Map11.wad.client": wad_bytes({map_force.geometry_file(WINTER): b"g"})},
            "Anima": {"WAD/Map11.wad.client": wad_bytes({map_force.materials_file(BASE): STANDARD_MATERIALS})},
        }
        for name, entries in mods.items():
            with self.subTest(mod=name):
                self.assertIsNone(map_force.prepare(self.injector, RoseFile(self.mod(f"{name}.fantome", entries), name)))
        self.assertFalse((self.mods / "rose_map_force").exists())

    def test_nothing_it_cannot_read_stops_the_injection_or_leaves_half_a_mod(self):
        broken = self.root / "Broken.fantome"
        broken.write_bytes(b"not a zip")
        self.assertIsNone(map_force.prepare(self.injector, RoseFile(broken, "Broken")))

        (self.game / map_force.MAP_WAD).write_bytes(wad_bytes({map_force.MAP_BIN: GAME_BIN, map_force.materials_file(BASE): STANDARD_MATERIALS,
                                                               map_force.materials_file(WINTER): WINTER_MATERIALS}))  # no geometry
        map_force._game_skins.clear()
        self.assertIsNone(map_force.prepare(self.injector, self.plain))
        self.assertFalse((self.mods / "rose_map_force").exists())

    def test_the_staged_plan_puts_it_after_the_map(self):
        self.mode = "practice"

        self.assertEqual(prepare_plan(self.injector, StagePlan("skin_1000", (ModStep(self.plain), MapForceStep(self.plain, True))), self.mods),
                         ["Hexed Rift", "rose_map_force"])
        shutil.rmtree(self.mods / "rose_map_force")
        self.assertEqual(prepare_plan(self.injector, StagePlan("skin_1000", (ModStep(self.plain), MapForceStep(self.plain))), self.mods),
                         ["Hexed Rift"], "not a Practice Tool game")


if __name__ == "__main__":
    unittest.main()

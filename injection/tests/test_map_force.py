"""A custom map on a Summoner's Rift the game shows under another look (injection/core/map_force.py)."""

import json
import shutil
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from injection.baseskin.propbin import Entry, Field, Value, build, fnv1a_lower
from injection.baseskin.wad import ModWad, path_hash
from injection.core import map_force
from injection.core.stage_plan import MapForceStep, ModStep, StagePlan, prepare_plan
from injection.mods.mod_source import RoseFile

H = fnv1a_lower
BASE = "Maps/MapGeometry/Map11/Base_SRX"
WINTER = "Maps/MapGeometry/Map11/Milkshake_SRS"
SRX = ("ASSETS/Maps/CFG/objectcfg_SRX.cfg", "ASSETS/Maps/NavGrid/AIPath_SRX.aimesh_ngrid")


def skin(name: str, container: str, playfield=SRX, entry_name: str = "") -> Entry:
    return Entry(H("MapSkin"), H(map_force.SKIN_PREFIX + (entry_name or name)), [
        Field(H("name"), Value.string(name)),
        Field(H("mMapContainerLink"), Value.string(container)),
        Field(H("mMapObjectsCFG"), Value.string(playfield[0])),
        Field(0x63242493, Value.string(playfield[1])),
    ])


def map_bin(*skins: Entry) -> bytes:
    return build([Entry(H("MapContainer"), H(BASE), [Field(H("note"), Value.string("not a skin"))]), *skins])


GAME_BIN = map_bin(
    skin("Default", BASE),
    skin("Milkshake_SRS", WINTER),                                         # the winter look of the same playfield
    skin("LunarRevel", BASE),                                              # on the standard map already
    skin("URF", "Maps/MapGeometry/Map11/URF", ("ASSETS/Maps/CFG/ObjectCFG_URF.cfg", SRX[1])),   # objects of its own
    skin("10Year", "Maps/MapGeometry/Map11/10Year", (SRX[0], "ASSETS/Maps/NavGrid/AIPath.aimesh_ngrid")),  # another grid
    skin("Odd", "Maps/MapGeometry/Map11/Odd", entry_name="NamedOtherwise"),  # an entry Rose cannot name
)


def wad_bytes(files: dict) -> bytes:
    wad = ModWad(b"RW\x03\x04" + bytes(264) + struct.pack("<I", 0))
    for path, data in files.items():
        wad.put(path_hash(path), data)
    return wad.to_bytes()


class MapSkinsTests(unittest.TestCase):
    def test_the_skins_of_a_map_file_are_read_with_what_they_link(self):
        skins = {one.name: one for one in map_force.map_skins(GAME_BIN)}

        self.assertEqual(sorted(skins), ["10Year", "Default", "LunarRevel", "Milkshake_SRS", "Odd", "URF"])
        self.assertEqual((skins["Default"].container, skins["Milkshake_SRS"].container), (BASE, WINTER))
        self.assertEqual(skins["Default"].playfield, SRX)
        self.assertEqual((skins["Milkshake_SRS"].addressable, skins["Odd"].addressable), (True, False))

    def test_only_another_look_of_the_default_playfield_is_linked_to_the_standard_map(self):
        self.assertEqual(map_force.forced(map_force.map_skins(GAME_BIN)), {"Milkshake_SRS": BASE})

    def test_a_skin_whose_map_the_mod_replaces_itself_is_left_alone(self):
        ships_winter = lambda path: path == "data/maps/mapgeometry/map11/milkshake_srs.mapgeo"

        self.assertEqual(map_force.forced(map_force.map_skins(GAME_BIN), ships_winter), {})

    def test_a_map_file_without_a_default_skin_links_nothing(self):
        self.assertEqual(map_force.forced(map_force.map_skins(map_bin(skin("Milkshake_SRS", WINTER)))), {})


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
        self.assertIsNone(view.map_bin)

    def test_loose_files_are_asked_by_path_or_by_the_hash_in_their_name(self):
        named = map_force.mod_view(self.mod("Named.fantome", {f"WAD/map11.wad.client/{self.WINTER_GEO.upper()}": b"g"}))
        hashed = map_force.mod_view(self.mod("Hashed.fantome", {f"WAD/Map11.wad.client/{path_hash(self.WINTER_GEO):016x}.mapgeo": b"g"}))

        self.assertTrue(named.ships(self.WINTER_GEO) and hashed.ships(self.WINTER_GEO))
        self.assertFalse(named.ships("assets/other.tex") or hashed.ships("assets/other.tex"))

    def test_a_mod_that_declares_its_own_edits_gets_nothing_from_rose(self):
        in_info = self.mod("Forcer.fantome", {"META/info.json": json.dumps({"Name": "Forcer", "Layers": {"base": {
            "GameData": {"version": 1, "modules": [{"target": map_force.MAP_BIN, "edits": [{}]}]}}}})})
        as_file = self.mod("Declares.fantome", {"META/info.json": "{}", "META/game_data/base/game_data.yaml": "version: 1\n"})

        self.assertIsNone(map_force.mod_view(in_info))
        self.assertIsNone(map_force.mod_view(as_file))

    def test_a_map_file_of_its_own_is_handed_over(self):
        own = map_bin(skin("Default", BASE), skin("Bloom", "Maps/MapGeometry/Map11/Bloom"))
        packed = map_force.mod_view(self.mod("Packed.fantome", {"WAD/Map11.wad.client": wad_bytes({map_force.MAP_BIN: own})}))
        loose = map_force.mod_view(self.mod("Loose.fantome", {f"WAD/Map11.wad.client/{map_force.MAP_BIN}": own}))

        self.assertEqual((packed.map_bin, loose.map_bin), (own, own))


class PrepareTests(ModTestCase):
    def setUp(self):
        super().setUp()
        game = self.root / "Game"
        (game / map_force.MAP_WAD).parent.mkdir(parents=True)
        (game / map_force.MAP_WAD).write_bytes(wad_bytes({map_force.MAP_BIN: GAME_BIN}))
        self.mods = self.root / "mods"
        self.mods.mkdir()
        self.injector = SimpleNamespace(game_dir=game, mods_dir=self.mods)
        self.plain = RoseFile(self.mod("Hexed Rift.fantome", {"META/info.json": '{"Name": "Hexed Rift"}',
                                                              "WAD/Map11.wad.client": wad_bytes({"assets/grass.tex": b"tex"})}), "Hexed Rift")

    def edits(self) -> dict:
        info = json.loads((self.mods / map_force.FOLDER / "META" / "info.json").read_text(encoding="utf-8"))
        module, = info["Layers"]["base"]["GameData"]["modules"]
        self.assertEqual((info["Layers"]["base"]["GameData"]["version"], module["target"]), (1, "data/maps/shipping/map11/map11.bin"))
        # The module's keys are the community Map Forcer's, all of them. Nov 19: without "origin" LTK Manager
        # refused the declarations ("missing field `origin`") and the winter map stayed, in every game
        self.assertEqual(sorted(module), ["edits", "origin", "target"])
        self.assertEqual(module["origin"], {"manifest": "game_data.yaml", "source": None, "module": 0})
        edits, = module["edits"]
        return edits

    def test_a_plain_custom_map_gets_the_winter_skin_linked_to_the_standard_map(self):
        self.assertEqual(map_force.prepare(self.injector, self.plain), "rose_map_force")

        self.assertEqual(self.edits(), {"Maps/Shipping/Map11/MapSkins/Milkshake_SRS": {"mMapContainerLink": BASE}})
        empty = ModWad((self.mods / "rose_map_force" / "WAD" / "Map11.wad.client").read_bytes())
        self.assertEqual(len(empty.files), 0, "an empty Map11 WAD, as the community's Map Forcer ships")
        self.assertEqual(map_force.prepare(self.injector, self.plain), "rose_map_force", "made again for the next game")

    def test_a_winter_map_mod_and_a_mod_with_its_own_edits_get_nothing(self):
        winter = RoseFile(self.mod("Winter.fantome", {"WAD/Map11.wad.client": wad_bytes({"data/maps/mapgeometry/map11/milkshake_srs.mapgeo": b"g"})}), "Winter")
        forcer = RoseFile(self.mod("Forcer.fantome", {"META/info.json": json.dumps({"Layers": {"base": {"GameData": {"version": 1, "modules": []}}}})}), "Forcer")

        self.assertIsNone(map_force.prepare(self.injector, winter))
        self.assertIsNone(map_force.prepare(self.injector, forcer))
        self.assertFalse((self.mods / "rose_map_force").exists())

    def test_a_mod_with_a_map_file_of_its_own_has_its_skins_linked(self):
        own = map_bin(skin("Default", BASE), skin("Bloom", "Maps/MapGeometry/Map11/Bloom"))
        mod = RoseFile(self.mod("Noxus.fantome", {"WAD/Map11.wad.client": wad_bytes({map_force.MAP_BIN: own})}), "Noxus")

        self.assertEqual(map_force.prepare(self.injector, mod), "rose_map_force")
        self.assertEqual(list(self.edits()), ["Maps/Shipping/Map11/MapSkins/Bloom"], "the skins of the file the game will read")

    def test_nothing_it_cannot_read_stops_the_injection(self):
        broken = self.root / "Broken.fantome"
        broken.write_bytes(b"not a zip")
        no_game = SimpleNamespace(game_dir=self.root / "nowhere", mods_dir=self.mods)

        self.assertIsNone(map_force.prepare(self.injector, RoseFile(broken, "Broken")))
        self.assertIsNone(map_force.prepare(no_game, self.plain))

    def test_the_staged_plan_puts_the_forcer_after_the_map(self):
        plan = StagePlan("skin_1000", (ModStep(self.plain), MapForceStep(self.plain)))

        self.assertEqual(prepare_plan(self.injector, plan, self.mods), ["Hexed Rift", "rose_map_force"])


if __name__ == "__main__":
    unittest.main()

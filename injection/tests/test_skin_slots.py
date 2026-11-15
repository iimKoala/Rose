"""A skin written again under the other slots of its champion (injection/baseskin/slots.py)."""

import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from injection.baseskin import slots
from injection.baseskin.propbin import HASH, LINK, Bin, Entry, Field, Value, build, fnv1a_lower
from injection.baseskin.wad import ModWad, path_hash

H = fnv1a_lower


def packed(name: str) -> bytes:
    return struct.pack("<I", H(name))


def skin_entry(slot: int, shows: int, character: str = "Aatrox") -> Entry:
    """The skin entry of skin<slot>.bin that shows skin *shows* (a skin Rose ships: slot 0 shows skin N)."""
    return Entry(slots.SKIN_CLASS, H(f"Characters/{character}/Skins/Skin{slot}"), [
        Field(H("championSkinName"), Value.string(f"{character}Skin{shows}")),
        Field(slots.PROP_OWN_NAME, Value(HASH, packed(f"Characters/{character}/Skins/Skin{shows}"))),
        Field(slots.PROP_RESOURCES, Value(LINK, packed(f"Characters/{character}/Skins/Skin{shows}/Resources"))),
    ])


def resources_entry(slot: int, character: str = "Aatrox") -> Entry:
    return Entry(slots.RESOURCES_CLASS, H(f"Characters/{character}/Skins/Skin{slot}/Resources"),
                 [Field(H("note"), Value.string("particles"))])


def material_entry() -> Entry:
    return Entry(H("SomeMaterial"), H("Characters/Aatrox/Skins/Skin0/Materials/Body"), [Field(H("note"), Value.string("body"))])


def wad_bytes(files: dict) -> bytes:
    wad = ModWad(b"RW\x03\x04" + bytes(264) + struct.pack("<I", 0))
    for path, data in files.items():
        wad.put(path_hash(path), data)
    return wad.to_bytes()


def names_in(data: bytes, character: str = "Aatrox") -> dict:
    """What a slot's copy says: its entries' names and the two names the skin entry repeats."""
    file = Bin(data)
    skin = file.find_entry(slots.SKIN_CLASS)
    resources = file.find_entry(slots.RESOURCES_CLASS)
    return {
        "skin": skin.path_hash, "resources": resources.path_hash if resources else None,
        "own": skin.find_field(slots.PROP_OWN_NAME).value.v, "link": skin.find_field(slots.PROP_RESOURCES).value.v,
        "entries": len(file.types), "linked": file.linked,
    }


class SlotCopiesTests(unittest.TestCase):
    def test_a_shipped_skin_is_named_for_the_slot_and_keeps_the_names_of_the_skin_it_shows(self):
        shipped = build([skin_entry(0, shows=5), resources_entry(0)], linked_files=["DATA/Characters/Aatrox/Skins/Skin5.bin"])

        copies = slots.slot_copies(shipped, "aatrox", [1, 12])

        self.assertEqual(sorted(copies), [1, 12])
        said = names_in(copies[12])
        self.assertEqual(said["skin"], H("Characters/Aatrox/Skins/Skin12"))
        self.assertEqual(said["resources"], H("Characters/Aatrox/Skins/Skin12/Resources"))
        self.assertEqual(said["own"], packed("Characters/Aatrox/Skins/Skin5"))
        self.assertEqual(said["link"], packed("Characters/Aatrox/Skins/Skin5/Resources"))
        self.assertEqual(said["linked"], ["DATA/Characters/Aatrox/Skins/Skin5.bin"])
        # one slot's copy does not change another's
        self.assertEqual(names_in(copies[1])["skin"], H("Characters/Aatrox/Skins/Skin1"))

    def test_a_custom_skin_is_renamed_whole_and_links_its_own_bin_for_the_rest(self):
        custom = build([skin_entry(0, shows=0), material_entry(), resources_entry(0)],
                       linked_files=["DATA/Characters/Aatrox/Aatrox.bin"])

        said = names_in(slots.slot_copies(custom, "aatrox", [7])[7])

        self.assertEqual(said["skin"], H("Characters/Aatrox/Skins/Skin7"))
        self.assertEqual(said["resources"], H("Characters/Aatrox/Skins/Skin7/Resources"))
        self.assertEqual(said["own"], packed("Characters/Aatrox/Skins/Skin7"))
        self.assertEqual(said["link"], packed("Characters/Aatrox/Skins/Skin7/Resources"))
        # the material stays in the mod's skin0.bin, which the copy links
        self.assertEqual(said["entries"], 2)
        self.assertEqual(said["linked"], ["DATA/Characters/aatrox/Skins/Skin0.bin"])

    def test_a_skin_without_a_resource_list_keeps_its_link(self):
        bare = build([skin_entry(0, shows=0)])

        said = names_in(slots.slot_copies(bare, "aatrox", [3])[3])

        self.assertEqual(said["skin"], H("Characters/Aatrox/Skins/Skin3"))
        self.assertIsNone(said["resources"])
        self.assertEqual(said["link"], packed("Characters/Aatrox/Skins/Skin0/Resources"))

    def test_what_is_not_the_base_skin_of_the_character_gives_nothing(self):
        other_slot = build([skin_entry(3, shows=3), resources_entry(3)])
        self.assertEqual(slots.slot_copies(other_slot, "aatrox", [1]), {})
        self.assertEqual(slots.slot_copies(build([skin_entry(0, shows=0)]), "ahri", [1]), {})
        self.assertEqual(slots.slot_copies(b"not a bin", "aatrox", [1]), {})
        self.assertEqual(slots.slot_copies(build([material_entry()]), "aatrox", [1]), {})


class WriteModTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / "Game"
        champions = self.game / "DATA" / "FINAL" / "Champions"
        champions.mkdir(parents=True)
        game_files = {slots.skin_bin_path("annie", slot): build([skin_entry(slot, slot, "Annie"), resources_entry(slot, "Annie")])
                      for slot in (0, 1, 2, 7)}
        game_files.update({slots.skin_bin_path("annietibbers", slot): build([skin_entry(slot, slot, "AnnieTibbers")])
                           for slot in (0, 2)})
        (champions / "Annie.wad.client").write_bytes(wad_bytes(game_files))
        self.archive = self.root / "shipped.fantome"
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("META/info.json", '{"Name": "Annie 2"}')
            archive.writestr("WAD/Annie.wad.client", wad_bytes({
                slots.skin_bin_path("annie", 0): build([skin_entry(0, 2, "Annie"), resources_entry(0, "Annie")]),
                "assets/characters/annie/skins/base/annie.skn": b"mesh",
            }))
            archive.writestr("WAD/Annie.en_US.wad.client", wad_bytes({
                slots.skin_bin_path("annie", 0): b"a voice-over WAD is not where a skin is",
            }))

    def written(self, target: Path) -> list:
        return sorted(str(f.relative_to(target)).replace("\\", "/") for f in target.rglob("*") if f.is_file())

    def test_a_mod_gets_a_copy_under_every_slot_the_game_has_but_its_own_and_the_skipped(self):
        bins = slots.mod_base_bins(self.archive)
        self.assertEqual([(b.stem, b.character) for b in bins], [("Annie", "annie")])

        target = self.root / "out"
        self.assertEqual(slots.write_mod(self.game, target, bins, skip={2}, note="Annie 2"), 2)

        self.assertEqual(self.written(target), [
            "META/info.json",
            "RAW/data/characters/annie/skins/skin1.bin",
            "RAW/data/characters/annie/skins/skin7.bin",
        ])
        copy = (target / "RAW" / "data" / "characters" / "annie" / "skins" / "skin7.bin").read_bytes()
        self.assertEqual(names_in(copy, "Annie")["skin"], H("Characters/Annie/Skins/Skin7"))

    def test_the_default_look_covers_the_champion_and_what_it_summons(self):
        bins = slots.game_base_bins(self.game, "Annie")
        self.assertEqual([b.character for b in bins], ["annie", "annietibbers"])

        target = self.root / "out"
        self.assertEqual(slots.write_mod(self.game, target, bins), 4)

        self.assertEqual(self.written(target), [
            "META/info.json",
            "RAW/data/characters/annie/skins/skin1.bin",
            "RAW/data/characters/annie/skins/skin2.bin",
            "RAW/data/characters/annie/skins/skin7.bin",
            "RAW/data/characters/annietibbers/skins/skin2.bin",
        ])

    def test_nothing_to_copy_leaves_no_folder(self):
        target = self.root / "out"
        self.assertEqual(slots.write_mod(self.game, target, []), 0)
        self.assertEqual(slots.write_mod(self.game, target, [slots.BaseBin("Annie", "annie", b"not a bin")]), 0)
        self.assertEqual(slots.write_mod(self.game, target, [slots.BaseBin("Nobody", "nobody", build([skin_entry(0, 0, "Nobody")]))]), 0)
        self.assertFalse(target.exists())

    def test_a_mod_that_does_not_read_has_no_base_skin(self):
        self.assertEqual(slots.mod_base_bins(self.root / "missing.fantome"), [])
        broken = self.root / "broken.fantome"
        broken.write_bytes(b"not an archive")
        self.assertEqual(slots.mod_base_bins(broken), [])
        self.assertEqual(slots.game_base_bins(self.game, "Nobody"), [])


if __name__ == "__main__":
    unittest.main()

"""Numbers a mod stores wider than the game reads, stored as the game reads them (injection/tools/int_widths.py)."""

import shutil
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from injection.baseskin.propbin import EMBED, I32, LIST, U8, U16, U32, Bin, Embed, Entry, Field, Value, _Reader, build, fnv1a_lower
from injection.baseskin.wad import ModWad, path_hash
from injection.tools import int_widths

H = fnv1a_lower
MATERIAL = 0xFF9D3409  # StaticMaterialDef
TYPE = 0x5127F14D      # its "type": 32 bits until patch 16.17, 8 bits since
FONT, FONT_SIZE = 0x92C8C778, 0x28C538E1  # a font's size: 32 bits, then 16


def u32(number: int) -> Value:
    return Value(U32, struct.pack("<I", number))


def material(name: str, kind: Value) -> Entry:
    return Entry(MATERIAL, H(name), [Field(H("note"), Value.string(name)), Field(TYPE, kind)])


def other_entry() -> Entry:
    """An entry of another class with a property of the same name: not the game's narrowed one"""
    return Entry(H("SomethingElse"), H("Other"), [Field(TYPE, u32(3))])


def wad_bytes(files: dict) -> bytes:
    wad = ModWad(b"RW\x03\x04" + bytes(264) + struct.pack("<I", 0))
    for path, data in files.items():
        wad.put(path_hash(path), data)
    return wad.to_bytes()


def kind_of(data: bytes, index: int = 0):
    """(type tag, number) of the "type" property of the file's entry at *index*"""
    file = Bin(data)
    start, end = file._locate()[index]
    reader = _Reader(data[start + 4:end])
    reader.u32()
    value = next(field.value for field in reader.fields(file.types[index]) if field.name_hash == TYPE)
    return value.ty, int.from_bytes(value.v, "little")


class NarrowBinTests(unittest.TestCase):
    def test_a_number_that_fits_is_stored_as_the_game_reads_it(self):
        data = build([material("Body", u32(3)), other_entry(), material("Hair", u32(3))])

        fresh, count = int_widths.narrow_bin(data)

        self.assertEqual(count, 2)
        self.assertEqual((kind_of(fresh, 0), kind_of(fresh, 2)), ((U8, 3), (U8, 3)))
        self.assertEqual(kind_of(fresh, 1), (U32, 3), "another class's property of that name is not the game's")
        self.assertEqual(len(fresh), len(data) - 6, "three bytes less for each, and nothing else moved")

    def test_a_number_that_does_not_fit_and_one_already_narrow_are_left(self):
        data = build([material("Big", u32(300)), material("Done", Value(U8, b"\x03"))])

        fresh, count = int_widths.narrow_bin(data)

        self.assertEqual((count, fresh), (0, data), "the same bytes: nothing was read back from values")

    def test_a_number_inside_a_nested_object_is_found(self):
        font = Embed(FONT, [Field(FONT_SIZE, u32(24)), Field(H("name"), Value.string("Beaufort"))])
        negative = Embed(0x665C9FE7, [Field(0xF3CA8ECE, Value(I32, struct.pack("<i", -1)))])  # no unsigned form
        data = build([Entry(H("FontList"), H("Fonts"), [Field(H("fonts"), Value(LIST, [Value(EMBED, font), Value(EMBED, negative)], EMBED))])])

        fresh, count = int_widths.narrow_bin(data)

        self.assertEqual(count, 1)
        fonts = Bin(fresh).find_entry(H("FontList")).find_field(H("fonts")).value.v
        size = fonts[0].v.find_field(FONT_SIZE).value
        self.assertEqual((size.ty, size.v), (U16, struct.pack("<H", 24)))
        self.assertEqual(fonts[1].v.find_field(0xF3CA8ECE).value.ty, I32, "a negative number has no place in an unsigned type")

    def test_a_file_without_such_a_class_is_not_even_read(self):
        self.assertEqual(int_widths.narrow_bin(b"PROP" + b"\xff" * 40), (b"PROP" + b"\xff" * 40, 0))


class RepairArchiveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose_widths_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.texture = b"TEX\x00" + bytes(64)
        self.wad = wad_bytes({"data/a.bin": build([material("Body", u32(3))]), "data/b.bin": build([other_entry()]),
                              "assets/body.tex": self.texture})

    def archive(self, name: str = "Zeri.fantome", wad: bytes = None) -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as out:
            out.writestr("META/info.json", '{"Name": "Zeri"}')
            out.writestr("WAD/Zeri.wad.client", self.wad if wad is None else wad)
            out.writestr("RAW/data/loose.bin", build([material("Loose", u32(2))]))
        return path

    def test_the_mod_is_rewritten_in_place_and_everything_else_is_kept(self):
        path = self.archive()

        self.assertEqual(int_widths.narrowable(path), 2, "counted without writing")
        before = path.read_bytes()
        self.assertEqual(int_widths.repair_archive(path), 2)

        self.assertNotEqual(path.read_bytes(), before)
        with zipfile.ZipFile(path) as fixed:
            self.assertEqual(fixed.namelist(), ["META/info.json", "WAD/Zeri.wad.client", "RAW/data/loose.bin"])
            self.assertEqual(fixed.read("META/info.json"), b'{"Name": "Zeri"}')
            wad = ModWad(fixed.read("WAD/Zeri.wad.client"))
            self.assertEqual(kind_of(fixed.read("RAW/data/loose.bin")), (U8, 2), "a bin kept as a loose file too")
        self.assertEqual(kind_of(wad.get(path_hash("data/a.bin")).data), (U8, 3))
        self.assertEqual(kind_of(wad.get(path_hash("data/b.bin")).data), (U32, 3))
        self.assertEqual(wad.get(path_hash("assets/body.tex")).data, self.texture)
        self.assertEqual(int_widths.narrowable(path), 0, "a second repair has nothing to do")
        self.assertEqual([p.name for p in self.root.iterdir()], ["Zeri.fantome"], "no copy is left beside the mod")

    def test_a_mod_with_nothing_to_narrow_is_not_touched(self):
        clean = self.root / "Clean.fantome"
        with zipfile.ZipFile(clean, "w") as out:
            out.writestr("WAD/Zeri.wad.client", wad_bytes({"data/b.bin": build([other_entry()])}))
        before = clean.read_bytes()

        self.assertEqual(int_widths.repair_archive(clean), 0)
        self.assertEqual(clean.read_bytes(), before)

    def test_a_file_it_cannot_read_or_does_not_repair_is_left_alone(self):
        broken = self.root / "Broken.fantome"
        broken.write_bytes(b"not a zip")
        package = self.archive("Zeri.modpkg")
        bad_wad = self.archive("BadWad.fantome", wad=b"RW" + bytes(10))

        for path in (broken, package, bad_wad, self.root / "Missing.fantome"):
            with self.subTest(path=path.name):
                before = path.read_bytes() if path.exists() else None
                self.assertEqual((int_widths.narrowable(path), int_widths.repair_archive(path)), (0, 0))
                self.assertEqual(path.read_bytes() if path.exists() else None, before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["BadWad.fantome", "Broken.fantome", "Zeri.modpkg"])


if __name__ == "__main__":
    unittest.main()

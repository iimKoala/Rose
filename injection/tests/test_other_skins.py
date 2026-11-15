"""The skins the user picks for other players' champions (injection/core/other_skins.py)."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from injection.baseskin import slots
from injection.baseskin.propbin import build
from injection.core import other_skins
from injection.core.stage_plan import OtherSkinStep, StagePlan, describe, prepare_plan
from injection.tests.test_skin_slots import resources_entry, skin_entry, wad_bytes
from party.discovery.skin_collector import PartySkinData
from party.integration.injection_hook import PartyInjectionHook

ANNIE = 1


def state(**fields):
    return SimpleNamespace(other_skins={}, locked_champ_id=None, hovered_champ_id=None, current_game_mode="CLASSIC", **fields)


class ChoiceTests(unittest.TestCase):
    def test_a_pick_is_kept_per_champion_and_own_forgets_it(self):
        mine = state()
        self.assertTrue(other_skins.choose(mine, ANNIE, "Annie", other_skins.SKIN, skin_id=1002))
        self.assertTrue(other_skins.choose(mine, 103, "Ahri", other_skins.DEFAULT))
        self.assertTrue(other_skins.choose(mine, 91, "Talon", other_skins.CUSTOM, mod_path="skins/91000/T.fantome"))
        self.assertEqual(other_skins.planned(mine), (
            OtherSkinStep(ANNIE, "Annie", "skin", 1002),
            OtherSkinStep(91, "Talon", "custom", 0, "skins/91000/T.fantome"),
            OtherSkinStep(103, "Ahri", "default"),
        ))

        self.assertTrue(other_skins.choose(mine, 103, "", "own"))
        self.assertEqual(other_skins.champions(mine), {ANNIE, 91})

    def test_a_pick_that_makes_no_sense_is_not_taken_and_clears_the_old_one(self):
        mine = state()
        other_skins.choose(mine, ANNIE, "Annie", other_skins.DEFAULT)
        # another champion's skin, no mod, a name that is not a file name, no champion
        self.assertFalse(other_skins.choose(mine, ANNIE, "Annie", other_skins.SKIN, skin_id=103001))
        self.assertFalse(other_skins.choose(mine, ANNIE, "Annie", other_skins.CUSTOM))
        self.assertFalse(other_skins.choose(mine, ANNIE, "..\\Annie", other_skins.DEFAULT))
        self.assertFalse(other_skins.choose(mine, 0, "Annie", other_skins.DEFAULT))
        self.assertEqual(other_skins.planned(mine), ())

    def test_nothing_is_planned_for_the_users_own_champion_or_in_rift_classic(self):
        mine = state()
        other_skins.choose(mine, ANNIE, "Annie", other_skins.DEFAULT)
        other_skins.choose(mine, 103, "Ahri", other_skins.DEFAULT)

        mine.locked_champ_id = 103
        self.assertEqual([step.champion_id for step in other_skins.planned(mine)], [ANNIE])
        mine.current_game_mode = "JADE"
        self.assertEqual(other_skins.planned(mine), ())

    def test_a_friend_whose_champion_has_a_pick_does_not_get_their_shared_skin(self):
        friends = [PartySkinData(summoner_id=7, summoner_name="friend", champion_id=ANNIE, skin_id=1005),
                   PartySkinData(summoner_id=8, summoner_name="other friend", champion_id=103, skin_id=103001)]
        manager = SimpleNamespace(enabled=True, party_state=SimpleNamespace(peers={7: 1, 8: 1}), get_party_skins=lambda: friends)
        mine = state()
        other_skins.choose(mine, ANNIE, "Annie", other_skins.DEFAULT)

        shared = PartyInjectionHook(manager, mine).get_party_skins_for_injection()

        self.assertEqual([skin.summoner_id for skin in shared], [8])


class PrepareTests(unittest.TestCase):
    """A fake game with Annie's skins 0, 1, 2 and 7, Rose's skin 2 of her, and a custom skin of the user's."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.game = self.root / "Game"
        champions = self.game / "DATA" / "FINAL" / "Champions"
        champions.mkdir(parents=True)
        (champions / "Annie.wad.client").write_bytes(wad_bytes({
            slots.skin_bin_path("annie", slot): build([skin_entry(slot, slot, "Annie"), resources_entry(slot, "Annie")])
            for slot in (0, 1, 2, 7)
        }))
        self.shipped = self.archive("1002.fantome", shows=2)
        self.mods_root = self.root / "mods"
        (self.mods_root / "skins" / "1000").mkdir(parents=True)
        self.archive("mods/skins/1000/Dark Annie.fantome", shows=0)
        mods_root = patch("party.discovery.custom_mods.get_mods_root", return_value=self.mods_root)
        mods_root.start()
        self.addCleanup(mods_root.stop)
        hook_root = patch("party.integration.injection_hook.get_mods_root", return_value=self.mods_root)
        hook_root.start()
        self.addCleanup(hook_root.stop)
        self.mods_dir = self.root / "injection"
        self.mods_dir.mkdir()
        self.injector = SimpleNamespace(game_dir=self.game, mods_dir=self.mods_dir,
                                        _resolve_zip=lambda name, **_: self.shipped if name == "skin_1002" else None)

    def archive(self, relative: str, shows: int) -> Path:
        path = self.root / relative
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META/info.json", '{"Name": "Annie"}')
            archive.writestr("WAD/Annie.wad.client", wad_bytes({
                slots.skin_bin_path("annie", 0): build([skin_entry(0, shows, "Annie"), resources_entry(0, "Annie")]),
            }))
        return path

    def slot_files(self, folder: str) -> list:
        skins = self.mods_dir / folder / "RAW" / "data" / "characters" / "annie" / "skins"
        return sorted(file.name for file in skins.iterdir())

    def test_a_shipped_skin_is_linked_and_copied_to_the_other_slots_but_its_own(self):
        names = other_skins.prepare(self.injector, OtherSkinStep(ANNIE, "Annie", other_skins.SKIN, 1002))

        self.assertEqual(names, ["other_1", "other_1_slots"])
        self.assertTrue((self.mods_dir / "other_1").exists())
        self.assertEqual(self.slot_files("other_1_slots"), ["skin1.bin", "skin7.bin"])

    def test_the_default_look_is_only_the_copies(self):
        names = other_skins.prepare(self.injector, OtherSkinStep(ANNIE, "Annie", other_skins.DEFAULT))

        self.assertEqual(names, ["other_1_slots"])
        self.assertEqual(self.slot_files("other_1_slots"), ["skin1.bin", "skin2.bin", "skin7.bin"])

    def test_a_custom_skin_is_linked_and_copied_to_every_other_slot(self):
        step = OtherSkinStep(ANNIE, "Annie", other_skins.CUSTOM, 0, "skins/1000/Dark Annie.fantome")

        self.assertEqual(other_skins.prepare(self.injector, step), ["other_1", "other_1_slots"])
        self.assertEqual(self.slot_files("other_1_slots"), ["skin1.bin", "skin2.bin", "skin7.bin"])

    def test_a_skin_that_is_gone_leaves_the_player_their_own(self):
        self.assertEqual(other_skins.prepare(self.injector, OtherSkinStep(ANNIE, "Annie", other_skins.SKIN, 1009)), [])
        gone = OtherSkinStep(ANNIE, "Annie", other_skins.CUSTOM, 0, "skins/1000/Gone.fantome")
        self.assertEqual(other_skins.prepare(self.injector, gone), [])
        self.assertEqual(other_skins.prepare(self.injector, OtherSkinStep(999, "Nobody", other_skins.DEFAULT)), [])
        self.assertEqual(list(self.mods_dir.iterdir()), [])

    def test_the_countdown_stages_what_the_injection_installs(self):
        mine = state()
        other_skins.choose(mine, ANNIE, "Annie", other_skins.SKIN, skin_id=1002)
        plan = StagePlan("party skins", other_skins.planned(mine))
        stage = self.root / "stage"
        stage.mkdir()

        staged = prepare_plan(self.injector, plan, stage)
        injected = other_skins.prepare_all(self.injector, mine)

        self.assertEqual(staged, injected)
        self.assertEqual(staged, ["other_1", "other_1_slots"])
        self.assertEqual(describe(StagePlan("skin_1", plan.steps)), " + 1 skin picked for other players")
        for name in ("skin1.bin", "skin7.bin"):
            tail = Path("other_1_slots") / "RAW" / "data" / "characters" / "annie" / "skins" / name
            self.assertEqual((stage / tail).read_bytes(), (self.mods_dir / tail).read_bytes())

    def test_one_pick_that_fails_does_not_cost_the_others(self):
        mine = state()
        other_skins.choose(mine, ANNIE, "Annie", other_skins.DEFAULT)
        other_skins.choose(mine, 103, "Ahri", other_skins.DEFAULT)
        real = other_skins.prepare

        def failing(injector, step, mods_dir=None):
            if step.champion_id == 103:
                raise OSError("disk")
            return real(injector, step, mods_dir)

        with patch.object(other_skins, "prepare", failing):
            self.assertEqual(other_skins.prepare_all(self.injector, mine), ["other_1_slots"])


class ShippedSkinsTests(unittest.TestCase):
    def test_the_skins_rose_has_a_file_for_are_listed_without_the_base_skin_and_chromas(self):
        with tempfile.TemporaryDirectory() as temp:
            champion = Path(temp) / "1"
            for skin, extension in ((1000, ".fantome"), (1002, ".fantome"), (1005, ".zip"), (1009, None), (2001, ".fantome")):
                (champion / str(skin)).mkdir(parents=True)
                if extension:
                    (champion / str(skin) / f"{skin}{extension}").write_bytes(b"")
            (champion / "1002" / "1013").mkdir()  # a chroma, under its skin
            (champion / "notes").mkdir()
            with patch("utils.core.paths.get_skins_dir", return_value=Path(temp)):
                self.assertEqual(other_skins.shipped_skin_ids(1), [1002, 1005])
                self.assertEqual(other_skins.shipped_skin_ids(77), [])


if __name__ == "__main__":
    unittest.main()

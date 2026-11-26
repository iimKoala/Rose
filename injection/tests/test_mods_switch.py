"""The fork's "Mods in game" switch: off, Rose starts no patcher, installs no mod and holds no game.

injection/core/mods_switch.py keeps it as a file in Rose's data folder. Here that folder is a temporary one,
and no LTK Manager, tray icon or game is touched.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from injection.core import mods_switch
from injection.overlay.overlay_manager import OverlayManager
from injection.overlay.process_manager import ProcessManager
from threads.handlers.injection_trigger import InjectionTrigger
from utils.integration import tray_manager


class SwitchCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.data = self.root / "Rose data"
        self.data.mkdir()
        folder = patch("utils.core.paths.get_user_data_dir", return_value=self.data)
        folder.start()
        self.addCleanup(folder.stop)
        self.arm(False)

    def arm(self, armed: bool) -> None:
        state = patch.object(mods_switch, "_armed", armed)
        state.start()
        self.addCleanup(state.stop)


class FileTests(SwitchCase):
    def test_without_a_file_mods_are_on(self):
        self.assertEqual(mods_switch.flag_file(), self.data / "mods-off.txt")
        self.assertEqual((mods_switch.is_off(), mods_switch.reason()), (False, ""))

    def test_off_keeps_the_reason_and_the_time_and_on_removes_them(self):
        self.assertTrue(mods_switch.turn_off("Riot Vanguard\ncloses the game"))
        self.assertTrue(mods_switch.is_off())
        self.assertEqual(mods_switch.reason(), "Riot Vanguard closes the game")
        lines = (self.data / "mods-off.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[1], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

        self.assertTrue(mods_switch.turn_off("   "))
        self.assertEqual(mods_switch.reason(), "switched off")

        self.assertTrue(mods_switch.turn_on())
        self.assertTrue(mods_switch.turn_on(), "no file: still on")
        self.assertEqual((mods_switch.is_off(), mods_switch.reason()), (False, ""))

    def test_a_file_saved_by_an_editor_reads_too(self):
        (self.data / "mods-off.txt").write_text("until LTK Manager is updated\r\n", encoding="utf-8-sig")
        self.assertEqual((mods_switch.is_off(), mods_switch.reason()), (True, "until LTK Manager is updated"))
        (self.data / "mods-off.txt").write_text("", encoding="utf-8")
        self.assertEqual((mods_switch.is_off(), mods_switch.reason()), (True, ""), "an empty file is off too")

    def test_a_data_folder_that_cannot_be_told_plays_with_mods_as_before(self):
        with patch("utils.core.paths.get_user_data_dir", side_effect=OSError("no profile")):
            self.assertIsNone(mods_switch.flag_file())
            self.assertEqual((mods_switch.is_off(), mods_switch.reason()), (False, ""))
            self.assertFalse(mods_switch.turn_off("x"))
            self.assertFalse(mods_switch.turn_on())


class ArmedTests(SwitchCase):
    def test_only_a_rose_that_armed_the_switch_obeys_it(self):
        """Tests and tools build the injection too: this PC's switch must never reach them"""
        mods_switch.turn_off("for this test")
        self.assertFalse(mods_switch.off_now(), "not armed: the file is not asked")
        self.arm(True)
        self.assertTrue(mods_switch.off_now())
        mods_switch.turn_on()
        self.assertFalse(mods_switch.off_now())

    def test_arming_is_what_roses_start_does(self):
        with patch.object(mods_switch, "_armed", False):
            mods_switch.arm()
            self.assertTrue(mods_switch._armed)


class InjectionGateTests(SwitchCase):
    """Every way to LTK Manager's patcher goes through these four methods of the overlay manager"""

    def setUp(self):
        super().setUp()
        tools, mods, game = self.root / "tools", self.root / "mods", self.root / "game"
        for folder in (tools, mods, game):
            folder.mkdir()
        self.overlay = OverlayManager(tools, mods, game, ProcessManager())
        for name in ("_acquire_session", "_staging_session", "_new_session", "_install_mods"):
            setattr(self.overlay, name, MagicMock(name=name, return_value=None))
        self.overlay.host = MagicMock(name="host")

    def off(self) -> None:
        mods_switch.turn_off("for this test")
        self.arm(True)

    def touched(self) -> bool:
        return any(getattr(self.overlay, name).called for name in ("_acquire_session", "_staging_session", "_new_session", "_install_mods")) \
            or bool(self.overlay.host.mock_calls)

    def test_off_no_patcher_is_started_no_mod_installed_and_no_game_held(self):
        self.off()

        self.overlay.start_patcher_early()
        self.overlay.open_staging()
        staged = self.overlay.stage_mods(self.root / "mods", ["skin_1"])
        result = self.overlay.mk_run_overlay(["skin_1"])

        self.assertFalse(self.touched(), "LTK Manager was not asked for anything")
        self.assertFalse(self.overlay._countdown_staging_open)
        self.assertIs(staged, False)
        self.assertEqual(result, 0, "as a session Rose stopped itself: no error is reported")

    def test_on_the_injection_goes_its_usual_way(self):
        self.arm(True)  # armed and no file: on

        self.overlay.open_staging()
        self.assertTrue(self.overlay._countdown_staging_open)

        self.overlay.mk_run_overlay(["skin_1"])  # the injection itself closes the staging again
        self.overlay._acquire_session.assert_called_once()


class TriggerGateTests(SwitchCase):
    def setUp(self):
        super().setUp()
        self.state = SimpleNamespace(locked_champ_id=91, hovered_champ_id=91, selected_custom_mod=None)
        self.manager = MagicMock(name="injection_manager")
        self.trigger = InjectionTrigger(MagicMock(), self.state, self.manager, MagicMock())
        self.trigger._effective_skin = MagicMock(side_effect=AssertionError("the pick was looked at"))

    def test_off_the_players_pick_is_left_alone_and_an_early_patcher_is_dropped(self):
        mods_switch.turn_off("for this test")
        self.arm(True)

        self.trigger.trigger_injection("skin_91049", 7, "Talon")

        self.manager.discard_early_patcher.assert_called_once_with()
        self.manager.inject_skin_immediately.assert_not_called()

    def test_on_the_trigger_goes_on_to_the_pick(self):
        self.arm(True)
        with self.assertRaisesRegex(AssertionError, "the pick was looked at"):
            self.trigger.trigger_injection("skin_91049", 7, "Talon")
        self.manager.discard_early_patcher.assert_not_called()


class TrayTests(SwitchCase):
    def setUp(self):
        super().setUp()
        self.tray = tray_manager.TrayManager()
        self.tray.icon = Mock()
        logger = patch.object(tray_manager, "log")
        logger.start()
        self.addCleanup(logger.stop)

    def test_the_item_is_ticked_while_mods_are_on_and_a_press_flips_it(self):
        self.assertTrue(self.tray._mods_in_game())

        self.tray._on_toggle_mods(self.tray.icon, None)

        self.assertFalse(self.tray._mods_in_game())
        self.assertEqual(mods_switch.reason(), "switched off from the tray")
        message, title = self.tray.icon.notify.call_args.args
        self.assertIn("Mods are off", message)
        self.assertEqual(title, "Rose")
        self.tray.icon.update_menu.assert_called_once()

        self.tray._on_toggle_mods(self.tray.icon, None)

        self.assertTrue(self.tray._mods_in_game())
        self.assertIn("Mods are on", self.tray.icon.notify.call_args.args[0])

    def test_the_menu_has_the_item(self):
        labels = [str(item.text) for item in self.tray._create_menu().items if getattr(item, "text", None)]
        self.assertIn("Mods in game", labels)


if __name__ == "__main__":
    unittest.main()

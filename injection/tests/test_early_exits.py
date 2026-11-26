"""The fork's guard: after two games in a row that left play within seconds of their loading screen with
Rose's mods in them, Rose turns its mods off by itself (injection/core/early_exits.py, mods_switch).

The game logs here are made of real lines of Nov 25, in a temporary folder; no game, tray or LTK Manager.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from injection.core import early_exits, mods_switch
from injection.overlay import overlay_manager
from injection.overlay.overlay_manager import OverlayManager
from injection.overlay.process_manager import ProcessManager

ENTER = "000003.433| ALWAYS|  FLOW| Switching Game State from GAMESTATE_SPAWN to GAMESTATE_GAMELOOP for reason Received Game Start Packet."
NOISE = "000003.484| ALWAYS| GAMESTATE_GAMELOOP UpdateVis"
QUIT = "000008.441| ALWAYS|  FLOW| Switching Game State from GAMESTATE_GAMELOOP to GAMESTATE_PRE_EXIT for reason Quit Game Confirmed"
CLOSED = "\n".join((ENTER, NOISE, QUIT))
PLAYED = "\n".join((ENTER, NOISE, "001803.120| ALWAYS|  FLOW| Switching Game State from GAMESTATE_GAMELOOP to GAMESTATE_ENDGAME for reason Game Over"))
KILLED = "\n".join((ENTER, NOISE))  # Rose closed it for a restart, or it crashed: no leaving line


class PlayedSecondsTests(unittest.TestCase):
    def test_the_time_between_entering_play_and_leaving_it(self):
        self.assertAlmostEqual(early_exits.played_seconds(CLOSED), 5.008, places=3)
        self.assertAlmostEqual(early_exits.played_seconds(PLAYED), 1799.687, places=3)

    def test_a_log_without_both_moments_cannot_be_told(self):
        for text in (KILLED, ENTER, "", NOISE, "\n".join((QUIT, ENTER)), "not a log at all"):
            self.assertIsNone(early_exits.played_seconds(text), text[:40])

    def test_a_line_without_its_time_cannot_be_told(self):
        self.assertIsNone(early_exits.played_seconds("\n".join((ENTER, QUIT.split("|", 1)[1]))))


class CountTests(unittest.TestCase):
    def test_two_in_a_row_with_mods_and_nothing_else_counts(self):
        guard = early_exits.EarlyExits()
        self.assertFalse(guard.game_over(2.0, True))
        self.assertFalse(guard.game_over(None, True), "cannot be told: the count stays")
        self.assertFalse(guard.game_over(2.0, False), "a game without mods says nothing about mods")
        self.assertTrue(guard.game_over(1.7, True))
        self.assertFalse(guard.game_over(2.0, True), "the count began anew")
        self.assertFalse(guard.game_over(1800.0, True), "a game that ran")
        self.assertFalse(guard.game_over(2.0, True))

    def test_a_quit_by_hand_is_not_early(self):
        guard = early_exits.EarlyExits()
        for _ in range(5):
            self.assertFalse(guard.game_over(early_exits.EARLY_EXIT_S, True), "ten seconds of play and more is a player's quit")


class GameFolderCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.game = self.root / "League of Legends" / "Game"
        self.game.mkdir(parents=True)
        self.logs = self.root / "League of Legends" / "Logs" / "GameLogs"

    def log(self, folder: str, text: str) -> None:
        (self.logs / folder).mkdir(parents=True, exist_ok=True)
        (self.logs / folder / f"{folder}_r3dlog.txt").write_text(text, encoding="utf-8")
        (self.logs / folder / f"{folder}_netlog.txt").write_text("not this one", encoding="utf-8")


class NewestLogTests(GameFolderCase):
    def test_the_newest_game_is_the_folder_whose_name_sorts_last(self):
        self.log("2026-11-25T21-12-45", PLAYED)
        self.log("2026-11-25T21-15-27", CLOSED)
        self.log("2026-11-21T17-10-56", PLAYED)

        self.assertEqual(early_exits.newest_game_log(self.game).name, "2026-11-25T21-15-27_r3dlog.txt")
        self.assertAlmostEqual(early_exits.read_played(self.game), 5.008, places=3)

    def test_no_logs_no_folder_or_no_game_folder_is_nothing(self):
        self.assertIsNone(early_exits.newest_game_log(self.game))
        self.assertIsNone(early_exits.read_played(self.game))
        self.assertIsNone(early_exits.newest_game_log(None))
        (self.logs / "2026-11-25T21-15-27").mkdir(parents=True)
        self.assertIsNone(early_exits.read_played(self.game), "a game folder without its log yet")


class GuardTests(GameFolderCase):
    """The overlay manager's part: when it looks, and what it does when the counter says so"""

    def setUp(self):
        super().setUp()
        self.data = self.root / "Rose data"
        self.data.mkdir()
        tools, mods = self.root / "tools", self.root / "mods"
        tools.mkdir()
        mods.mkdir()
        self.process_manager = ProcessManager()
        self.process_manager.stop_overlay_process = MagicMock(name="stop_overlay_process")
        self.overlay = OverlayManager(tools, mods, self.game, self.process_manager)
        self.told = []
        self.timers = []
        self.report_issue = MagicMock()
        for started in (patch("utils.core.paths.get_user_data_dir", return_value=self.data),
                        patch.object(mods_switch, "_armed", True), patch.object(mods_switch, "_tell", self.told.append),
                        patch.object(overlay_manager, "report_issue", self.report_issue),
                        patch.object(overlay_manager.threading, "Timer", self.timer)):
            started.start()
            self.addCleanup(started.stop)

    def timer(self, seconds, function, args=()):
        """Stands in for threading.Timer: the look at the log is run by the test, not two seconds later"""
        self.timers.append((seconds, function, args))
        return MagicMock()

    def game_ends(self, text: str, folder: str, with_mods: bool = True, next_phase: str = "Reconnect") -> bool:
        """One game: InProgress, then *next_phase*; its log is *text*. Whether the mods were turned off"""
        self.overlay._running_session = {"ltf": MagicMock()} if with_mods else None
        self.overlay.note_gameflow_phase("InProgress")
        self.log(folder, text)
        self.overlay.note_gameflow_phase(next_phase)
        if not self.timers:
            return False
        _seconds, function, args = self.timers.pop()
        return function(*args)

    def test_the_second_game_in_a_row_closed_at_its_start_turns_the_mods_off(self):
        self.assertFalse(self.game_ends(CLOSED, "2026-11-25T21-12-45"))
        self.assertFalse(mods_switch.is_off())

        self.assertTrue(self.game_ends(CLOSED, "2026-11-25T21-13-43"))

        self.assertTrue(mods_switch.is_off())
        self.assertIn("two games in a row", mods_switch.reason())
        self.process_manager.stop_overlay_process.assert_called_once_with()  # the reconnect must not meet the patcher
        self.assertEqual(len(self.told), 1)
        self.assertIn("Mods in game", self.told[0])
        self.assertEqual(self.report_issue.call_args.args[:2], ("MODS_SWITCHED_OFF", "warning"))

    def test_the_log_is_looked_at_a_moment_after_the_game_left_play(self):
        self.overlay.note_gameflow_phase("InProgress")
        self.assertEqual(self.timers, [], "nothing while the game runs")
        self.overlay.note_gameflow_phase("WaitingForStats")
        self.assertEqual([seconds for seconds, _f, _a in self.timers], [overlay_manager.EARLY_EXIT_LOG_WAIT_S])
        self.overlay.note_gameflow_phase("EndOfGame")
        self.assertEqual(len(self.timers), 1, "once a game")

    def test_a_game_that_ran_between_two_closed_ones_starts_the_count_anew(self):
        self.assertFalse(self.game_ends(CLOSED, "2026-11-25T21-12-45"))
        self.assertFalse(self.game_ends(PLAYED, "2026-11-25T21-13-43", next_phase="WaitingForStats"))
        self.assertFalse(self.game_ends(CLOSED, "2026-11-25T21-50-00"))
        self.assertFalse(mods_switch.is_off())

    def test_a_game_rose_closed_itself_for_a_restart_does_not_count(self):
        """Killed, so its log has no leaving line: it says nothing"""
        self.assertFalse(self.game_ends(CLOSED, "2026-11-25T21-12-45"))
        self.assertFalse(self.game_ends(KILLED, "2026-11-25T21-13-18"))
        self.assertFalse(mods_switch.is_off())
        self.assertTrue(self.game_ends(CLOSED, "2026-11-25T21-13-43"), "the count was kept")

    def test_games_without_rose_mods_never_turn_anything_off(self):
        for folder in ("2026-11-25T21-12-45", "2026-11-25T21-13-43", "2026-11-25T21-14-52"):
            self.assertFalse(self.game_ends(CLOSED, folder, with_mods=False))
        self.assertFalse(mods_switch.is_off())

    def test_a_rose_that_did_not_arm_the_switch_looks_at_nothing(self):
        with patch.object(mods_switch, "_armed", False):
            self.overlay.note_gameflow_phase("InProgress")
            self.overlay.note_gameflow_phase("Reconnect")
        self.assertEqual(self.timers, [])

    def test_with_mods_off_already_nothing_is_looked_at(self):
        mods_switch.turn_off("by hand")
        self.overlay.note_gameflow_phase("InProgress")
        self.overlay.note_gameflow_phase("Reconnect")
        self.assertEqual(self.timers, [])


if __name__ == "__main__":
    unittest.main()

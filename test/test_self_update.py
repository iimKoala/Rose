"""main/self_update.py: an installed copy downloads new versions while it runs and asks to restart when the user is free.

No network, no window, no thread: the updater, the question and Rose's state are stand-ins.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from main import self_update

V2, V3 = "2" * 40, "3" * 40


class Updater:
    """scripts/rose_update.py's stage(): the version it says is downloaded, or the error it raises"""

    def __init__(self, version=""):
        self.version, self.looks = version, 0

    def stage(self, root):
        self.looks += 1
        if isinstance(self.version, Exception):
            raise self.version
        return self.version


class WatcherCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose_selfupdate_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.state = SimpleNamespace(phase="Lobby", stop=False)
        self.updater = Updater()
        self.asked, self.answer = [], False
        self.quits = []

        def ask(version):
            self.asked.append(version)
            return self.answer

        self.watcher = self_update.UpdateWatcher(self.state, lambda: self.quits.append(True), updater=self.updater,
                                                 ask=ask, root=self.root)

    def note(self) -> bool:
        return (self.root / ".rose-restart").exists()


class AskingTests(WatcherCase):
    def test_nothing_new_asks_nothing(self):
        self.watcher.check()

        self.assertFalse(self.watcher.tell_if_free())
        self.assertEqual((self.asked, self.updater.looks), ([], 1))

    def test_a_downloaded_version_is_asked_about_when_the_user_is_free(self):
        self.updater.version = V2
        self.watcher.check()

        self.assertFalse(self.watcher.tell_if_free())
        self.assertEqual(self.asked, [V2])
        self.assertEqual((self.quits, self.note()), ([], False), "No: Rose runs on, the next start installs it")

    def test_yes_leaves_the_note_for_the_start_script_and_quits_rose(self):
        self.updater.version, self.answer = V2, True
        self.watcher.check()

        self.assertTrue(self.watcher.tell_if_free())
        self.assertEqual((self.quits, self.note()), ([True], True))

    def test_it_waits_while_a_game_a_queue_or_champion_select_is_on(self):
        self.updater.version, self.answer = V2, True
        self.watcher.check()

        for phase in ("Matchmaking", "ReadyCheck", "ChampSelect", "GameStart", "InProgress", "Reconnect", "WaitingForStats", "PreEndOfGame"):
            self.state.phase = phase
            self.assertFalse(self.watcher.tell_if_free(), phase)
        self.assertEqual(self.asked, [])

        self.state.phase = "EndOfGame"  # after the game
        self.assertTrue(self.watcher.tell_if_free())
        self.assertEqual(self.asked, [V2])

    def test_the_client_closed_or_on_its_home_screen_counts_as_free(self):
        self.updater.version = V2
        self.watcher.check()
        for phase in (None, "None", "Lobby"):
            self.state.phase = phase
            self.watcher.told = ""
            self.assertFalse(self.watcher.tell_if_free())
        self.assertEqual(self.asked, [V2, V2, V2])

    def test_one_question_a_version(self):
        self.updater.version = V2
        self.watcher.check()
        self.watcher.tell_if_free()
        self.watcher.check()
        self.watcher.tell_if_free()
        self.assertEqual(self.asked, [V2], "No is remembered")

        self.updater.version = V3
        self.watcher.check()
        self.watcher.tell_if_free()
        self.assertEqual(self.asked, [V2, V3], "a newer version is news again")

    def test_a_game_found_while_the_question_stood_open_is_not_interrupted(self):
        self.updater.version = V2
        self.watcher.check()

        def yes_but_later(version):
            self.state.phase = "ChampSelect"
            return True

        self.watcher.ask = yes_but_later
        self.assertFalse(self.watcher.tell_if_free())
        self.assertEqual((self.quits, self.note()), ([], False))

    def test_github_out_of_reach_is_looked_past(self):
        self.updater.version = OSError("no internet")

        self.watcher.check()

        self.assertEqual(self.watcher.ready, "")
        self.assertFalse(self.watcher.tell_if_free())


class QuestionTests(unittest.TestCase):
    def test_the_question_is_a_yes_or_no_window_on_top(self):
        with patch.object(self_update.ctypes, "windll", create=True) as windows:
            windows.user32.MessageBoxW.return_value = 6  # Yes
            self.assertTrue(self_update.ask_restart(V2))
            windows.user32.MessageBoxW.return_value = 7  # No
            self.assertFalse(self_update.ask_restart(V2))

        _owner, text, title, flags = windows.user32.MessageBoxW.call_args.args
        self.assertIn("Restart Rose now", text)
        self.assertIn("22222222", title)
        self.assertTrue(flags & 0x4 and flags & 0x40000, "Yes/No, and on top of other windows")


class StartTests(WatcherCase):
    def installed(self) -> None:
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "rose_update.py").write_text("def stage(root):\n    return ''\n", encoding="utf-8")

    def started(self):
        with patch.object(self_update.UpdateWatcher, "start") as thread_start:
            watcher = self_update.start(self.state, lambda: None, root=self.root)
        return watcher, thread_start.called

    def test_an_installed_copy_gets_a_watcher(self):
        self.installed()

        watcher, running = self.started()

        self.assertTrue(running)
        self.assertEqual(watcher.updater.stage(self.root), "", "the copy's own updater script is the one used")

    def test_a_developers_copy_a_built_rose_and_a_copy_without_updater_get_none(self):
        self.assertEqual(self.started(), (None, False), "no updater script")
        self.installed()
        (self.root / ".git").mkdir()
        self.assertEqual(self.started(), (None, False), "a developer's copy")
        (self.root / ".git").rmdir()
        with patch.object(self_update.sys, "frozen", True, create=True):
            self.assertEqual(self.started(), (None, False), "a built Rose.exe")

    def test_a_note_nobody_read_is_removed_at_the_start(self):
        """Left by a Rose that was not started by Start Rose.bat: it must not restart Rose at its next quit"""
        (self.root / ".rose-restart").write_text(V2, encoding="utf-8")

        self.started()

        self.assertFalse(self.note())

    def test_nothing_here_can_keep_rose_from_starting(self):
        self.installed()
        with patch.object(self_update, "load_updater", side_effect=SyntaxError("a broken script")):
            self.assertIsNone(self_update.start(self.state, lambda: None, root=self.root))

    def test_the_question_is_not_asked_while_a_game_runs_even_at_the_first_look(self):
        self.assertTrue(self_update.BUSY_PHASES >= {"ChampSelect", "InProgress", "Matchmaking"})
        self.assertNotIn("EndOfGame", self_update.BUSY_PHASES)
        self.assertNotIn("Lobby", self_update.BUSY_PHASES)


if __name__ == "__main__":
    unittest.main()

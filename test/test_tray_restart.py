"""The tray's Restart of a copy installed from GitHub goes through Start Rose.bat, so the updater runs.

Until Nov 23 it started `python main.py` itself: a version published meanwhile stayed downloaded and
waiting, whatever the number of restarts. No process is started here: the helper, Rose's parents and the
temporary folder are stand-ins.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main
from main import self_update


def process(name, *cmdline, error=None):
    def read(value):
        def reader():
            if error is not None:
                raise error
            return value
        return reader
    return SimpleNamespace(name=read(name), cmdline=read(list(cmdline)))


PYTHON = process("python.exe", r"C:\Rose\.venv\Scripts\python.exe", "main.py")
START_SCRIPT = process("cmd.exe", r"C:\WINDOWS\system32\cmd.exe", "/c", r'"C:\Rose\Start Rose.bat" ')
EXPLORER = process("explorer.exe", r"C:\WINDOWS\Explorer.EXE")


class CopyCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose tray restart "))  # a space, as in "Start Rose.bat"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        note_left = patch.object(self_update, "_note_left", False)
        note_left.start()
        self.addCleanup(note_left.stop)

    def installed(self) -> None:
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "rose_update.py").write_text("def stage(root):\n    return ''\n", encoding="utf-8")
        (self.root / "Start Rose.bat").write_text("@echo off\n", encoding="utf-8")

    def note(self) -> bool:
        return (self.root / ".rose-restart").exists()


class StartsThroughScriptTests(CopyCase):
    def test_an_installed_copy_does(self):
        self.installed()

        self.assertTrue(self_update.starts_through_script(self.root))

    def test_a_developers_copy_and_a_built_rose_do_not(self):
        self.installed()
        with patch.object(self_update.sys, "frozen", True, create=True):
            self.assertFalse(self_update.starts_through_script(self.root), "a built Rose.exe")
        (self.root / ".git").mkdir()
        self.assertFalse(self_update.starts_through_script(self.root), "a developer's copy")

    def test_a_copy_without_its_updater_or_its_start_script_does_not(self):
        self.assertFalse(self_update.starts_through_script(self.root))
        self.installed()
        (self.root / "Start Rose.bat").unlink()
        self.assertFalse(self_update.starts_through_script(self.root), "no start script to go through")


class StartScriptWaitsTests(unittest.TestCase):
    def waits(self, *parents) -> bool:
        return self_update.start_script_waits(SimpleNamespace(parents=lambda: list(parents)))

    def test_the_start_script_among_the_parents_waits(self):
        self.assertTrue(self.waits(PYTHON, START_SCRIPT, EXPLORER), "the .venv's python.exe stands in between")

    def test_a_rose_started_another_way_has_no_script_waiting(self):
        self.assertFalse(self.waits(PYTHON, EXPLORER), "started by the old restart helper, which is gone")
        self.assertFalse(self.waits(PYTHON, process("cmd.exe", r"C:\WINDOWS\system32\cmd.exe")), "a prompt, python typed in")
        self.assertFalse(self.waits())

    def test_a_parent_that_cannot_be_read_is_looked_past(self):
        self.assertTrue(self.waits(process("?", error=PermissionError("denied")), START_SCRIPT))

    def test_parents_that_cannot_be_listed_count_as_no_script(self):
        def parents():
            raise OSError("gone")

        self.assertFalse(self_update.start_script_waits(SimpleNamespace(parents=parents)))


class TrayRestartTests(CopyCase):
    def restart(self, waits: bool):
        """(what _schedule_restart answered, the helper's batch file text or None when no helper was started)"""
        temp = self.root / "temp"
        temp.mkdir(exist_ok=True)
        with patch("subprocess.Popen") as popen, patch("tempfile.gettempdir", return_value=str(temp)), \
                patch.object(self_update, "start_script_waits", return_value=waits):
            answer = main._schedule_restart(root=self.root)
        if not popen.called:
            return answer, None
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], ["cmd", "/c"])
        return answer, Path(command[2]).read_text(encoding="utf-8")

    def test_the_start_script_that_waits_gets_the_note_and_no_helper_is_started(self):
        self.installed()

        answer, helper = self.restart(waits=True)

        self.assertEqual((answer, helper, self.note()), (True, None, True))

    def test_without_a_waiting_script_the_helper_starts_rose_through_it(self):
        self.installed()

        answer, helper = self.restart(waits=False)

        self.assertTrue(answer)
        self.assertFalse(self.note(), "nobody would read it")
        script = self.root / "Start Rose.bat"
        self.assertIn(f'start "Rose" /D "{self.root}" cmd /c ""{script}""', helper)
        self.assertNotIn("main.py", helper, "never past the updater")

    def test_a_developers_copy_starts_main_py_as_before(self):
        self.installed()
        (self.root / ".git").mkdir()

        answer, helper = self.restart(waits=True)

        self.assertTrue(answer)
        self.assertFalse(self.note())
        self.assertIn(f'/D "{self.root}"', helper)
        self.assertIn('"main.py"', helper)
        self.assertNotIn("Start Rose.bat", helper)

    def test_a_note_the_tray_left_while_rose_was_starting_is_not_removed_as_one_nobody_read(self):
        """Restart clicked before the watcher starts: start() removes notes nobody read, not this one"""
        self.installed()
        self.restart(waits=True)

        with patch.object(self_update.UpdateWatcher, "start"):
            self_update.start(SimpleNamespace(phase="Lobby", stop=True), lambda: None, root=self.root)

        self.assertTrue(self.note())


if __name__ == "__main__":
    unittest.main()

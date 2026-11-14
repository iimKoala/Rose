"""mod_checker runs rose-mod-check.exe (LTK Manager's rules, without LTK Manager) and reads its verdict; it repairs too."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from injection.tools import mod_checker

HEALTHY = {"health": "healthy", "fixable": 0, "counts": {"fatals": 0, "errors": 0, "warnings": 0, "infos": 0}, "rules": []}
SKINHACK = {"rule": "bin/skinhack", "title": "Another skin's model", "description": "This base skin uses the mesh of another skin.",
            "severity": "error", "count": 1, "fixable": 0}


class CheckModFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose_modcheck_"))
        self.checker = self.root / "rose-mod-check.exe"
        self.checker.write_bytes(b"MZ")
        self.archive = self.root / "Talon Mahoraga.fantome"
        self.archive.write_bytes(b"PK")
        self.calls = []
        patcher = patch.object(mod_checker, "CHECKER", self.checker)
        patcher.start()
        self.addCleanup(patcher.stop)

    def answer(self, stdout="", code=0, error=None):
        def run(command, **kwargs):
            self.calls.append((command, kwargs))
            if error is not None:
                raise error
            return SimpleNamespace(returncode=code, stdout=stdout.encode("utf-8"), stderr=b"")
        return patch.object(mod_checker.subprocess, "run", run)

    def test_a_verdict_is_read_from_the_last_line(self):
        with self.answer("starting\n" + json.dumps(HEALTHY) + "\n"):
            self.assertEqual(mod_checker.check_mod_file(self.archive, r"C:\Riot Games\League of Legends\Game"), HEALTHY)

    def test_the_league_folder_is_the_parent_of_game(self):
        with self.answer(json.dumps(HEALTHY)):
            mod_checker.check_mod_file(self.archive, r"C:\Riot Games\League of Legends\Game")
        command, kwargs = self.calls[0]
        self.assertEqual(command, [str(self.checker), str(self.archive), "--league", str(Path(r"C:\Riot Games\League of Legends"))])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], mod_checker.CHECK_TIMEOUT_S)

    def test_no_game_folder_runs_without_league(self):
        with self.answer(json.dumps(HEALTHY)):
            mod_checker.check_mod_file(self.archive, None)
        self.assertEqual(self.calls[0][0], [str(self.checker), str(self.archive)])

    def test_a_missing_checker_gives_no_verdict(self):
        self.checker.unlink()
        with self.answer(json.dumps(HEALTHY)):
            self.assertIsNone(mod_checker.check_mod_file(self.archive))
        self.assertEqual(self.calls, [])

    def test_an_unreadable_mod_gives_no_verdict(self):
        with self.answer(json.dumps({"error": "not a zip"}), code=1):
            self.assertIsNone(mod_checker.check_mod_file(self.archive))

    def test_output_that_is_not_json_gives_no_verdict(self):
        with self.answer("thread 'main' panicked", code=101):
            self.assertIsNone(mod_checker.check_mod_file(self.archive))

    def test_no_output_gives_no_verdict(self):
        with self.answer(""):
            self.assertIsNone(mod_checker.check_mod_file(self.archive))

    def test_a_timeout_gives_no_verdict(self):
        with self.answer(error=subprocess.TimeoutExpired("rose-mod-check", 120)):
            self.assertIsNone(mod_checker.check_mod_file(self.archive))

    def test_a_program_that_cannot_start_gives_no_verdict(self):
        with self.answer(error=OSError("blocked")):
            self.assertIsNone(mod_checker.check_mod_file(self.archive))


class RejectedTests(unittest.TestCase):
    def test_an_unrepairable_error_is_rejected(self):
        self.assertEqual(mod_checker.rejected({"rules": [SKINHACK]}), [
            {"rule": "bin/skinhack", "title": "Another skin's model", "description": "This base skin uses the mesh of another skin."}])

    def test_a_fatal_ltk_manager_can_repair_is_kept(self):
        rule = {"rule": "bin/property-type", "title": "Meta property type mismatch", "description": "",
                "severity": "fatal", "count": 28, "fixable": 28}
        self.assertEqual(mod_checker.rejected({"rules": [rule]}), [])

    def test_a_partly_repairable_error_is_rejected(self):
        self.assertEqual(len(mod_checker.rejected({"rules": [dict(SKINHACK, count=3, fixable=2)]})), 1)

    def test_warnings_and_infos_are_not_rejected(self):
        rules = [dict(SKINHACK, severity="warning"), dict(SKINHACK, severity="info")]
        self.assertEqual(mod_checker.rejected({"rules": rules}), [])

    def test_a_verdict_without_rules_rejects_nothing(self):
        self.assertEqual(mod_checker.rejected(HEALTHY), [])
        self.assertEqual(mod_checker.rejected({}), [])


class RepairModFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose_modrepair_"))
        self.checker = self.root / "rose-mod-check.exe"
        self.checker.write_bytes(b"MZ")
        self.archive = self.root / "Talon Mahoraga.fantome"
        self.archive.write_bytes(b"original")
        self.calls = []
        patcher = patch.object(mod_checker, "CHECKER", self.checker)
        patcher.start()
        self.addCleanup(patcher.stop)

    def repairing(self, repaired, writes=True):
        """A checker that applies *repaired* fixes and writes the copy (unless not *writes*)"""
        def run(command, **kwargs):
            self.calls.append(command)
            copy = Path(command[command.index("--repair") + 1])
            if writes and repaired:
                copy.write_bytes(b"repaired")
            verdict = dict(HEALTHY, repaired=repaired, output=str(copy) if repaired else None)
            return SimpleNamespace(returncode=0, stdout=json.dumps(verdict).encode("utf-8"), stderr=b"")
        return patch.object(mod_checker.subprocess, "run", run)

    def leftovers(self):
        return [p.name for p in self.root.iterdir() if p.name.startswith(mod_checker.REPAIR_TEMP_PREFIX)]

    def test_a_repaired_copy_replaces_the_mod(self):
        with self.repairing(28):
            verdict = mod_checker.repair_mod_file(self.archive, None)
        self.assertEqual(verdict["repaired"], 28)
        self.assertEqual(self.archive.read_bytes(), b"repaired")
        self.assertEqual(self.leftovers(), [])

    def test_the_copy_waits_beside_the_mod_under_a_temporary_name(self):
        with self.repairing(1):
            mod_checker.repair_mod_file(self.archive, None)
        copy = Path(self.calls[0][self.calls[0].index("--repair") + 1])
        self.assertEqual(copy.parent, self.archive.parent)
        self.assertTrue(copy.name.startswith(".rose-import-") and copy.name.endswith(".tmp"), copy.name)

    def test_nothing_to_repair_leaves_the_mod_alone(self):
        with self.repairing(0):
            verdict = mod_checker.repair_mod_file(self.archive, None)
        self.assertEqual(verdict["repaired"], 0)
        self.assertEqual(self.archive.read_bytes(), b"original")
        self.assertEqual(self.leftovers(), [])

    def test_a_repair_that_wrote_no_copy_keeps_the_mod(self):
        with self.repairing(5, writes=False):
            self.assertIsNone(mod_checker.repair_mod_file(self.archive, None))
        self.assertEqual(self.archive.read_bytes(), b"original")

    def test_a_failed_repair_keeps_the_mod_and_removes_the_copy(self):
        def run(command, **kwargs):
            Path(command[command.index("--repair") + 1]).write_bytes(b"half written")
            return SimpleNamespace(returncode=1, stdout=b'{"error": "Failed to edit"}', stderr=b"")
        with patch.object(mod_checker.subprocess, "run", run):
            self.assertIsNone(mod_checker.repair_mod_file(self.archive, None))
        self.assertEqual(self.archive.read_bytes(), b"original")
        self.assertEqual(self.leftovers(), [])

    def test_a_modpkg_is_not_repaired(self):
        modpkg = self.root / "Leona.modpkg"
        modpkg.write_bytes(b"package")
        with self.repairing(3):
            self.assertIsNone(mod_checker.repair_mod_file(modpkg, None))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

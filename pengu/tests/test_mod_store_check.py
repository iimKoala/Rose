"""The Mod store's check of a fresh download: a mod LTK Manager will turn off
is deleted before the user is asked where it goes, except one only the
skinhack rule stands on, which the install judges once it has matched the skin
to the base skin."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pengu.communication import message_handler, mod_store_handlers

SKINHACK = {"rule": "bin/skinhack", "title": "Skinhack",
            "description": "A base skin that uses the mesh or the name of another skin of its champion"}
BANK = {"rule": "audio/bank-id", "title": "Bank", "description": "An audio bank the game will not load"}


class ModStoreCheckTests(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.downloads = Path(temp_dir.name) / "store-downloads"
        self.downloads.mkdir()
        self.outside = Path(temp_dir.name) / "elsewhere.fantome"
        self.outside.write_bytes(b"mod")
        self.file = self.downloads / "32d05cc135b5484fa4b46b465327c893.fantome"
        self.file.write_bytes(b"mod")
        downloads_dir = patch.object(mod_store_handlers, "store_downloads_dir", return_value=self.downloads)
        downloads_dir.start()
        self.addCleanup(downloads_dir.stop)

    def handler(self, verdict, phase="Lobby", injecting=False):
        overlay = MagicMock()
        overlay.check_mod.return_value = verdict  # Rose's checker; None: it did not run
        instance = object.__new__(message_handler.MessageHandler)
        instance.injection_manager = SimpleNamespace(injector=SimpleNamespace(overlay_manager=overlay),
                                                     _injection_in_progress=injecting)
        instance.shared_state = SimpleNamespace(phase=phase)
        instance.sent = []
        instance._send_response = lambda message: instance.sent.append(json.loads(message))
        return instance

    def check(self, verdict, file=None, **state):
        instance = self.handler(verdict, **state)
        instance._handle_mod_store_check({"requestId": 7, "file": str(file or self.file)})
        self.assertEqual(len(instance.sent), 1)
        answer = instance.sent[0]
        self.assertEqual((answer["type"], answer["requestId"]), ("mod-store-check-response", 7))
        return instance, answer

    def test_a_healthy_download_is_kept(self):
        verdict = {"health": "healthy", "repaired": 0, "problems": []}

        instance, answer = self.check(verdict)

        instance.injection_manager.injector.overlay_manager.check_mod.assert_called_once_with(self.file, self.file.stem)
        self.assertEqual((answer["success"], answer["health"]), (True, verdict))
        self.assertNotIn("baseSkinPending", answer)
        self.assertTrue(self.file.exists())

    def test_a_download_only_the_skinhack_rule_stands_on_is_kept_for_the_install(self):
        """The Talon skin of Nov 23: 5859 problems repaired, the skinhack rule
        left. The install matches it to the base skin, then judges it"""
        verdict = {"health": "repairable", "repaired": 5859, "problems": [SKINHACK]}

        _, answer = self.check(verdict)

        self.assertEqual((answer["success"], answer["health"]), (True, verdict))
        self.assertIs(answer["baseSkinPending"], True)
        self.assertNotIn("error", answer)
        self.assertTrue(self.file.exists(), "the install still needs the file")

    def test_a_problem_the_base_skin_fix_does_not_change_deletes_the_download(self):
        _, answer = self.check({"health": "unrepairable", "repaired": 0, "problems": [BANK]})

        self.assertFalse(answer["success"])
        self.assertIn("An audio bank the game will not load", answer["error"])
        self.assertFalse(self.file.exists())

    def test_with_the_skinhack_rule_the_other_problem_is_the_reason(self):
        """The skinhack rule may not stand after the install: the answer names
        what will"""
        _, answer = self.check({"health": "unrepairable", "repaired": 0, "problems": [SKINHACK, BANK]})

        self.assertFalse(answer["success"])
        self.assertIn("An audio bank the game will not load", answer["error"])
        self.assertNotIn("skinhack", answer["error"])
        self.assertNotIn("baseSkinPending", answer)
        self.assertFalse(self.file.exists())

    def test_a_check_that_did_not_run_keeps_the_download(self):
        _, answer = self.check(None)

        self.assertEqual((answer["success"], answer["health"]), (True, None))
        self.assertTrue(self.file.exists())

    def test_no_check_while_a_game_wants_ltk_manager(self):
        for state in ({"phase": "ChampSelect"}, {"injecting": True}):
            with self.subTest(state):
                instance, answer = self.check({"health": "unrepairable", "problems": [BANK]}, **state)

                instance.injection_manager.injector.overlay_manager.check_mod.assert_not_called()
                self.assertEqual((answer["success"], answer["health"]), (True, None))
                self.assertTrue(self.file.exists())

    def test_a_file_outside_the_store_downloads_is_not_checked(self):
        instance, answer = self.check({"health": "healthy", "problems": []}, file=self.outside)

        instance.injection_manager.injector.overlay_manager.check_mod.assert_not_called()
        self.assertFalse(answer["success"])
        self.assertTrue(self.outside.exists())


if __name__ == "__main__":
    unittest.main()

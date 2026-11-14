"""The reconnect screen's drop-down: leaving some of a game's mods out of the game the player reconnects to.
A fake bridge stands in for LTK Manager; no game, no client."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from injection.overlay.overlay_manager import OverlayManager
from injection.tests.test_ltf_session import LtfSessionTestCase
from injection.tools.bridge import BridgeCommandError


class ReconnectChoiceTests(LtfSessionTestCase):
    def play(self, client):
        """Run a game session with two mods. *client* stands for the reconnect screen's requests: it runs in
        another thread (as Rose's bridge to the client does) once the session serves the game, and the
        game is over when it returns. Returns (the session's exit code, what *client* returned)."""
        mods = [self.make_mod(), self.make_mod("map-1", "Rift of the Unbound")]
        ended = threading.Event()
        seen = {}

        def other_thread():
            try:
                self.wait(lambda: self.overlay.reconnect_mods() is not None)
                seen["value"] = client()
            except BaseException as e:
                seen["error"] = e
            finally:
                ended.set()

        thread = threading.Thread(target=other_thread)
        thread.start()
        code = self.overlay.mk_run_overlay(mods, stop_callback=ended.is_set)
        thread.join()
        if "error" in seen:
            raise seen["error"]
        return code, seen["value"]

    @staticmethod
    def wait(done, seconds=5.0):
        deadline = time.monotonic() + seconds
        while not done():
            if time.monotonic() > deadline:
                raise AssertionError("timed out")
            time.sleep(0.01)

    def listed(self):
        """Ask until the session's thread has read the mods, as the drop-down does."""
        self.wait(lambda: self.overlay.reconnect_mods()["mods"] is not None)
        return {mod["name"]: mod for mod in self.overlay.reconnect_mods()["mods"]}

    def leave_out(self, mod_id):
        """Choose a mod and wait until the session has dealt with it. Returns (the answer, the commands
        LTK Manager got meanwhile, without the status polls)."""
        before = len(self.bridge.calls)
        answer = self.overlay.leave_out_on_reconnect([mod_id])
        self.wait(lambda: self.overlay.reconnect_mods()["status"] != "applying")
        return answer, [call for call in self.bridge.calls[before:] if call[0] != "patcher_status"]

    def test_no_game_session_means_nothing_to_choose(self):
        self.assertIsNone(self.overlay.reconnect_mods())
        self.assertEqual(self.overlay.leave_out_on_reconnect(["anything"]), "unknown")

    def test_the_drop_down_lists_this_games_mods_by_name(self):
        code, mods = self.play(self.listed)

        self.assertEqual(code, 0)
        self.assertEqual({name: mod["off"] for name, mod in mods.items()},
                         {"Eternal Aspect Leona": False, "Rift of the Unbound": False})
        self.assertIsNone(self.overlay.reconnect_mods())  # the game is over

    def test_a_chosen_mod_is_turned_off_and_the_overlay_is_built_again(self):
        def client():
            leona = self.listed()["Eternal Aspect Leona"]["id"]
            answer, commands = self.leave_out(leona)
            return leona, answer, commands, self.overlay.reconnect_mods()

        code, (leona, answer, commands, state) = self.play(client)

        self.assertEqual(answer, "applying")
        self.assertEqual(commands, [("stop_patcher",), ("toggle", leona, False), ("start_patcher",)])
        self.assertEqual(state["status"], "ready")
        self.assertEqual({mod["name"]: mod["off"] for mod in state["mods"]},
                         {"Eternal Aspect Leona": True, "Rift of the Unbound": False})
        # and the session ends as any other: Rose's mods removed, nothing reported
        self.assertEqual(code, 0)
        self.assertEqual(self.bridge.library_entries, [])
        self.assertEqual(self.state()["installed"], {})
        self.assertEqual(self.reported_codes(), [])

    def test_a_mod_that_is_already_off_or_not_in_this_game_is_refused(self):
        def client():
            leona = self.listed()["Eternal Aspect Leona"]["id"]
            self.leave_out(leona)
            return self.leave_out(leona), self.leave_out("not-in-this-game")

        _, (again, stranger) = self.play(client)

        self.assertEqual(again, ("unknown", []))
        self.assertEqual(stranger, ("unknown", []))

    def test_a_running_game_is_never_touched(self):
        def client():
            leona = self.listed()["Eternal Aspect Leona"]["id"]
            with patch.object(OverlayManager, "_running_game", return_value=object()):
                return self.leave_out(leona), self.overlay.reconnect_mods()["status"]

        _, ((answer, commands), status) = self.play(client)

        self.assertEqual((answer, commands, status), ("game-running", [], ""))

    def test_a_mod_ltk_manager_will_not_turn_off_is_reported_and_the_patcher_runs_again(self):
        def client():
            leona = self.listed()["Eternal Aspect Leona"]["id"]
            real = self.bridge.toggle

            def toggle(target, enabled=True):
                if target == leona and not enabled:
                    raise BridgeCommandError("toggle failed: refused")
                return real(target, enabled)

            self.bridge.toggle = toggle
            try:
                _, commands = self.leave_out(leona)
            finally:
                self.bridge.toggle = real
            return commands, self.overlay.reconnect_mods()

        _, (commands, state) = self.play(client)

        self.assertEqual(commands, [("stop_patcher",), ("start_patcher",)])
        self.assertEqual(state["status"], "failed")
        self.assertEqual({mod["name"]: mod["off"] for mod in state["mods"]},
                         {"Eternal Aspect Leona": False, "Rift of the Unbound": False})

    def test_a_library_that_cannot_be_read_is_asked_again(self):
        def client():
            self.bridge.library_fails = True
            reads = self.bridge.library_reads
            self.assertIsNone(self.overlay.reconnect_mods()["mods"])
            self.wait(lambda: self.bridge.library_reads > reads)  # the session's thread tried
            still_none = self.overlay.reconnect_mods()["mods"]
            self.bridge.library_fails = False
            return still_none, sorted(self.listed())

        _, (still_none, names) = self.play(client)

        self.assertIsNone(still_none)
        self.assertEqual(names, ["Eternal Aspect Leona", "Rift of the Unbound"])

    def test_only_roses_mods_of_this_game_are_listed(self):
        """What Rose imported and the saved mods it switched on; never the user's own LTK Manager mods"""
        library = [{"id": "a", "displayName": "Imported skin", "enabled": True},
                   {"id": "b", "name": "Saved map", "enabled": True},
                   {"id": "c", "displayName": "The user's own mod", "enabled": False}]
        ltf = SimpleNamespace(bridge=SimpleNamespace(library=lambda: library),
                              imports={"a": None}, switched_on={"b": "Saved map"})

        self.assertEqual(OverlayManager._session_mods({"ltf": ltf}),
                         [{"id": "a", "name": "Imported skin", "off": False},
                          {"id": "b", "name": "Saved map", "off": False}])

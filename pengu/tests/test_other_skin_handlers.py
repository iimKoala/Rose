"""The messages of the ROSE-OtherSkins panel (pengu/communication/other_skin_handlers.py)."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from injection.core import other_skins
from injection.core.stage_plan import OtherSkinStep
from pengu.communication.other_skin_handlers import MAX_CHAMPIONS, OtherSkinHandlersMixin

MODS_ROOT = Path("C:/mods")


class Handler(OtherSkinHandlersMixin):
    """The mixin with what it needs of MessageHandler: one saved custom skin of Annie's, and the client's
    champion names."""

    def __init__(self, connected=True):
        self.sent = []
        self.shared_state = SimpleNamespace(other_skins={}, locked_champ_id=None, hovered_champ_id=None, current_game_mode=None)
        entries = {1: [SimpleNamespace(path=MODS_ROOT / "skins" / "1000" / "Dark Annie.fantome", display_name="Dark Annie", mod_name="dark")]}
        self.mod_storage = SimpleNamespace(mods_root=MODS_ROOT, list_mods_for_champion=lambda champion_id: entries.get(champion_id, []))
        summary = [{"id": -1, "alias": "None"}, {"id": 1, "alias": "Annie"}, {"id": 62, "alias": "MonkeyKing"}]
        self.skin_scraper = SimpleNamespace(lcu=SimpleNamespace(ok=connected, get=lambda path: summary))

    def _send_response(self, message):
        self.sent.append(json.loads(message))

    def ask(self, **payload):
        self.assertTrue(self._route_other_skin_message(payload["type"], payload))
        return self.sent[-1]

    assertTrue = unittest.TestCase().assertTrue


@patch.object(other_skins, "shipped_skin_ids", lambda champion_id: [1002, 1005] if champion_id == 1 else [])
class OtherSkinHandlersTests(unittest.TestCase):
    def test_the_list_says_what_each_champion_can_be_given_and_what_is_picked(self):
        handler = Handler()
        handler.shared_state.other_skins = {62: OtherSkinStep(62, "MonkeyKing", "default")}

        answer = handler.ask(type="other-skins-list", requestId="r1", championIds=["x", 0, 1, 62])

        self.assertEqual(answer["type"], "other-skins-list-response")
        self.assertEqual(answer["requestId"], "r1")
        self.assertEqual(answer["champions"]["1"], {
            "skins": [1002, 1005],
            "mods": [{"name": "Dark Annie", "path": "skins/1000/Dark Annie.fantome"}],
            "choice": {"kind": "own"},
        })
        self.assertEqual(answer["champions"]["62"]["choice"], {"kind": "default", "skinId": 0, "modPath": ""})
        self.assertNotIn("0", answer["champions"])

    def test_the_list_is_never_longer_than_a_game_has_players(self):
        answer = Handler().ask(type="other-skins-list", championIds=list(range(1, 40)))
        self.assertEqual(len(answer["champions"]), MAX_CHAMPIONS)

    def test_a_pick_rose_offers_is_remembered_under_the_champions_file_name(self):
        handler = Handler()

        answer = handler.ask(type="other-skin-set", requestId="r2", championId=1, kind="skin", skinId=1005)

        self.assertEqual((answer["ok"], answer["championId"], answer["requestId"]), (True, 1, "r2"))
        self.assertEqual(answer["choice"], {"kind": "skin", "skinId": 1005, "modPath": ""})
        self.assertEqual(handler.shared_state.other_skins, {1: OtherSkinStep(1, "Annie", "skin", 1005)})

        handler.ask(type="other-skin-set", championId=1, kind="custom", modPath="skins/1000/Dark Annie.fantome")
        self.assertEqual(handler.shared_state.other_skins[1], OtherSkinStep(1, "Annie", "custom", 0, "skins/1000/Dark Annie.fantome"))

        handler.ask(type="other-skin-set", championId=62, kind="default")
        self.assertEqual(handler.shared_state.other_skins[62], OtherSkinStep(62, "MonkeyKing", "default"))

    def test_what_rose_does_not_offer_is_refused_and_the_pick_stays_as_it_was(self):
        handler = Handler()
        handler.ask(type="other-skin-set", championId=1, kind="default")
        refused = [
            dict(kind="skin", skinId=1009),                                   # a skin Rose has no file for
            dict(kind="skin", skinId=103001),                                 # another champion's skin
            dict(kind="custom", modPath="skins/1000/Other.fantome"),          # not one of this champion's saved skins
            dict(kind="custom", modPath="../../Windows/system32/x.fantome"),
        ]
        for pick in refused:
            answer = handler.ask(type="other-skin-set", championId=1, **pick)
            self.assertFalse(answer["ok"], pick)
            self.assertEqual(answer["choice"]["kind"], "default")
        self.assertFalse(handler.ask(type="other-skin-set", championId=999, kind="default")["ok"])  # a champion the client does not know

    def test_own_forgets_the_pick_even_when_the_client_is_gone(self):
        handler = Handler(connected=False)
        handler.shared_state.other_skins = {1: OtherSkinStep(1, "Annie", "default")}

        self.assertFalse(handler.ask(type="other-skin-set", championId=62, kind="default")["ok"])
        answer = handler.ask(type="other-skin-set", championId=1, kind="own")

        self.assertTrue(answer["ok"])
        self.assertEqual(answer["choice"], {"kind": "own"})
        self.assertEqual(handler.shared_state.other_skins, {})

    def test_a_message_that_cannot_be_read_still_gets_an_answer(self):
        answer = Handler().ask(type="other-skin-set", championId="not a number", kind="skin")
        self.assertFalse(answer["ok"])

    def test_other_messages_are_left_to_the_other_handlers(self):
        handler = Handler()
        self.assertFalse(handler._route_other_skin_message("party-get-state", {}))
        self.assertEqual(handler.sent, [])


if __name__ == "__main__":
    unittest.main()

"""The party panel's switch for a friend's skin, from the plugin's message to the party manager."""

import asyncio
import threading
import unittest
from types import SimpleNamespace

from pengu.communication import message_handler
from pengu.communication.party_mod_handlers import PartyModHandlersMixin


class PartyModHandlerTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.loop.call_soon_threadsafe(self.loop.stop), thread.join(2), self.loop.close()))
        self.switched = []

        async def set_peer_skin_off(summoner_id, off):
            self.switched.append((summoner_id, off))

        self.handler = PartyModHandlersMixin()
        self.handler.shared_state = SimpleNamespace(party_manager=SimpleNamespace(set_peer_skin_off=set_peer_skin_off))
        self.handler.websocket_server = SimpleNamespace(loop=self.loop)

    def settle(self):
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), self.loop).result(2)

    def test_the_switch_reaches_the_party_manager_on_the_partys_own_loop(self):
        self.assertTrue(self.handler._route_party_mod_message("party-peer-skin-off", {"summoner_id": 7, "off": True}))
        self.assertTrue(self.handler._route_party_mod_message("party-peer-skin-off", {"summoner_id": "7", "off": False}))
        self.settle()

        self.assertEqual(self.switched, [(7, True), (7, False)])

    def test_other_messages_are_not_taken(self):
        self.assertFalse(self.handler._route_party_mod_message("party-remove-peer", {"summoner_id": 7}))
        self.assertFalse(self.handler._route_party_mod_message("builds-get", {}))

    def test_a_message_that_names_no_friend_or_comes_without_a_party_does_nothing(self):
        for payload in ({}, {"summoner_id": "x"}, {"summoner_id": 0}, {"summoner_id": -3}, {"summoner_id": None, "off": True}):
            self.assertTrue(self.handler._route_party_mod_message("party-peer-skin-off", payload))
        self.handler.shared_state = SimpleNamespace(party_manager=None)
        self.handler._route_party_mod_message("party-peer-skin-off", {"summoner_id": 7, "off": True})
        self.handler.shared_state = None
        self.handler._route_party_mod_message("party-peer-skin-off", {"summoner_id": 7, "off": True})
        self.settle()

        self.assertEqual(self.switched, [])

    def test_rose_routes_the_message_to_it(self):
        self.assertTrue(issubclass(message_handler.MessageHandler, PartyModHandlersMixin))


if __name__ == "__main__":
    unittest.main()

"""Custom skin mods sent between party members: party/network/mod_transfer.py and party/core/mod_sharing.py.

No network: the room is a stand-in that hands one member's messages to the other, as the relay does.
"""

import asyncio
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from party.core import mod_sharing
from party.core.mod_sharing import ModSharing
from party.core.party_manager import PartyManager
from party.core.party_state import PartyState
from party.discovery import custom_mods, received_mods
from party.network import mod_transfer
from party.network.mod_transfer import MAGIC, ModTransfers, piece_header
from party.tests.test_party import make_state, member


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:32]


class Room:
    """Hands what one member sends to the member it is for, in the order sent"""

    def __init__(self):
        self.members = {}

    def join(self, summoner_id: int):
        relay = SimpleNamespace(connected=True, sent=[], direct=None, binary=None)
        relay.set_direct_callbacks = lambda on_direct=None, on_binary=None: (setattr(relay, "direct", on_direct), setattr(relay, "binary", on_binary))

        async def send_to(to, data):
            relay.sent.append(("text", to, data))
            target = self.members.get(to)
            if target is not None and target.direct:
                target.direct(summoner_id, data)
            return True

        async def send_binary_to(to, payload):
            relay.sent.append(("binary", to, len(payload)))
            target = self.members.get(to)
            if target is not None and target.binary:
                target.binary(summoner_id, payload)
            return True

        relay.send_to, relay.send_binary_to = send_to, send_binary_to
        self.members[summoner_id] = relay
        return relay


async def settle(transfers, seconds=5.0):
    """Let the sending task run to its end"""
    for _ in range(int(seconds / 0.01)):
        tasks = [task for task in transfers._sending.values() if not task.done()]
        if not tasks:
            return
        await asyncio.sleep(0.01)


class TransferCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.mod = self.root / "owner" / "Cool Skin.fantome"
        self.mod.parent.mkdir()
        self.mod.write_bytes(bytes(range(256)) * 300)  # 76,800 bytes: several pieces with the small piece size below
        self.hash, self.size = sha(self.mod), self.mod.stat().st_size
        pieces = patch.object(mod_transfer, "PIECE_BYTES", 20_000)
        pieces.start()
        self.addCleanup(pieces.stop)
        self.room = Room()
        self.owner_relay, self.friend_relay = self.room.join(1), self.room.join(2)
        self.announced = {self.hash: self.mod}
        self.owner = ModTransfers(self.root / "owner-cache", self.announced.get, sha)
        self.friend = ModTransfers(self.root / "friend-cache", lambda content_hash: None, sha)
        self.owner.attach(self.owner_relay)
        self.friend.attach(self.friend_relay)

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    async def fetch(self, content_hash=None, size=None, suffix=".fantome"):
        asked = await self.friend.want(self.friend_relay, 1, content_hash or self.hash, self.size if size is None else size, suffix)
        await settle(self.owner)
        return asked


class TransferTests(TransferCase):
    def test_a_friend_gets_the_whole_file_named_by_its_hash(self):
        self.assertTrue(self.run_async(self.fetch()))

        received = self.friend.cached(self.hash)
        self.assertEqual(received, self.root / "friend-cache" / f"{self.hash}.fantome")
        self.assertEqual(received.read_bytes(), self.mod.read_bytes())
        self.assertEqual(list((self.root / "friend-cache").glob("*.part")), [])
        self.assertEqual(self.friend.status(self.hash)["state"], "have")
        self.assertFalse(self.friend.pending())
        self.assertEqual(sum(1 for kind, _, _ in self.owner_relay.sent if kind == "binary"), 4, "76,800 bytes in pieces of 20,000")

    def test_a_file_that_is_here_or_on_its_way_is_not_asked_for_again(self):
        async def twice():
            first = await self.friend.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome")  # member 9 is not there: no answer
            second = await self.friend.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome")
            return first, second, self.friend.pending()

        self.assertEqual(self.run_async(twice()), (True, False, True))
        self.run_async(self.fetch())
        self.assertFalse(self.run_async(self.fetch()))

    def test_only_a_file_the_owner_announced_is_sent(self):
        secret = self.root / "owner" / "Not Announced.fantome"
        secret.write_bytes(b"private" * 100)

        self.run_async(self.fetch(sha(secret), secret.stat().st_size))

        self.assertEqual(self.friend.status(sha(secret))["state"], "failed")
        self.assertFalse(any(kind == "binary" for kind, _, _ in self.owner_relay.sent))

    def test_a_file_that_is_not_the_one_announced_is_deleted(self):
        self.announced["cd" * 16] = self.mod  # the owner sends another file under this hash

        self.run_async(self.fetch("cd" * 16))

        self.assertEqual(self.friend.status("cd" * 16)["state"], "failed")
        self.assertIsNone(self.friend.cached("cd" * 16))
        self.assertEqual(list((self.root / "friend-cache").iterdir()), [])

    def test_more_bytes_than_announced_are_refused(self):
        self.run_async(self.fetch(size=30_000))  # the owner's start says 76,800: not what was announced

        self.assertEqual(self.friend.status(self.hash)["state"], "failed")
        self.assertEqual(list((self.root / "friend-cache").glob("*")), [])

    def test_pieces_nobody_asked_for_and_pieces_from_someone_else_are_ignored(self):
        async def stray():
            await self.owner_relay.send_binary_to(2, piece_header("ef" * 16, 0) + b"unasked")
            await self.owner_relay.send_binary_to(2, MAGIC + b"short")
            await self.owner_relay.send_to(2, {"t": "mod-end", "hash": "../../evil"})
            await self.owner_relay.send_to(2, {"t": "mod-start", "hash": "ef" * 16, "size": 7})
            await self.friend.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome")
            third = self.room.join(3)
            await third.send_to(2, {"t": "mod-start", "hash": "ab" * 16, "size": 500})
            await third.send_binary_to(2, piece_header("ab" * 16, 0) + b"x" * 500)

        self.run_async(stray())

        self.assertEqual(self.friend.status("ab" * 16)["state"], "asked", "only its owner can start it")
        self.assertEqual([path.name for path in (self.root / "friend-cache").iterdir()], [])

    def test_what_cannot_be_a_mod_file_is_never_asked_for(self):
        async def asks():
            return [await self.friend.want(self.friend_relay, 1, *wrong) for wrong in (
                ("../../x", 100, ".fantome"), ("zz" * 16, 100, ".fantome"), (self.hash, 100, ".exe"), (self.hash, 0, ".fantome"),
                (self.hash, mod_transfer.MAX_MOD_BYTES + 1, ".zip"), (None, 100, ".zip"))]

        self.assertEqual(self.run_async(asks()), [False] * 6)
        self.assertEqual(self.friend_relay.sent, [])

    def test_a_download_that_stopped_arriving_no_longer_holds_a_game(self):
        self.run_async(self.friend.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome"))
        self.assertTrue(self.friend.pending())

        self.friend.downloads["ab" * 16].last_piece_at -= mod_transfer.STALLED_S + 1

        self.assertFalse(self.friend.pending())
        self.assertTrue(self.run_async(self.friend.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome")), "and it is asked for again")

    def test_the_same_member_id_in_another_room_cannot_answer_for_the_owner(self):
        content = b"x" * 500
        wanted = hashlib.sha256(content).hexdigest()[:32]
        other_room = Room()
        self.friend.attach(other_room.join(2))  # the friend is in a second room too

        async def answer(room):
            sender = room.join(9)
            await sender.send_to(2, {"t": "mod-start", "hash": wanted, "size": 500})
            await sender.send_binary_to(2, piece_header(wanted, 0) + content)
            await sender.send_to(2, {"t": "mod-end", "hash": wanted})

        self.run_async(self.friend.want(self.friend_relay, 9, wanted, 500, ".fantome"))
        self.run_async(answer(other_room))
        self.assertEqual((self.friend.status(wanted)["state"], list((self.root / "friend-cache").iterdir())), ("asked", []))

        self.run_async(answer(self.room))
        self.assertEqual(self.friend.status(wanted)["state"], "have", "the room it was asked in is the one that counts")

    def test_the_folder_of_received_files_never_grows_past_its_limit(self):
        cache = self.root / "friend-cache"
        cache.mkdir()
        for name, size, age in (("11" * 16 + ".fantome", 80_000, 300), ("22" * 16 + ".zip", 80_000, 200), ("33" * 16 + ".part", 30_000, 100)):
            (cache / name).write_bytes(b"o" * size)
            os.utime(cache / name, (time.time() - age, time.time() - age))

        with patch.object(mod_transfer, "CACHE_BYTES", 200_000):
            self.assertTrue(self.run_async(self.fetch()))
            self.assertEqual(sorted(path.name for path in cache.iterdir()), sorted(["22" * 16 + ".zip", self.hash + ".fantome"]),
                             "the leftover of a broken download went first, then the oldest file")
            self.run_async(self.friend.want(self.friend_relay, 9, "ab" * 16, 150_000, ".fantome"))  # on its way: counts in full
            self.assertEqual(list(cache.iterdir()), [], "150,000 more only fits once both files are gone")
            (cache / ("44" * 16 + ".zip")).write_bytes(b"o" * 10_000)
            sent = len(self.friend_relay.sent)
            self.assertFalse(self.run_async(self.friend.want(self.friend_relay, 8, "cd" * 16, 60_000, ".fantome")))
            self.assertEqual((len(self.friend_relay.sent), self.friend.status("cd" * 16)["state"]), (sent, "none"), "refused, not asked for")
            self.assertEqual([path.name for path in cache.iterdir()], ["44" * 16 + ".zip"], "and nothing was deleted for it")

    def test_a_member_has_one_file_on_its_way(self):
        async def two_picks():
            return (await self.friend.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome"),
                    await self.friend.want(self.friend_relay, 9, "cd" * 16, 600, ".fantome"))

        self.assertEqual(self.run_async(two_picks()), (True, True))
        self.assertEqual((self.friend.status("ab" * 16)["state"], self.friend.status("cd" * 16)["state"]), ("none", "asked"))
        self.assertEqual(list(self.friend.downloads), ["cd" * 16], "a member who keeps changing their pick fills nothing")


class SharingTests(TransferCase):
    def setUp(self):
        super().setUp()
        # received files go to the test's folder, and a file's hash is read as the test's files have it
        for name, stand_in in (("received_dir", lambda: self.root / "friend-cache"), ("content_hash_of", sha)):
            replaced = patch.object(mod_sharing, name, stand_in)
            replaced.start()
            self.addCleanup(replaced.stop)
        self.sharing = ModSharing()
        self.sharing.attach(self.friend_relay)
        self.local = patch.object(mod_sharing, "find_local_mod", return_value=None)
        self.find_local = self.local.start()
        self.addCleanup(self.local.stop)

    def custom(self, summoner_id=1, **changes):
        fields = dict(is_custom=True, custom_mod_content_hash=self.hash, custom_mod_size=self.size, custom_mod_ext=".fantome", custom_mod_name="Cool Skin")
        fields.update(changes)
        return member(summoner_id, f"Friend {summoner_id}", 103, 103000, **fields)

    def fetch_missing(self, members, my_id=2, ignored=frozenset()):
        async def run():
            asked = await self.sharing.fetch_missing([(self.friend_relay, members)], my_id, set(ignored))
            await settle(self.owner)
            return asked
        return self.run_async(run())

    def test_our_own_pick_tells_the_party_what_to_ask_for(self):
        state = {"champion_id": 103, "skin_id": 103000, "is_custom": True, "custom_mod_content_hash": self.hash}
        with patch.object(mod_sharing, "own_mod_file", return_value=self.mod):
            self.sharing.announce(state, "skins/103000/Cool Skin.fantome")

        self.assertEqual((state["custom_mod_size"], state["custom_mod_ext"], state["custom_mod_name"]), (self.size, ".fantome", "Cool Skin"))
        self.assertEqual(self.sharing.transfers.own_file(self.hash), self.mod, "and only that file can be asked for")

    def test_a_mod_that_cannot_be_sent_is_announced_as_before(self):
        for label, found, state in (("kept as a folder", None, {"custom_mod_content_hash": self.hash}),
                                    ("no content hash (an older mod)", self.mod, {"custom_mod_hash": "abcd"})):
            with self.subTest(label), patch.object(mod_sharing, "own_mod_file", return_value=found):
                before = dict(state)
                self.sharing.announce(state, "skins/103000/x")
                self.assertEqual(state, before)

    def test_a_friends_custom_mod_we_lack_is_asked_for_and_arrives(self):
        self.assertEqual(self.fetch_missing([self.custom()]), 1)

        self.assertEqual(self.sharing.transfers.status(self.hash)["state"], "have")
        self.assertEqual(self.sharing.describe(self.custom()["skin"]), {"name": "Cool Skin", "size": self.size, "state": "have", "received": 0})

    def test_nothing_is_asked_for_what_needs_no_file(self):
        cases = {
            "an official skin": [member(1, "Friend", 103, 103001)],
            "ourselves": [self.custom(2)],
            "a friend the user removed": [self.custom(1)],
            "a friend whose skin is switched off": [self.custom(1)],
            "an older Rose that does not say the size": [self.custom(custom_mod_size=None)],
            "a member without a pick": [member(1, "Friend")],
        }
        self.sharing.switched_off = set()
        for label, members in cases.items():
            with self.subTest(label):
                self.sharing.switched_off = {1} if "switched off" in label else set()
                asked = self.fetch_missing(members, ignored={1} if "removed" in label else frozenset())
                self.assertEqual((asked, self.friend_relay.sent), (0, []))

    def test_a_mod_we_have_our_own_copy_of_is_not_asked_for(self):
        self.find_local.return_value = "skins/103000/Cool Skin.fantome"

        self.assertEqual(self.fetch_missing([self.custom()]), 0)
        self.assertEqual(self.sharing.describe(self.custom()["skin"])["state"], "have")
        self.find_local.assert_called_once_with(103, content_hash=self.hash, legacy_hash=None)

    def test_the_panel_is_told_where_a_friends_mod_stands(self):
        self.assertIsNone(self.sharing.describe(member(1, "Friend", 103, 103001)["skin"]))
        self.assertIsNone(self.sharing.describe(None))
        self.assertEqual(self.sharing.describe(self.custom()["skin"])["state"], "none")
        self.run_async(self.sharing.transfers.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome"))
        told = self.sharing.describe(self.custom(custom_mod_content_hash="ab" * 16, custom_mod_size=500, custom_mod_name="N" * 200)["skin"])
        self.assertEqual((told["state"], told["size"], len(told["name"])), ("asked", 500, mod_sharing.NAME_LENGTH))

    def test_an_injection_waits_for_a_file_on_its_way_but_not_for_ever(self):
        naps = []
        self.assertTrue(self.sharing.wait(5.0, naps.append))
        self.assertEqual(naps, [], "nothing on its way: no wait")
        self.run_async(self.sharing.transfers.want(self.friend_relay, 9, "ab" * 16, 500, ".fantome"))

        ticks = iter(range(10_000))
        with patch.object(mod_sharing.time, "monotonic", lambda: 100.0 + next(ticks)):  # a clock that moves a second each look
            arrived = self.sharing.wait(5.0, naps.append)

        self.assertFalse(arrived, "the file never came: the wait ends by itself")
        self.assertTrue(0 < len(naps) <= 5 and set(naps) == {0.2}, naps)


class PartyWiringTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        for target in (received_mods, custom_mods):
            located = patch.object(target, "get_user_data_dir", lambda: self.data)
            located.start()
            self.addCleanup(located.stop)

    def test_a_file_a_friend_sent_is_found_as_our_copy_of_their_mod(self):
        received = self.data / "mods" / received_mods.FOLDER
        received.mkdir(parents=True)
        (received / ("ab" * 16 + ".fantome")).write_bytes(b"mod")

        self.assertEqual(custom_mods.find_local_mod(103, content_hash="ab" * 16), "party-received/" + "ab" * 16 + ".fantome")
        self.assertIsNone(custom_mods.find_local_mod(103, content_hash="cd" * 16))
        self.assertIsNone(received_mods.received_mod("../../x"))
        self.assertIsNone(received_mods.received_mod(None))

    def test_the_panel_gets_each_friends_mod_and_switch(self):
        state = PartyState()
        state.add_peer(2, "Friend")
        state.set_peer_mod(2, {"name": "Cool Skin", "size": 5, "state": "receiving", "received": 2}, True)
        state.set_peer_mod(9, None, False)  # not a peer: nothing happens

        peer = state.to_dict()["peers"][0]
        self.assertEqual((peer["custom_mod"]["name"], peer["custom_mod"]["state"], peer["skin_off"]), ("Cool Skin", "receiving", True))

    def test_a_friend_whose_skin_is_switched_off_is_not_injected_but_stays_in_the_party(self):
        manager = PartyManager(Mock(), make_state())
        manager.party_state.enabled = True
        manager.party_state.my_summoner_id = 1
        manager._relays = {"a" * 32: SimpleNamespace(members=[member(1, "Me"), member(2, "B", 11, 11002), member(3, "C", 22, 22003)], connected=True)}
        manager._lobby_matcher = SimpleNamespace(get_team_info=lambda: ({}, set()))
        manager._skin_collector = Mock()

        asyncio.run(manager.set_peer_skin_off(2, True))
        manager.get_party_skins()

        collected = manager._skin_collector.collect_relay_skins.call_args.kwargs["members"]
        self.assertEqual([m["summoner_id"] for m in collected], [3])
        peers = {peer["summoner_id"]: peer for peer in manager.party_state.to_dict()["peers"]}
        self.assertEqual((sorted(peers), peers[2]["skin_off"], peers[3]["skin_off"]), ([2, 3], True, False))
        asyncio.run(manager.set_peer_skin_off(2, False))
        manager.get_party_skins()
        self.assertEqual(len(manager._skin_collector.collect_relay_skins.call_args.kwargs["members"]), 2)

    def test_every_room_hands_its_direct_messages_to_the_mod_sharing(self):
        manager = PartyManager(Mock(), make_state())
        manager.party_state.my_summoner_id = 1
        with patch("party.core.party_manager.PartyRelay") as relay_class:
            manager._add_relay("a" * 32)

        relay_class.return_value.set_direct_callbacks.assert_called_once()


if __name__ == "__main__":
    unittest.main()

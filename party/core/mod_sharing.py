#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Party mode's part in sending custom skin mods between members (party/network/mod_transfer.py).

- announce: what our own pick tells the party about its file, so a friend can ask for it.
- fetch_missing: ask each friend for the mod they play with, when we have no copy of it.
- describe: what the panel shows about a friend's mod (its name, whether it is here, how far it is).
- wait: the last moments before a game, for files still on their way.
- switched_off: friends whose skin the user does not want on their own screen.
Design: docs/party-mod-sharing.md.
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Set, Tuple

from party.discovery.custom_mods import _stored_path, find_local_mod, get_mods_root, mod_hashes
from party.discovery.received_mods import SUFFIXES, received_dir
from party.network.mod_transfer import MAX_MOD_BYTES, ModTransfers, valid_hash
from injection.mods.manifest import find_saved_mod
from utils.core.logging import get_logger

log = get_logger()

WAIT_BEFORE_GAME_S = 15.0  # how long an injection waits for files still arriving; they usually arrive in champ select
NAME_LENGTH = 60


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def content_hash_of(path: Path) -> Optional[str]:
    """The hash party mode announces for a mod file"""
    return mod_hashes(Path(path))[0]


def own_mod_file(relative_path: str) -> Optional[Path]:
    """The file of our own custom skin pick, when it is one file (a mod kept as a folder cannot be sent)"""
    mods_root = get_mods_root()
    saved = find_saved_mod(mods_root, relative_path, match_content=False)
    path = saved.rose_copy if saved is not None else _stored_path(mods_root / relative_path)
    return path if path is not None and path.is_file() and path.suffix.lower() in SUFFIXES else None


class ModSharing:
    def __init__(self, on_change: Optional[Callable[[], None]] = None):
        self.transfers = ModTransfers(received_dir(), self._announced_file, content_hash_of, on_change)
        self._announced: Dict[str, Path] = {}   # content hash -> our file, for what we told the party
        self._have: Set[str] = set()            # content hashes we found a copy of (our own mods, or received)
        self.switched_off: Set[int] = set()     # friends whose skin the user switched off for their own screen

    def _announced_file(self, content_hash: str) -> Optional[Path]:
        return self._announced.get(content_hash)

    def attach(self, relay) -> None:
        self.transfers.attach(relay)

    def announce(self, skin_state: dict, relative_path: str) -> None:
        """Add to our pick, as the party gets it, what a friend needs to ask for its file: the size, the kind
        of file and the mod's name. Nothing is added for a mod that cannot be sent."""
        content_hash = skin_state.get("custom_mod_content_hash")
        if not valid_hash(content_hash):
            return
        try:
            path = own_mod_file(relative_path)
            size = path.stat().st_size if path is not None else 0
        except OSError:
            return
        if path is None or not 0 < size <= MAX_MOD_BYTES:
            return
        self._announced[content_hash] = path
        skin_state.update(custom_mod_size=size, custom_mod_ext=path.suffix.lower(), custom_mod_name=path.stem[:NAME_LENGTH])

    async def fetch_missing(self, rooms: Iterable[Tuple[object, list]], my_id: int, ignored: Set[int] = frozenset()) -> int:
        """Ask each friend in *rooms* ((relay, its members)) for the custom mod they play with, when we have
        no copy of it. Returns how many files were asked for."""
        asked = 0
        for relay, members in rooms:
            if not getattr(relay, "connected", False):
                continue
            for member in members:
                skin = member.get("skin") if isinstance(member, dict) else None
                owner = _to_int(member.get("summoner_id")) if isinstance(member, dict) else 0
                if not owner or owner == my_id or owner in ignored or owner in self.switched_off or not isinstance(skin, dict):
                    continue
                content_hash, size, suffix = skin.get("custom_mod_content_hash"), _to_int(skin.get("custom_mod_size")), skin.get("custom_mod_ext")
                if not skin.get("is_custom") or not valid_hash(content_hash) or not size or suffix not in SUFFIXES:
                    continue
                if content_hash in self._have:
                    continue
                found = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: find_local_mod(_to_int(skin.get("champion_id")), content_hash=content_hash, legacy_hash=skin.get("custom_mod_hash")))
                if found:
                    self._have.add(content_hash)
                    continue
                if await self.transfers.want(relay, owner, content_hash, size, suffix):
                    asked += 1
        return asked

    def describe(self, skin) -> Optional[dict]:
        """For the panel: {"name", "size", "state", "received"} of a friend's custom mod; None for an
        official skin. state: "have", "asked", "receiving", "failed", or "none" (a mod that cannot be sent)."""
        if not isinstance(skin, dict) or not skin.get("is_custom"):
            return None
        content_hash = skin.get("custom_mod_content_hash")
        status = self.transfers.status(content_hash) if valid_hash(content_hash) else {"state": "none", "received": 0, "size": 0}
        if content_hash in self._have:
            status = dict(status, state="have")
        return {"name": str(skin.get("custom_mod_name") or "Custom skin")[:NAME_LENGTH], "size": _to_int(skin.get("custom_mod_size")),
                "state": status["state"], "received": status["received"]}

    def wait(self, timeout: float = WAIT_BEFORE_GAME_S, sleep: Callable[[float], None] = time.sleep) -> bool:
        """Wait (in the injection's thread) until no file is on its way, *timeout* seconds at most. True when
        nothing is left on its way."""
        deadline = time.monotonic() + timeout
        while self.transfers.pending():
            if time.monotonic() >= deadline:
                return False
            sleep(0.2)
        return True

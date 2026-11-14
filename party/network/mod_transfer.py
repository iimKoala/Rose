#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Party members send each other the custom skin mods they play with.

The original party mode shares only a mod's hash: a friend sees the mod when they happen to have the same
file, and the official skin (or nothing) when they don't. Here a member who lacks the file asks its owner for
it, through the party's relay, one member to one other. The relay passes the pieces on and keeps nothing.

What keeps it safe:
- An owner only sends a file whose hash it announced to the party as its own pick. Nothing else can be asked
  for.
- A receiver only takes pieces of a file it asked for, from the member it asked, up to the size that member
  announced and never past MAX_MOD_BYTES. The finished file must have the hash that was announced, or it is
  deleted.
- Files go to a folder of their own (party_cache_dir), never into the user's own mods.

Messages, one member to one other (PartyRelay.send_to / send_binary_to):
    {"t": "mod-want", "hash": h}                      the receiver asks
    {"t": "mod-start", "hash": h, "size": n}          the owner answers, then sends the pieces
    binary: MAGIC + 8 bytes of the hash + 4 bytes piece number + the piece
    {"t": "mod-end", "hash": h}                       all pieces were sent
    {"t": "mod-none", "hash": h}                      the owner cannot send it
Design: docs/party-mod-sharing.md.
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from utils.core.logging import get_logger

log = get_logger()

MAGIC = b"RMOD"
PIECE_BYTES = 256 * 1024
MAX_MOD_BYTES = 600 * 1024 * 1024
STALLED_S = 20.0  # a download that got no piece for this long is given up, so it can be asked for again
HASH_RE_LENGTH = (16, 64)  # a content hash is hex digits, this many at least and at most
SUFFIXES = (".fantome", ".zip", ".modpkg")


def valid_hash(value) -> bool:
    return isinstance(value, str) and HASH_RE_LENGTH[0] <= len(value) <= HASH_RE_LENGTH[1] and all(c in "0123456789abcdef" for c in value)


def piece_header(content_hash: str, number: int) -> bytes:
    return MAGIC + bytes.fromhex(content_hash[:16]) + number.to_bytes(4, "little")


class Download:
    """One file being received"""

    def __init__(self, owner: int, content_hash: str, size: int, suffix: str, folder: Path):
        self.owner, self.content_hash, self.size, self.suffix = owner, content_hash, size, suffix
        self.received, self.next_piece, self.last_piece_at = 0, 0, time.monotonic()
        self.part = folder / f"{content_hash}.part"
        self.final = folder / f"{content_hash}{suffix}"
        self.file = None
        self.state = "asked"  # asked -> receiving -> done | failed

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None


class ModTransfers:
    """The sending and receiving of mod files for one party.

    *cache_dir* is where received files go. *own_file(content hash)* is the path of a file we announced with
    that hash, or None. *file_hash(path)* is the content hash of a received file, as the party announces
    hashes. *on_change()* is called when a download starts, moves on or ends.
    """

    def __init__(self, cache_dir: Path, own_file: Callable[[str], Optional[Path]], file_hash: Callable[[Path], Optional[str]],
                 on_change: Optional[Callable[[], None]] = None):
        self.cache_dir, self.own_file, self.file_hash, self.on_change = Path(cache_dir), own_file, file_hash, on_change
        self.downloads: Dict[str, Download] = {}
        self._sending: Dict[tuple, asyncio.Task] = {}
        self._relays = {}  # summoner id of a member -> the relay of a room we share with them

    # ---------- wiring
    def attach(self, relay) -> None:
        """Take the direct messages of *relay* (one of the party's rooms)"""
        relay.set_direct_callbacks(lambda sender, data: self._on_direct(relay, sender, data),
                                   lambda sender, payload: self._on_binary(sender, payload))

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception as e:  # noqa: BLE001 - a listener must not break a transfer
                log.debug(f"[PARTY_MODS] A listener failed: {e}")

    # ---------- receiving
    def cached(self, content_hash: str) -> Optional[Path]:
        """A file received earlier with this hash, or None"""
        if not valid_hash(content_hash):
            return None
        for suffix in SUFFIXES:
            path = self.cache_dir / f"{content_hash}{suffix}"
            if path.is_file():
                return path
        return None

    def status(self, content_hash: str) -> dict:
        """{"state": "have" | "asked" | "receiving" | "failed" | "none", "received", "size"} of a file"""
        if self.cached(content_hash):
            return {"state": "have", "received": 0, "size": 0}
        download = self.downloads.get(content_hash)
        if download is None:
            return {"state": "none", "received": 0, "size": 0}
        return {"state": download.state, "received": download.received, "size": download.size}

    def pending(self) -> bool:
        """Whether a file is still on its way (asked for or being received, and not stalled)"""
        now = time.monotonic()
        # a copy of the list: the injection's thread asks while the party's own thread adds to it
        return any(d.state in ("asked", "receiving") and now - d.last_piece_at < STALLED_S for d in list(self.downloads.values()))

    async def want(self, relay, owner: int, content_hash: str, size: int, suffix: str) -> bool:
        """Ask *owner* for the file with *content_hash*, unless we have it or it is already on its way.
        Returns whether it was asked for now."""
        if not valid_hash(content_hash) or suffix not in SUFFIXES or not 0 < int(size or 0) <= MAX_MOD_BYTES:
            return False
        if self.cached(content_hash):
            return False
        current = self.downloads.get(content_hash)
        if current is not None and current.state in ("asked", "receiving") and time.monotonic() - current.last_piece_at < STALLED_S:
            return False
        if current is not None:
            self._drop(current)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        download = Download(int(owner), content_hash, int(size), suffix, self.cache_dir)
        self.downloads[content_hash] = download
        if not await relay.send_to(owner, {"t": "mod-want", "hash": content_hash}):
            download.state = "failed"
            return False
        log.info(f"[PARTY_MODS] Asked member {owner} for the mod {content_hash[:8]} ({size // 1024} KB)")
        self._changed()
        return True

    def _drop(self, download: Download, failed: bool = True) -> None:
        download.close()
        try:
            download.part.unlink(missing_ok=True)
        except OSError:
            pass
        if failed:
            download.state = "failed"

    def _on_binary(self, sender, payload: bytes) -> None:
        if len(payload) < 16 or payload[:4] != MAGIC:
            return
        prefix, number = payload[4:12].hex(), int.from_bytes(payload[12:16], "little")
        download = next((d for d in self.downloads.values() if d.content_hash.startswith(prefix) and d.owner == sender), None)
        if download is None or download.state != "receiving" or number != download.next_piece:
            return  # not asked for, not from its owner, or out of order: not taken
        piece = payload[16:]
        if download.received + len(piece) > download.size:
            log.warning(f"[PARTY_MODS] Member {sender} sent more than the {download.size} bytes announced: dropped")
            self._drop(download)
            self._changed()
            return
        download.file.write(piece)
        download.received += len(piece)
        download.next_piece += 1
        download.last_piece_at = time.monotonic()
        if download.next_piece % 8 == 0:
            self._changed()

    def _on_direct(self, relay, sender, data) -> None:
        if not isinstance(data, dict) or not valid_hash(data.get("hash")):
            return
        kind, content_hash = data.get("t"), data["hash"]
        if kind == "mod-want":
            key = (sender, content_hash)
            if key not in self._sending or self._sending[key].done():
                self._sending[key] = asyncio.ensure_future(self._send(relay, sender, content_hash))
            return
        download = self.downloads.get(content_hash)
        if download is None or download.owner != sender:
            return
        if kind == "mod-start" and download.state == "asked":
            if int(data.get("size") or 0) != download.size:
                log.warning(f"[PARTY_MODS] Member {sender} now says another size for {content_hash[:8]}: dropped")
                self._drop(download)
            else:
                download.file = open(download.part, "wb")
                download.state, download.last_piece_at = "receiving", time.monotonic()
        elif kind == "mod-end" and download.state == "receiving":
            self._finish(download)
        elif kind == "mod-none":
            log.info(f"[PARTY_MODS] Member {sender} cannot send the mod {content_hash[:8]}")
            self._drop(download)
        self._changed()

    def _finish(self, download: Download) -> None:
        download.close()
        try:
            good = download.received == download.size and self.file_hash(download.part) == download.content_hash
        except Exception as e:  # noqa: BLE001 - a file that cannot even be read is not good
            log.warning(f"[PARTY_MODS] The received mod {download.content_hash[:8]} could not be read: {e}")
            good = False
        if not good:
            log.warning(f"[PARTY_MODS] The mod received from member {download.owner} is not the one announced: deleted")
            self._drop(download)
            return
        os.replace(download.part, download.final)
        download.state = "done"
        log.info(f"[PARTY_MODS] Received the mod {download.content_hash[:8]} from member {download.owner} ({download.size // 1024} KB)")

    # ---------- sending
    async def _send(self, relay, receiver, content_hash: str) -> None:
        path = self.own_file(content_hash)
        try:
            size = path.stat().st_size if path is not None and path.is_file() else 0
        except OSError:
            size = 0
        if not 0 < size <= MAX_MOD_BYTES:
            await relay.send_to(receiver, {"t": "mod-none", "hash": content_hash})
            return
        log.info(f"[PARTY_MODS] Sending the mod {content_hash[:8]} to member {receiver} ({size // 1024} KB)")
        if not await relay.send_to(receiver, {"t": "mod-start", "hash": content_hash, "size": size}):
            return
        number = 0
        with open(path, "rb") as source:
            while True:
                piece = await asyncio.get_running_loop().run_in_executor(None, source.read, PIECE_BYTES)
                if not piece:
                    break
                if not await relay.send_binary_to(receiver, piece_header(content_hash, number) + piece):
                    log.info(f"[PARTY_MODS] The connection dropped while sending {content_hash[:8]}")
                    return
                number += 1
        await relay.send_to(receiver, {"t": "mod-end", "hash": content_hash})

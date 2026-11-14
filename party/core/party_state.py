#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Party State
State management for party mode
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from ..protocol.message_types import SkinSelection


@dataclass
class PartyPeerState:
    """State for a single party peer"""
    summoner_id: int
    summoner_name: str = "Unknown"
    connected: bool = False
    connection_state: str = "disconnected"  # connecting, handshaking, connected, disconnected, dead
    in_lobby: bool = False
    skin_selection: Optional[SkinSelection] = None
    # The custom skin mod this friend plays with (party/core/mod_sharing.py: name,
    # size, whether its file is here), and whether the user switched their skin off
    custom_mod: Optional[dict] = None
    skin_off: bool = False


@dataclass
class PartyState:
    """Party mode state container"""

    # Party mode status
    enabled: bool = False
    connection: str = "offline"  # online, reconnecting, offline
    my_token: Optional[str] = None
    my_summoner_id: Optional[int] = None
    my_summoner_name: str = "Unknown"

    # Connected peers
    peers: Dict[int, PartyPeerState] = field(default_factory=dict)

    # Skin selections from peers (champion_id -> skin_data)
    party_skins: Dict[int, dict] = field(default_factory=dict)

    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_peer(
        self,
        summoner_id: int,
        summoner_name: str = "Unknown",
        connected: bool = False,
        connection_state: str = "disconnected",
    ):
        """Add or update a peer"""
        with self._lock:
            if summoner_id in self.peers:
                self.peers[summoner_id].summoner_name = summoner_name
                self.peers[summoner_id].connected = connected
                self.peers[summoner_id].connection_state = connection_state
            else:
                self.peers[summoner_id] = PartyPeerState(
                    summoner_id=summoner_id,
                    summoner_name=summoner_name,
                    connected=connected,
                    connection_state=connection_state,
                )

    def remove_peer(self, summoner_id: int):
        """Remove a peer"""
        with self._lock:
            if summoner_id in self.peers:
                del self.peers[summoner_id]

    def update_peer_lobby_status(self, summoner_id: int, in_lobby: bool):
        """Update peer lobby status"""
        with self._lock:
            if summoner_id in self.peers:
                self.peers[summoner_id].in_lobby = in_lobby

    def update_peer_skin(self, summoner_id: int, selection: SkinSelection):
        """Update peer skin selection"""
        with self._lock:
            if summoner_id in self.peers:
                self.peers[summoner_id].skin_selection = selection
                # Also update party_skins for easy lookup by champion
                self.party_skins[selection.champion_id] = {
                    "summoner_id": selection.summoner_id,
                    "summoner_name": selection.summoner_name,
                    "skin_id": selection.skin_id,
                    "chroma_id": selection.chroma_id,
                    "custom_mod_path": selection.custom_mod_path,
                }

    def set_peer_mod(self, summoner_id: int, custom_mod: Optional[dict], skin_off: bool):
        """What the panel shows about a friend's custom mod and the user's switch for their skin"""
        with self._lock:
            if summoner_id in self.peers:
                self.peers[summoner_id].custom_mod = custom_mod
                self.peers[summoner_id].skin_off = skin_off

    def clear_peer_skin(self, summoner_id: int):
        """Clear peer skin selection"""
        with self._lock:
            if summoner_id in self.peers:
                old_selection = self.peers[summoner_id].skin_selection
                self.peers[summoner_id].skin_selection = None
                # Remove from party_skins
                if old_selection:
                    self.party_skins.pop(old_selection.champion_id, None)

    def clear_all(self):
        """Clear all party state"""
        with self._lock:
            self.enabled = False
            self.connection = "offline"
            self.my_token = None
            self.peers.clear()
            self.party_skins.clear()

    def to_dict(self) -> dict:
        """Convert to dictionary for UI broadcast"""
        with self._lock:
            return {
                "enabled": self.enabled,
                "connection": self.connection,
                "my_token": self.my_token,
                "my_summoner_id": self.my_summoner_id,
                "my_summoner_name": self.my_summoner_name,
                "peers": [
                    {
                        "summoner_id": p.summoner_id,
                        "summoner_name": p.summoner_name,
                        "connected": p.connected,
                        "connection_state": p.connection_state,
                        "in_lobby": p.in_lobby,
                        "skin_selection": (
                            p.skin_selection.to_dict() if p.skin_selection else None
                        ),
                        "custom_mod": p.custom_mod,
                        "skin_off": p.skin_off,
                    }
                    for p in self.peers.values()
                ],
            }

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Party Mode Message Types
Protocol message definitions for P2P communication
"""

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional

from utils.core.logging import get_logger

log = get_logger()


class MessageType(Enum):
    """Types of P2P messages"""

    # Connection management
    PING = "ping"
    PONG = "pong"
    HELLO = "hello"          # Initial handshake
    HELLO_ACK = "hello_ack"  # Handshake acknowledgment

    # Skin sharing
    SKIN_UPDATE = "skin_update"    # Single skin selection update
    SKIN_SYNC = "skin_sync"        # Full skin state sync request/response
    SKIN_CLEAR = "skin_clear"      # Clear skin selection

    # Lobby coordination
    LOBBY_INFO = "lobby_info"      # Share lobby/summoner info
    LOBBY_MATCH = "lobby_match"    # Confirm same lobby
    READY = "ready"                # Ready for injection

    # Errors
    ERROR = "error"


@dataclass
class Message:
    """P2P protocol message"""

    type: MessageType
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    sequence: int = 0

    def to_bytes(self) -> bytes:
        """Serialize message to bytes for transmission"""
        data = {
            "type": self.type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        """Deserialize message from bytes"""
        try:
            parsed = json.loads(data.decode("utf-8"))
            return cls(
                type=MessageType(parsed["type"]),
                payload=parsed.get("payload", {}),
                timestamp=parsed.get("timestamp", time.time()),
                sequence=parsed.get("sequence", 0),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.warning(f"[MSG] Failed to parse message: {e}")
            raise ValueError(f"Invalid message format: {e}")


@dataclass
class SkinSelection:
    """Skin selection data for a single champion"""

    summoner_id: int
    summoner_name: str
    champion_id: int
    skin_id: int
    chroma_id: Optional[int] = None
    custom_mod_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for message payload"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkinSelection":
        """Create from dictionary"""
        return cls(
            summoner_id=data["summoner_id"],
            summoner_name=data.get("summoner_name", "Unknown"),
            champion_id=data["champion_id"],
            skin_id=data["skin_id"],
            chroma_id=data.get("chroma_id"),
            custom_mod_path=data.get("custom_mod_path"),
        )

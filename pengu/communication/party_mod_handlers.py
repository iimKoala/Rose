#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Party panel messages about friends' skins and custom mods (the ROSE-PartyMode plugin's switch on a friend's row)
Mixed into MessageHandler; the work is in party/core/mod_sharing.py.
"""

import asyncio
import logging

log = logging.getLogger(__name__)


class PartyModHandlersMixin:
    """Needs self.shared_state (with party_manager) and self.websocket_server (with loop) from MessageHandler."""

    def _route_party_mod_message(self, payload_type: str, payload: dict) -> bool:
        """Handle a party-peer-skin-off message. Returns False for any other type."""
        if payload_type != "party-peer-skin-off":
            return False
        self._handle_party_peer_skin_off(payload)
        return True

    def _handle_party_peer_skin_off(self, payload: dict) -> None:
        """{"summoner_id", "off"}: one friend's skin is, or is not, applied on this PC. The panel learns the
        result from the party state Rose sends after every change."""
        try:
            summoner_id = int(payload.get("summoner_id") or 0)
        except (TypeError, ValueError):
            return
        party_manager = getattr(getattr(self, "shared_state", None), "party_manager", None)
        loop = getattr(getattr(self, "websocket_server", None), "loop", None)
        if summoner_id <= 0 or party_manager is None or loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(party_manager.set_peer_skin_off(summoner_id, bool(payload.get("off"))), loop)
            log.info(f"[PARTY] Skin of friend {summoner_id} switched {'off' if payload.get('off') else 'on'} for this PC")
        except Exception as e:  # noqa: BLE001 - a switch must never break the message loop
            log.error(f"[PARTY] Could not switch a friend's skin: {e}")

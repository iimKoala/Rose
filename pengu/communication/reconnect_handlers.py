#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reconnect screen message handler (the ROSE-ReconnectMods plugin's drop-down)
Mixed into MessageHandler; the work is in injection/overlay/reconnect_choice.py.
"""

import json
import logging

log = logging.getLogger(__name__)


class ReconnectHandlersMixin:
    """Reconnect handler. Needs self._send_response(message: str) and self.injection_manager from MessageHandler."""

    def _route_reconnect_message(self, payload_type: str, payload: dict) -> bool:
        """Handle a reconnect-* message. Returns False if the type isn't a reconnect message."""
        if payload_type != "reconnect-mods":
            return False
        self._handle_reconnect_mods(payload)
        return True

    def _handle_reconnect_mods(self, payload: dict) -> None:
        """This game's mods and how the drop-down's last choice is going. With "disable" (a list of mod
        ids): leave those out of the game the player reconnects to. "active" is False when no game
        session runs: Rose's mods are off already."""
        response = {"type": "reconnect-mods-response", "requestId": payload.get("requestId"),
                    "active": False, "mods": [], "status": ""}
        try:
            injector = getattr(getattr(self, "injection_manager", None), "injector", None)
            overlay = getattr(injector, "overlay_manager", None)
            state = overlay.reconnect_mods() if overlay else None
            if state is not None:
                disable = payload.get("disable")
                if isinstance(disable, list) and disable:
                    state["status"] = overlay.leave_out_on_reconnect(disable)
                response.update(state, active=True)
        except Exception:
            log.exception("reconnect-mods failed")
        self._send_response(json.dumps(response))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Champ select builds message handler (the ROSE-Builds plugin's panel)
Mixed into MessageHandler; the work is in main/build_service.py.
"""

import json
import logging

log = logging.getLogger(__name__)


class BuildHandlersMixin:
    """Builds handler. Needs self._send_response(message: str) and self.skin_scraper from MessageHandler."""

    def _route_build_message(self, payload_type: str, payload: dict) -> bool:
        """Handle a builds-* message. Returns False if the type isn't a builds message."""
        if payload_type != "builds-get":
            return False
        self._handle_builds_get(payload)
        return True

    def _handle_builds_get(self, payload: dict) -> None:
        """The panel's state for what it sees in champ select: championId, lane, enemyIds, playerIndex,
        versus (an enemy champion id, -1 to guess the lane opponent, 0 for the usual build), buildIndex (0, or
        the number of one of the player's other builds, which then stands in for the matchup's), import (the
        list of parts to import: "runes", "spells", "items"; the panel has a button for each)."""
        from main.build_import import PARTS
        from main.build_service import AUTO, panel_state
        from main.onetricks import OnetricksError
        response = {"type": "builds-get-response", "requestId": payload.get("requestId")}
        try:
            lcu = getattr(getattr(self, "skin_scraper", None), "lcu", None)
            if not lcu or not getattr(lcu, "ok", False):
                raise OnetricksError("Rose isn't connected to the League client yet")
            champions = lcu.get("/lol-game-data/assets/v1/champion-summary.json") or []
            names = {int(c["id"]): str(c["alias"]) for c in champions if c.get("alias") and int(c.get("id") or 0) > 0}
            # what each finished shop item gives (armour, magic resist, damage...), for the situational items
            items = lcu.get("/lol-game-data/assets/v1/items.json") or []
            categories = {int(i["id"]): i.get("categories") or [] for i in items if i.get("inStore") and not i.get("to")}
            wanted = payload.get("import")
            state = panel_state(
                lcu, names, int(payload.get("championId") or 0), str(payload.get("lane") or ""),
                [int(enemy) for enemy in payload.get("enemyIds") or []], int(payload.get("playerIndex") or 0),
                int(payload.get("versus", AUTO)),
                tuple(part for part in wanted if part in PARTS) if isinstance(wanted, list) else (), categories,
                build_index=int(payload.get("buildIndex") or 0),
            )
            response.update(state, success=True)
            try:  # the in-game guide follows the build that is on the panel when the game starts
                from main.game_build import save_game_build
                save_game_build(lcu, state["build"], int(payload.get("championId") or 0),
                                state["players"][state["playerIndex"]]["name"])
            except Exception:
                log.exception("Saving the build for the in-game guide failed")
        except OnetricksError as e:
            response.update(success=False, error=str(e))
        except Exception:
            log.exception("builds-get failed")
            response.update(success=False, error="Rose couldn't get a build (see Rose's log)")
        self._send_response(json.dumps(response))

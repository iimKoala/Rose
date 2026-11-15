#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The skins the user picks for other players' champions in champ select (the ROSE-OtherSkins plugin's panel)
Mixed into MessageHandler; the work is in injection/core/other_skins.py.
"""

import json
import logging

log = logging.getLogger(__name__)

MAX_CHAMPIONS = 10  # a game has nine other players


class OtherSkinHandlersMixin:
    """Needs self.shared_state, self.mod_storage, self.skin_scraper (for its lcu) and
    self._send_response(message: str) from MessageHandler."""

    def _route_other_skin_message(self, payload_type: str, payload: dict) -> bool:
        """Handle an other-skin* message. Returns False for any other type."""
        if payload_type == "other-skins-list":
            self._handle_other_skins_list(payload)
        elif payload_type == "other-skin-set":
            self._handle_other_skin_set(payload)
        else:
            return False
        return True

    def _other_skin_mods(self, champion_id: int) -> list:
        """The user's saved custom skins of a champion: [{"name", "path"}], the path relative to the mods folder."""
        storage = getattr(self, "mod_storage", None)
        if storage is None:
            return []
        mods = []
        for entry in storage.list_mods_for_champion(champion_id):
            try:
                path = str(entry.path.relative_to(storage.mods_root)).replace("\\", "/")
            except ValueError:
                continue
            mods.append({"name": entry.display_name or entry.mod_name, "path": path})
        return mods

    @staticmethod
    def _other_skin_choice(step) -> dict:
        return {"kind": step.kind, "skinId": step.skin_id, "modPath": step.mod_path} if step is not None else {"kind": "own"}

    def _handle_other_skins_list(self, payload: dict) -> None:
        """{"championIds"}: what the drop-down of each champion can offer (the skins Rose has, the user's custom
        skins) and what is picked now. The skins' names are the client's own: the panel reads them itself."""
        from injection.core import other_skins

        response = {"type": "other-skins-list-response", "requestId": payload.get("requestId"), "champions": {}}
        try:
            chosen = getattr(self.shared_state, "other_skins", None) or {}
            for raw in list(payload.get("championIds") or [])[:MAX_CHAMPIONS]:
                try:
                    champion_id = int(raw)
                except (TypeError, ValueError):
                    continue
                if champion_id <= 0:
                    continue
                response["champions"][str(champion_id)] = {
                    "skins": other_skins.shipped_skin_ids(champion_id),
                    "mods": self._other_skin_mods(champion_id),
                    "choice": self._other_skin_choice(chosen.get(champion_id)),
                }
        except Exception:
            log.exception("other-skins-list failed")
        self._send_response(json.dumps(response))

    def _handle_other_skin_set(self, payload: dict) -> None:
        """{"championId", "kind", "skinId", "modPath"}: the user's pick for a champion: "own" (their own skin),
        "default", "skin" (one Rose has) or "custom" (one of the user's saved skins of that champion)."""
        from injection.core import other_skins

        response = {"type": "other-skin-set-response", "requestId": payload.get("requestId"), "ok": False}
        try:
            champion_id = int(payload.get("championId") or 0)
            kind = str(payload.get("kind") or "own")
            skin_id = int(payload.get("skinId") or 0)
            mod_path = str(payload.get("modPath") or "")
            response["championId"] = champion_id
            # What comes from the panel is checked against what Rose itself offers for that champion
            known = (
                kind not in (other_skins.SKIN, other_skins.CUSTOM)
                or (kind == other_skins.SKIN and skin_id in other_skins.shipped_skin_ids(champion_id))
                or (kind == other_skins.CUSTOM and any(mod["path"] == mod_path for mod in self._other_skin_mods(champion_id)))
            )
            stem = self._other_skin_stem(champion_id) if known and kind != "own" else ""
            if known and (kind == "own" or stem):
                response["ok"] = other_skins.choose(self.shared_state, champion_id, stem, kind, skin_id, mod_path)
            if response["ok"]:
                log.info(f"[OTHERS] Champion {champion_id}: {kind}"
                         + (f" {skin_id}" if kind == other_skins.SKIN else f" {mod_path}" if kind == other_skins.CUSTOM else ""))
            chosen = getattr(self.shared_state, "other_skins", None) or {}
            response["choice"] = self._other_skin_choice(chosen.get(champion_id))
        except Exception:
            log.exception("other-skin-set failed")
        self._send_response(json.dumps(response))

    def _other_skin_stem(self, champion_id: int) -> str:
        """The champion's name in file names ("MonkeyKing"), from the League client; "" when it is not known."""
        lcu = getattr(getattr(self, "skin_scraper", None), "lcu", None)
        if not lcu or not getattr(lcu, "ok", False):
            return ""
        for champion in lcu.get("/lol-game-data/assets/v1/champion-summary.json") or []:
            if isinstance(champion, dict) and champion.get("id") == champion_id:
                return str(champion.get("alias") or "")
        return ""

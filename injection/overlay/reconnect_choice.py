#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The client's reconnect screen: leave some of this game's mods out of the game the player reconnects to.
Mixed into OverlayManager. Only the session's own thread talks to LTK Manager (the bridge is not shared
between threads): the other threads leave a request in the session, and its loop serves it.
"""

from typing import Iterable, Optional

from utils.core.logging import get_logger
from ..tools.bridge import BridgeCommandError, BridgeUnavailable
from .ltk_data import entry_name

log = get_logger()


class ReconnectChoiceMixin:
    """Needs _stop_patcher, _start_patcher, _wait_for_patcher and _running_game from OverlayManager."""

    _running_session: Optional[dict] = None  # the session _run_session serves now

    def reconnect_mods(self) -> Optional[dict]:
        """This game's mods for the reconnect screen: {"mods": [{"id", "name", "off"}], "status"}.

        None when no game session runs (Rose's mods are off already). "mods" is None until the session's
        thread has read them: ask again. "status" is "", "applying", "ready" or "failed".
        """
        session = self._running_session
        if session is None or session["ltf"].ended:
            return None
        if session.get("mods") is None:
            session["mods_wanted"] = True
        return {"mods": session.get("mods"), "status": session.get("leave_out_status") or ""}

    def leave_out_on_reconnect(self, mod_ids: Iterable[str]) -> str:
        """Ask the session to build the overlay again without *mod_ids*. "applying" when it will, else why
        not: "game-running" (a running game is never touched) or "unknown" (none of them is on in this game)."""
        session = self._running_session
        if session is None or session["ltf"].ended:
            return "unknown"
        still_on = {mod["id"] for mod in session.get("mods") or [] if not mod["off"]}
        wanted = {str(mod_id) for mod_id in mod_ids} & still_on
        if not wanted:
            return "unknown"
        if self._running_game() is not None:
            return "game-running"
        session["leave_out_status"] = "applying"
        session["leave_out"] = wanted
        return "applying"

    def _serve_reconnect_screen(self, session: dict) -> None:
        """The session loop's part, every tick: read the mods when asked, and apply a choice."""
        if session.get("mods_wanted"):
            session["mods_wanted"] = False
            session["mods"] = self._session_mods(session)
        leave_out = session.get("leave_out")
        if leave_out:
            session["leave_out"] = None
            session["leave_out_status"] = "ready" if self._restart_without(session, leave_out) else "failed"

    @staticmethod
    def _session_mods(session: dict) -> Optional[list]:
        """Rose's mods of this game as LTK Manager lists them; None when it can't be read (asked again)."""
        ltf = session["ltf"]
        try:
            library = ltf.bridge.library()
        except (BridgeUnavailable, BridgeCommandError) as e:
            log.warning(f"[INJECT] Could not read this game's mods for the reconnect screen: {e}")
            return None
        ours = set(ltf.imports) | set(ltf.switched_on)
        return [{"id": str(entry.get("id")), "name": entry_name(entry), "off": not entry.get("enabled")}
                for entry in library if str(entry.get("id") or "") in ours]

    def _restart_without(self, session: dict, mod_ids: set) -> bool:
        """Turn *mod_ids* off in LTK Manager and build the overlay again, for the game the player reconnects
        to. Whether all of them are off and the patcher is ready. The session's end handles them as any
        other mod of the game, so the choice lasts for this match only."""
        ltf = session["ltf"]
        names = {mod["id"]: mod["name"] for mod in session.get("mods") or []}
        log.info("[INJECT] Reconnect: leaving out " + ", ".join(names.get(mod_id, mod_id) for mod_id in sorted(mod_ids))
                 + " - building the overlay again without them")
        self._stop_patcher(session)
        off = set()
        for mod_id in sorted(mod_ids):
            try:
                ltf.bridge.toggle(mod_id, False)
                off.add(mod_id)
            except (BridgeUnavailable, BridgeCommandError) as e:
                log.warning(f"[INJECT] Could not turn off {names.get(mod_id, mod_id)}: {e}")
        for mod in session.get("mods") or []:
            mod["off"] = mod["off"] or mod["id"] in off
        # A Reconnect pressed while the overlay builds is held until the patcher scans, as at the game's start
        session["reconnects"] = 0
        if not self._start_patcher(session, report=False) or not self._wait_for_patcher(session):
            log.warning("[INJECT] Reconnect: the LTK patcher did not get ready again")
            return False
        # The game the player reconnects to reports to the patcher anew
        session["ltk_attached"] = False
        session["attach_logged"] = False
        session["ltk_late"] = False
        session["late_join_reported"] = False
        log.info("[INJECT] Reconnect: the LTK patcher is ready without them")
        return off == set(mod_ids)

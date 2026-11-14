# -*- coding: utf-8 -*-
"""
Mod check and repair without LTK Manager: runs rose-mod-check.exe, LTK Manager's
own rules (LeagueToolkit/ltk-manager, ltk-manager-problems v1.33.0) built as a
separate program in native/rose-mod-check (GPL-3.0-or-later). Rose only runs it
and reads the JSON verdict it prints, so Rose itself stays MIT.
"""

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional

from utils.core.logging import get_logger

log = get_logger()

CHECKER = Path(__file__).with_name("rose-mod-check.exe")
# The first check indexes the installed game; later ones take about a second
CHECK_TIMEOUT_S = 120
# LTK's severities: "fatal" (the game crashes on it) and "error" (the game rejects it)
REJECTED_SEVERITIES = ("fatal", "error")
# The archives rose-mod-check repairs (a .modpkg is checked, not repaired)
REPAIRABLE_SUFFIXES = (".fantome", ".zip")
# A repaired copy waits beside the mod under ModStorageService's temporary name, so one a stop
# leaves behind is never listed as a mod and the next start removes it
REPAIR_TEMP_PREFIX = ".rose-import-"


def league_root(game_dir) -> Optional[Path]:
    """The League of Legends folder LTK Manager's rules expect, from Rose's ...\\League of Legends\\Game"""
    if not game_dir:
        return None
    path = Path(game_dir)
    return path.parent if path.name.lower() == "game" else path


def _run(arguments: List[str], game_dir, name: str) -> Optional[dict]:
    """Run rose-mod-check with *arguments* and return the verdict it prints (None: no verdict)."""
    if not CHECKER.is_file():
        log.info("[MODCHECK] rose-mod-check.exe is missing - mods are not checked")
        return None
    command = [str(CHECKER), *arguments]
    league = league_root(game_dir)
    if league is not None:
        command += ["--league", str(league)]
    try:
        done = subprocess.run(command, capture_output=True, timeout=CHECK_TIMEOUT_S,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning(f"[MODCHECK] rose-mod-check did not finish on {name}: {type(e).__name__}")
        return None
    lines = done.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        verdict = json.loads(lines[-1]) if lines else {}
    except ValueError:
        verdict = {}
    if done.returncode != 0 or not isinstance(verdict, dict) or "health" not in verdict:
        reason = verdict.get("error") if isinstance(verdict, dict) else None
        log.warning(f"[MODCHECK] rose-mod-check could not check {name} "
                    f"(exit {done.returncode}): {reason or 'no verdict'}")
        return None
    return verdict


def check_mod_file(archive: Path, game_dir=None) -> Optional[dict]:
    """LTK Manager's verdict on one mod archive (.fantome, .zip, .modpkg).

    None when no verdict came (no checker, a timeout, a file it can't read):
    the caller goes on without a check, as it did when LTK Manager could not check.
    """
    return _run([str(archive)], game_dir, Path(archive).name)


def repair_mod_file(archive: Path, game_dir=None) -> Optional[dict]:
    """Repair what LTK Manager can repair in one .fantome (or .zip), as LTK Manager's repair does.

    rose-mod-check writes the repaired copy beside the mod, and the copy replaces the mod in
    one rename, so the mod is never half written. Returns the verdict of the mod as it is
    afterwards, with "repaired": the fixes applied (0: nothing changed); None when no repair ran.
    """
    archive = Path(archive)
    if archive.suffix.lower() not in REPAIRABLE_SUFFIXES:
        return None
    copy = archive.with_name(f"{REPAIR_TEMP_PREFIX}{uuid.uuid4().hex}.tmp")
    try:
        verdict = _run([str(archive), "--repair", str(copy)], game_dir, archive.name)
        if verdict is not None and int(verdict.get("repaired") or 0) > 0:
            if not copy.is_file():
                log.warning(f"[MODCHECK] rose-mod-check repaired {archive.name} but wrote no copy - kept the mod as it was")
                return None
            os.replace(copy, archive)
        return verdict
    except OSError as e:
        log.warning(f"[MODCHECK] Could not put the repaired {archive.name} in place: {e}")
        return None
    finally:
        copy.unlink(missing_ok=True)


def rejected(verdict: dict) -> List[dict]:
    """The problems the game rejects that LTK Manager can't repair: LTK Manager turns such a mod off in game.

    A problem LTK Manager can repair is not counted: check_mod repairs it, and a mod is kept either way.
    """
    return [
        {"rule": str(rule.get("rule") or ""), "title": str(rule.get("title") or ""),
         "description": str(rule.get("description") or "")}
        for rule in verdict.get("rules") or []
        if isinstance(rule, dict) and rule.get("severity") in REJECTED_SEVERITIES
        and int(rule.get("count") or 0) > int(rule.get("fixable") or 0)
    ]


def warnings(verdict: dict) -> List[dict]:
    """The flaws LTK Manager can't repair that don't stop the mod: it plays, with something missing (its sound...)"""
    return [
        {"rule": str(rule.get("rule") or ""), "title": str(rule.get("title") or ""),
         "description": str(rule.get("description") or "")}
        for rule in verdict.get("rules") or []
        if isinstance(rule, dict) and rule.get("severity") == "warning"
        and int(rule.get("count") or 0) > int(rule.get("fixable") or 0)
    ]

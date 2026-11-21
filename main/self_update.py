#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""An installed copy of this Rose updates while it runs.

`Start Rose.bat` brings a copy up to date before every start (scripts/rose_update.py). A Rose left open
for days never saw a new version. Now, while Rose runs, it asks GitHub for the newest version every half
hour (one small request; GitHub allows 60 an hour), downloads a new one without installing it (Rose is
running from those files), and asks once, when no game, queue or champion select is on, whether to restart
now. Yes: Rose leaves a note for `Start Rose.bat` and quits; the bat installs the update and starts Rose
again in the same window. No: the update is installed the next time Rose starts.

Nothing of this runs in a developer's copy (a folder with .git) or in a built Rose.exe.
Design: docs/install-from-github.md.
"""

import ctypes
import importlib.util
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from utils.core.logging import get_logger

log = get_logger()

ROOT = Path(__file__).resolve().parent.parent
UPDATER = Path("scripts") / "rose_update.py"
RESTART_MARKER = ".rose-restart"  # Start Rose.bat: Rose asked to be started again
FIRST_CHECK_S = 5 * 60    # the start itself just updated
CHECK_EVERY_S = 30 * 60
LOOK_EVERY_S = 5.0        # how often a waiting update looks whether the user is free
# Not asked during these: a restart of Rose restarts the League client, and a window over a game is a nuisance
BUSY_PHASES = frozenset({"Matchmaking", "ReadyCheck", "ChampSelect", "GameStart", "InProgress", "Reconnect",
                         "WaitingForStats", "PreEndOfGame"})
_MB_YESNO, _MB_ICONINFORMATION, _MB_SETFOREGROUND, _MB_TOPMOST, _IDYES = 0x4, 0x40, 0x10000, 0x40000, 6


def load_updater(root: Path = ROOT):
    """scripts/rose_update.py of this copy, as a module (it is a script, not part of a package)"""
    spec = importlib.util.spec_from_file_location("rose_update", root / UPDATER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ask_restart(version: str) -> bool:
    """Ask the user whether Rose restarts now to install the downloaded version"""
    text = ("A new version of Rose was downloaded.\n\n"
            "Restart Rose now to install it? Rose restarts the League client when it starts.\n\n"
            "No: it is installed the next time you start Rose.")
    return ctypes.windll.user32.MessageBoxW(None, text, f"Rose update ({version[:8]})",
                                            _MB_YESNO | _MB_ICONINFORMATION | _MB_SETFOREGROUND | _MB_TOPMOST) == _IDYES


class UpdateWatcher(threading.Thread):
    """Downloads a new version while Rose runs and asks, when the user is free, to restart."""

    def __init__(self, state, quit_rose: Callable[[], None], updater=None, ask: Callable[[str], bool] = ask_restart,
                 root: Path = ROOT) -> None:
        super().__init__(name="UpdateWatcher", daemon=True)
        self.state, self.quit_rose, self.ask, self.root = state, quit_rose, ask, Path(root)
        self.updater = updater if updater is not None else load_updater(self.root)
        self.ready = ""  # the version downloaded and waiting
        self.told = ""   # the version the user was asked about: once is enough
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def check(self) -> None:
        """One look at GitHub. Whatever goes wrong (no internet, GitHub's limit) waits for the next look."""
        try:
            version = self.updater.stage(self.root)
        except Exception as e:  # noqa: BLE001 - an update that cannot be fetched must never disturb Rose
            log.debug(f"[UPDATE] No look at GitHub this time: {type(e).__name__}: {e}")
            return
        if version and version != self.ready:
            log.info(f"[UPDATE] Version {version[:8]} is downloaded; it is installed at the next start")
        self.ready = version or ""

    def free(self) -> bool:
        """Whether nothing is on that a question, or a restart, would disturb"""
        return getattr(self.state, "phase", None) not in BUSY_PHASES

    def tell_if_free(self) -> bool:
        """Ask about a waiting version once, when the user is free. True when Rose is restarting."""
        if not self.ready or self.ready == self.told or not self.free():
            return False
        self.told = self.ready
        if not self.ask(self.ready):
            log.info("[UPDATE] The user keeps playing: the update is installed at the next start")
            return False
        if not self.free():  # a game was found while the question stood open
            log.info("[UPDATE] A game started meanwhile: the update is installed at the next start")
            return False
        log.info("[UPDATE] Restarting Rose to install the update")
        (self.root / RESTART_MARKER).write_text(self.ready, encoding="utf-8")
        self.quit_rose()
        return True

    def run(self) -> None:
        next_check = time.monotonic() + FIRST_CHECK_S
        while not self._halt.wait(LOOK_EVERY_S):
            if time.monotonic() >= next_check:
                self.check()
                next_check = time.monotonic() + CHECK_EVERY_S
            try:
                if self.tell_if_free():
                    return
            except Exception as e:  # noqa: BLE001
                log.warning(f"[UPDATE] Could not ask about the update: {e}")


def start(state, quit_rose: Callable[[], None], root: Path = ROOT) -> Optional[UpdateWatcher]:
    """Start the watcher for an installed copy; None for a developer's copy, a built Rose.exe, or a copy
    without its updater. Never raises: Rose starts either way."""
    try:
        root = Path(root)
        (root / RESTART_MARKER).unlink(missing_ok=True)  # a note nobody read must not restart Rose at its next quit
        if getattr(sys, "frozen", False) or (root / ".git").exists() or not (root / UPDATER).is_file():
            return None
        watcher = UpdateWatcher(state, quit_rose, root=root)
        watcher.start()
        log.info("[UPDATE] Looking for new versions while Rose runs (every 30 minutes)")
        return watcher
    except Exception as e:  # noqa: BLE001
        log.warning(f"[UPDATE] Not looking for new versions while Rose runs: {e}")
        return None

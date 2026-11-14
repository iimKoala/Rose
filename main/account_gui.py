#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rose's own windows (the Account window and the Mod store, each a program of its own): starting them,
bringing an open one to the front, and closing the ones an earlier Rose left open.
"""

import ctypes
import importlib.util
import subprocess
import sys
from pathlib import Path

from utils.core.logging import get_logger
from utils.core.paths import get_app_dir

log = get_logger()

_store_proc = None
STORE_TITLE = "Rose - Mod store"  # main/mod_store.py's window title; a status may follow it
ACCOUNTS_TITLE = "Rose - Accounts"  # main/account_window.py's window title
ROSE_WINDOW_TITLES = (ACCOUNTS_TITLE, STORE_TITLE, "Rose - Installed mods", "Rose - Install mod")


def _rose_windows(*titles: str) -> list:
    """Handles of Rose's own visible windows whose title starts with one of *titles*"""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(handle, _):
        title, kind = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(handle, title, 64)
        user32.GetClassNameW(handle, kind, 64)
        # The window class too (pywebview's windows): a browser tab could carry the same title
        if title.value.startswith(titles) and kind.value.startswith("WindowsForms") and user32.IsWindowVisible(handle):
            found.append(handle)
        return True

    user32.EnumWindows(visit, 0)
    return found


def close_leftover_windows() -> int:
    """Close the Account and store windows an earlier Rose left open; called once when Rose starts.

    They are separate programs that outlive Rose and keep running the code they started with
    (Nov 10: a window from before a fix switched accounts the old way). Returns how many it closed.
    """
    handles = _rose_windows(*ROSE_WINDOW_TITLES)
    for handle in handles:
        ctypes.windll.user32.PostMessageW(handle, 0x0010, 0, 0)  # WM_CLOSE, as the window's own X does
    if handles:
        log.info(f"Closed {len(handles)} Rose window(s) left open by an earlier Rose")
    try:  # and the in-game strip and gold board, which would go on drawing what they last knew
        from main.game_build import end_running_overlays

        ended = end_running_overlays()
        if ended:
            log.info(f"Ended {ended} in-game program(s) left running by an earlier Rose")
    except Exception as e:
        log.debug(f"Could not look for in-game programs left running: {e}")
    return len(handles)


def _show_open_store() -> bool:
    """Bring the mod store's window to the front if one is open, whichever Rose process opened it"""
    return _show_window(STORE_TITLE)


def _show_window(title: str) -> bool:
    """Bring Rose's window with this title to the front; False if none is open"""
    user32 = ctypes.windll.user32
    found = _rose_windows(title)
    if not found:
        return False
    if not user32.IsIconic(found[0]):
        user32.ShowWindow(found[0], 6)  # SW_MINIMIZE: from a background program a plain SetForegroundWindow only flashes the taskbar
    user32.ShowWindow(found[0], 9)  # SW_RESTORE
    user32.SetForegroundWindow(found[0])
    return True


def open_mod_store() -> None:
    """Start the mod store window, or bring it to the front if it is already open."""
    global _store_proc
    if _show_open_store():
        log.info("Mod store is already open: brought it to the front")
        return
    if _store_proc is not None and _store_proc.poll() is None:
        log.info("Mod store is still starting")
        return
    rose_dir = Path(__file__).resolve().parent.parent
    # The file itself, not "-m main.mod_store": importing the main package loads all of Rose first (0.8 s, against 0.5 s)
    _store_proc = subprocess.Popen(
        [sys.executable, "-c", "import runpy; runpy.run_path('main/mod_store.py', run_name='__main__')"],
        cwd=str(rose_dir),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.info("Mod store started")


_window_proc = None  # the account window (main/account_window.py as its own program), one at a time
# Runs main/account_window.py with an empty stand-in for the main package, so main/__init__.py, which loads
# all of Rose, is not run first (0.85 s against 0.6 s, Nov 11). The window only imports files of the main folder.
ACCOUNT_WINDOW_START = (
    "import sys, types; package = types.ModuleType('main'); package.__path__ = ['main']; "
    "sys.modules['main'] = package; import runpy; runpy.run_module('main.account_window', run_name='__main__')"
)


def open_account_switcher_thread() -> None:
    """Open the account window (main/account_window.py as its own program), or bring it to the front if it is open."""
    global _window_proc
    if importlib.util.find_spec("webview") is None or getattr(sys, "frozen", False):
        log.error("The account window needs pywebview and a Rose run from source (pip install -r requirements-run.txt)")
        return
    if _window_proc is not None and _window_proc.poll() is None:
        _show_window(ACCOUNTS_TITLE)
        log.info("Account window is already open: brought it to the front")
        return
    _window_proc = subprocess.Popen(
        [sys.executable, "-c", ACCOUNT_WINDOW_START],
        cwd=str(get_app_dir()),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.info("Account window started")

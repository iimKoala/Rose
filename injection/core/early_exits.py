"""Early exit detector for Rose.

Reads the game's own log file after a game ends and counts how many
games in a row left play within seconds of the loading screen.
Other code turns the mods switch off when this file says so.
It only reads the game's own log and counts; it loads nothing and hides nothing.
"""

import re
from pathlib import Path
from typing import Optional

EARLY_EXIT_S = 10.0  # play that ends this soon after the loading screen was not ended by hand
IN_A_ROW = 2         # this many such games in a row: Rose turns its mods off
_LINE_TIME = re.compile(r"^(\d+\.\d+)\|")


def played_seconds(log_text: str) -> Optional[float]:
    """Return how long the game stayed in GAMESTATE_GAMELOOP, or None."""
    enter_time: Optional[float] = None
    leave_time: Optional[float] = None
    found_enter = False
    for line in log_text.splitlines():
        match = _LINE_TIME.match(line)
        if not match:
            continue
        time_val = float(match.group(1))
        if "to GAMESTATE_GAMELOOP" in line and not found_enter:
            enter_time = time_val
            found_enter = True
        elif "from GAMESTATE_GAMELOOP to" in line and found_enter and leave_time is None:
            leave_time = time_val
            break
    if enter_time is None or leave_time is None:
        return None
    return leave_time - enter_time


def newest_game_log(game_dir) -> Optional[Path]:
    """Return the path to the newest r3dlog.txt, or None."""
    if game_dir is None:
        return None
    try:
        logs = Path(game_dir).parent / "Logs" / "GameLogs"
        if not logs.is_dir():
            return None
        folders = [f for f in logs.iterdir() if f.is_dir()]
        if not folders:
            return None
        newest = sorted(folders)[-1]
        files = sorted(newest.glob("*r3dlog.txt"))
        return files[0] if files else None
    except OSError:
        return None


def read_played(game_dir) -> Optional[float]:
    """Read the newest game log and return played_seconds, or None."""
    path = newest_game_log(game_dir)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return played_seconds(text)
    except OSError:
        return None


class EarlyExits:
    """Counts consecutive games that left play early with mods in them."""

    def __init__(self) -> None:
        self.count = 0

    def game_over(self, played: Optional[float], with_mods: bool) -> bool:
        """Return True when Rose should turn its mods off now."""
        if not with_mods:
            return False
        if played is None:
            return False
        if played >= EARLY_EXIT_S:
            self.count = 0
            return False
        self.count += 1
        if self.count >= IN_A_ROW:
            self.count = 0
            return True
        return False

"""Mods switch: controls whether Rose loads mods into the game.
The switch is stored in a small text file in Rose's data folder.
When the file exists, mods are OFF; when it does not exist, mods are ON.
Off means Rose loads nothing into the game; nothing is hidden."""

import time
from pathlib import Path
from typing import Optional

FLAG = "mods-off.txt"  # in Rose's data folder: it exists while mods are off; its text is the reason


def flag_file() -> Optional[Path]:
    """Return the path to the flag file, or None if the data folder cannot be found."""
    try:
        from utils.core.paths import get_user_data_dir
        return get_user_data_dir() / FLAG
    except Exception:
        return None


def is_off() -> bool:
    """Return True only when the flag file exists; False otherwise."""
    path = flag_file()
    if path is None:
        return False
    try:
        return path.is_file()
    except OSError:
        return False


def reason() -> str:
    """Return the first line of the flag file, or "" when mods are on or the file cannot be read."""
    path = flag_file()
    if path is None:
        return ""
    try:
        text = path.read_text(encoding="utf-8-sig")
        first_line = text.splitlines()[0] if text else ""
        return first_line.strip()
    except (OSError, ValueError):
        return ""


def turn_off(why: str) -> bool:
    """Write the flag file with the reason and current time; return True on success."""
    path = flag_file()
    if path is None:
        return False
    try:
        cleaned = " ".join(why.split())  # every kind of line break: a "\r" left in would end the first line too
        if not cleaned:
            cleaned = "switched off"
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        text = f"{cleaned}\n{timestamp}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def turn_on() -> bool:
    """Remove the flag file; return True when mods are on afterwards."""
    path = flag_file()
    if path is None:
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


# Only a Rose that armed the switch at its own start obeys it. The tests and tools that build the injection
# run on the developer's PC too, and that PC's file must never reach them.
_armed = False


def arm() -> None:
    """Rose's start: from now on the injection asks the switch."""
    global _armed
    _armed = True


def off_now() -> bool:
    """What the injection asks before it starts anything: off only in a Rose that armed the switch."""
    return _armed and is_off()

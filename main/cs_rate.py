"""Calculate CS per minute from the game's local data dict.

The game's creepScore is reported to move in steps of 10 (0, 10, 20…)
on purpose. This is reported, not verified, Nov 21 2026.
"""

from typing import Optional

STEP = 10  # the steps the game's count is said to move in
MIN_GAME_S = 90.0  # before this the number says nothing: the first minions die at about 1:30


def read_cs(data: dict) -> Optional[tuple]:
    """Return (creep score, game time in seconds) or None."""
    active = data.get("activePlayer") or {}
    me = active.get("riotId") or active.get("summonerName")
    players = data.get("allPlayers") or []
    game_data = data.get("gameData") or {}
    game_time = game_data.get("gameTime")
    if game_time is None:
        return None
    if not me:
        return None
    for p in players:
        if not isinstance(p, dict):
            continue
        if me in (p.get("riotId"), p.get("summonerName")):
            scores = p.get("scores") or {}
            cs = scores.get("creepScore")
            if cs is not None:
                return (int(cs), float(game_time))
    return None


class CsRate:
    """Track CS rate across updates, handling step-based counts."""

    def __init__(self) -> None:
        self.cs: Optional[int] = None
        self.changed_at: float = 0.0
        self.exact: bool = False

    def update(self, cs: int, game_time: float) -> Optional[float]:
        """Update with a new count, return rate or None if too early."""
        if cs != self.cs:
            self.cs = cs
            self.changed_at = game_time
        if cs % STEP != 0:
            self.exact = True
        if game_time < MIN_GAME_S:
            return None
        minutes = game_time / 60
        if self.exact:
            return cs / minutes
        at_change = cs / (max(self.changed_at, 1.0) / 60)
        at_most = (cs + STEP - 1) / minutes
        return min(at_change, at_most)


def label(rate: Optional[float]) -> str:
    """Return a display string for the rate."""
    if rate is None:
        return "CS/min \u2013"
    return f"CS/min {rate:.1f}"

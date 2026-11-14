#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gold in items, lane against lane, for the board over the game's scoreboard (main/gold_board.py).

Only arithmetic on what the game's own "Live Client Data" answers (every player's items are on the
scoreboard anyway) and the shop prices the League client gave Rose. Design: docs/in-game-gold-board.md.
"""

from typing import Optional

LANES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")  # the scoreboard's order, as the game names the lanes


def item_gold(player: dict, prices: dict) -> int:
    """What the items a player holds cost in the shop"""
    return sum(int(prices.get(int(item.get("itemID") or 0), 0)) * max(1, int(item.get("count") or 1))
               for item in player.get("items") or [])


def by_lane(team: list) -> list:
    """The team from top to support when the game gave each of the five lanes to one player; else as listed"""
    lanes = [str(player.get("position") or "").upper() for player in team]
    if sorted(lanes) != sorted(LANES):
        return team
    return sorted(team, key=lambda player: LANES.index(str(player.get("position")).upper()))


def lane_gold(data: dict, prices: dict) -> Optional[dict]:
    """{"mine": "left" or "right", "rows": [[left, right], ...]}: per lane the gold in items of the blue
    team's player (left) and the red team's (right), None where a team has no player; "mine" is the side
    of the player at this computer. None when that player isn't in the game's data."""
    active = data.get("activePlayer") or {}
    me = active.get("riotId") or active.get("summonerName")
    players = [player for player in data.get("allPlayers") or [] if isinstance(player, dict)]
    team = next((player.get("team") for player in players
                 if me and me in (player.get("riotId"), player.get("summonerName"))), None)
    if team not in ("ORDER", "CHAOS"):
        return None
    left = by_lane([player for player in players if player.get("team") == "ORDER"])
    right = by_lane([player for player in players if player.get("team") == "CHAOS"])
    rows = [[item_gold(left[i], prices) if i < len(left) else None,
             item_gold(right[i], prices) if i < len(right) else None]
            for i in range(max(len(left), len(right)))]
    return {"mine": "left" if team == "ORDER" else "right", "rows": rows}


def compare(own: Optional[int], other: Optional[int]) -> str:
    """The sign beside a player's gold: ">" with more than the opponent, "<" with less, "=" with the same;
    "" without an opponent"""
    if own is None or other is None:
        return ""
    return ">" if own > other else "<" if own < other else "="

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What deeplol.gg adds to a player's stats: the season's losses (so a win rate), the peak, the ladder position.

The site's pages hold no data: it all comes from the data service the site itself asks
(b2c-api-cdn.deeplol.gg). That is not an official API: it can change or stop answering, and then the panel
just shows what the League client gave. Two questions a player, asked only about the other players of a game
the user is in; the user's own account is never sent. Design: docs/player-stats-panel.md.
"""

from typing import Optional

import requests

SERVICE = "https://b2c-api-cdn.deeplol.gg"
# The League client's region -> deeplol's platform id
PLATFORMS = {"NA": "NA1", "EUW": "EUW1", "EUNE": "EUN1", "KR": "KR", "JP": "JP1", "BR": "BR1",
             "LAN": "LA1", "LAS": "LA2", "OCE": "OC1", "TR": "TR1", "RU": "RU"}
TIMEOUT_S = 6.0
STATS_TIMEOUT_S = 10.0  # the champion stats are a large answer (2 MB unpacked for a player with many games)
NO_RANK = {"wins": 0, "losses": 0, "ladderRank": 0, "ladderPercent": None, "peakTier": "", "peakLp": 0}
_season = []  # deeplol's number for the season being played, asked once


def new_session() -> requests.Session:
    """One kept connection for a game's questions, with a plain browser name: nothing about the user or Rose"""
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    return session


def solo_extras(solo) -> Optional[dict]:
    """The numbers the panel uses, from deeplol's solo queue answer; None when it has no rank in it"""
    if not isinstance(solo, dict) or not solo.get("tier"):
        return None
    percent = solo.get("ranking_rate")  # already a percentage: 0.0003 is the top 0.0003 %; -1 when deeplol has none
    return {"wins": int(solo.get("wins") or 0), "losses": int(solo.get("losses") or 0),
            "ladderRank": max(0, int(solo.get("ranking") or 0)),
            "ladderPercent": float(percent) if isinstance(percent, (int, float)) and percent > 0 else None,
            # the peak comes as a tier, with its division when it has one ("PLATINUM I", "MASTER"), and its LP
            "peakTier": str(solo.get("high_tier") or ""), "peakLp": int(solo.get("high_lp") or 0)}


def current_season(session) -> Optional[int]:
    """deeplol's number for the season being played (its champion stats are asked by season); asked once"""
    if not _season:
        try:
            listed = (session.get(f"{SERVICE}/common/season-list", timeout=TIMEOUT_S).json() or {}).get("season_list") or []
            _season.append(max(int(season) for season in listed))
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            return None
    return _season[0]


def champion_record(stats, champion_id: int) -> Optional[dict]:
    """{"championWins", "championLosses"}: a player's solo queue games on one champion this season, from
    deeplol's champion stats answer (zeros when the player has none on it); None when it can't be read"""
    try:
        played = stats["counter_champion_stats"]["ranked_solo_5x5"]["enemy_champion_stats"]["All"]
        entry = next((entry for entry in played if int(entry.get("champion_id") or 0) == champion_id), {})
        return {"championWins": int(entry.get("wins") or 0), "championLosses": int(entry.get("losses") or 0)}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _champion_record(session, puuid: str, platform: str, champion_id: int) -> Optional[dict]:
    """champion_record for a player deeplol knows; None when it doesn't answer"""
    season = current_season(session)
    if season is None:
        return None
    try:
        answer = session.get(f"{SERVICE}/summoner/champion-stat", timeout=STATS_TIMEOUT_S,
                             params={"puu_id": puuid, "season": season, "platform_id": platform})
        return champion_record(answer.json(), champion_id) if answer.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def player_extras(session, name: str, tag: str, region: str = "NA", champion_id: int = 0) -> Optional[dict]:
    """{"wins", "losses", "ladderRank", "ladderPercent", "peakTier", "peakLp"} of a player's solo queue on deeplol; None when
    deeplol doesn't know the player, doesn't answer, or the region is one this file has no platform for.
    With *champion_id* also "championWins" and "championLosses" on that champion, when deeplol gives them
    (a third question; for a player without a rank they come with NO_RANK's zeros)."""
    platform = PLATFORMS.get(str(region or "").upper())
    if not (name and tag and platform):
        return None
    try:
        found = session.get(f"{SERVICE}/summoner/summoner", timeout=TIMEOUT_S,
                            params={"riot_id_name": name, "riot_id_tag_line": tag, "platform_id": platform})
        info = (found.json() or {}).get("summoner_basic_info_dict") or {}
        if found.status_code != 200 or not info.get("puu_id"):
            return None
        now = session.get(f"{SERVICE}/summoner/summoner-realtime", timeout=TIMEOUT_S,
                          params={"platform_id": platform, "summoner_id": info.get("summoner_id") or "", "puu_id": info["puu_id"]})
        if now.status_code != 200:
            return None
        extras = solo_extras(((now.json() or {}).get("season_tier_info_dict") or {}).get("ranked_solo_5x5"))
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return None
    record = _champion_record(session, info["puu_id"], platform, champion_id) if champion_id else None
    return {**(extras or NO_RANK), **record} if record else extras

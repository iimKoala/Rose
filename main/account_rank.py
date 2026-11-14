# -*- coding: utf-8 -*-
"""
Account Rank - Read current account rank from the League client LCU API
"""

from typing import Optional, Dict, Any
from urllib.parse import quote

from lcu.core.client import LCU


def _solo_rank(ranked_stats: dict) -> Dict[str, Any]:
    """Tier, division, LP and last season's end rank in solo queue, from the client's ranked stats"""
    solo_queue = next((queue for queue in ranked_stats.get("queues") or []
                       if queue.get("queueType") == "RANKED_SOLO_5x5"), None) or {}
    # "NA" is the client's word for no division: unranked, and Master and above
    division = solo_queue.get("division", "")
    prev_tier = solo_queue.get("previousSeasonEndTier", "")
    prev_div = solo_queue.get("previousSeasonEndDivision", "")
    return {
        "tier": solo_queue.get("tier", ""),
        "division": "" if division == "NA" else division,
        "lp": solo_queue.get("leaguePoints", 0),
        "last_season": f"{prev_tier} {'' if prev_div == 'NA' else prev_div}".strip() if prev_tier else "",
    }


def read_current_account(lcu: LCU) -> Optional[Dict[str, Any]]:
    """Read the current account's summoner info and rank from the LCU.

    Returns a dict with username (the Riot login name), riot_id, level, tier,
    division, lp and last_season, or None if the client isn't ready or the requests fail.
    """
    if not lcu.ok:
        return None

    # Which login is signed in; used to match the saved account
    try:
        login_session = lcu.get("/lol-login/v1/session")
    except Exception:
        return None
    username = (login_session or {}).get("username", "")
    if not username:
        return None

    # Get current summoner info
    summoner = None
    try:
        summoner = lcu.get("/lol-summoner/v1/current-summoner")
    except Exception:
        return None

    if not summoner:
        return None

    # Get ranked stats
    ranked_stats = None
    try:
        ranked_stats = lcu.get("/lol-ranked/v1/current-ranked-stats")
    except Exception:
        return None

    if not ranked_stats:
        return None

    # Build riot_id from gameName and tagLine
    game_name = summoner.get("gameName", "")
    tag_line = summoner.get("tagLine", "")
    riot_id = f"{game_name}#{tag_line}" if tag_line else game_name

    return {
        "username": username,
        "riot_id": riot_id,
        "level": summoner.get("summonerLevel", 0),
        **_solo_rank(ranked_stats),
    }


def read_other_account(lcu: LCU, riot_id: str) -> Optional[Dict[str, Any]]:
    """Look up another player's solo queue rank through the signed-in client, as its profile search does.

    Only players of the signed-in account's server have a rank there. Returns tier, division, lp,
    last_season and level, or None if the player isn't found or the requests fail.
    """
    name, _, tag = riot_id.partition("#")
    if not lcu.ok or not name or not tag:
        return None
    try:
        found = lcu.get(f"/lol-summoner/v1/alias/lookup?gameName={quote(name)}&tagLine={quote(tag)}") or {}
        if not found.get("puuid"):  # older clients: the lookup by full name
            found = lcu.get("/lol-summoner/v1/summoners?name=" + quote(riot_id)) or {}
        puuid = found.get("puuid")
        if not puuid:
            return None
        ranked_stats = lcu.get(f"/lol-ranked/v1/ranked-stats/{quote(str(puuid))}")
        summoner = lcu.get(f"/lol-summoner/v2/summoners/puuid/{quote(str(puuid))}") or {}
    except Exception:
        return None
    if not ranked_stats:
        return None
    return {**_solo_rank(ranked_stats), "level": summoner.get("summonerLevel", 0)}

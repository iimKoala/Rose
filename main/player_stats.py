#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The players of the game that is starting, for the in-game stats panel (main/stats_panel.py, Ctrl+X).

The League client itself knows, the moment a game starts, who plays which champion in which role, and each
player's solo queue rank, LP, wins and highest tier of the season: that is saved first. It gives the losses
of the user's own account only (checked in a real game, Nov 14: 0 for the nine others), so deeplol.gg then
adds the other players' losses, and their peak LP and ladder position (main/deeplol.py); the user's own
account is never sent anywhere. Saved to state/build_guide/player_stats.json, which the strip's program reads.
Design: docs/player-stats-panel.md.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from main.game_build import guide_dir

LANES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")  # the scoreboard's order, as the client names the roles
STATS_FILE = "player_stats.json"
RANKED_QUEUES = (420, 440)  # solo/duo and flex, in the client's match history
SESSION_TRIES, SESSION_WAIT_S = 10, 3.0  # the client can need a moment to list both teams


def solo_queue(ranked) -> dict:
    """Rank, LP, wins, losses and the season's highest tier in solo queue, from the client's ranked stats"""
    queues = ranked.get("queues") if isinstance(ranked, dict) else None
    solo = next((queue for queue in queues or [] if isinstance(queue, dict) and queue.get("queueType") == "RANKED_SOLO_5x5"), None) or {}
    clean = lambda word: "" if word in (None, "NA", "NONE") else str(word)  # the client's words for "none"
    return {"tier": clean(solo.get("tier")), "division": clean(solo.get("division")), "lp": int(solo.get("leaguePoints") or 0),
            "wins": int(solo.get("wins") or 0), "losses": int(solo.get("losses") or 0),
            "peakTier": clean(solo.get("highestTier")), "peakDivision": clean(solo.get("highestDivision"))}


def in_role_order(team: list) -> list:
    """The team from top to support when each of the five roles has one player; else as the client lists it"""
    if sorted(player["position"] for player in team) != sorted(LANES):
        return team
    return sorted(team, key=lambda player: LANES.index(player["position"]))


def with_unlisted(game: dict, own_puuid: str = "") -> list:
    """The client's two teams, with a player it names only among the champion picks put on the shorter team,
    in that team's one open role (a real ranked game listed four players on one team, Nov 14). With teams of
    the same size there is no telling whose player it is, so it stays out.

    Such a player hides their name (streamer mode): they get their slot marked "hidden", without their
    account id, so nothing is looked up about them. The user's own account (*own_puuid*) is not hidden."""
    sides = [list(game.get("teamOne") or []), list(game.get("teamTwo") or [])]
    listed = {player.get("puuid") for side in sides for player in side if isinstance(player, dict)}
    for pick in game.get("playerChampionSelections") or []:
        puuid = pick.get("puuid") if isinstance(pick, dict) else None
        if not puuid or puuid in listed or len(sides[0]) == len(sides[1]):
            continue
        side = min(sides, key=len)
        taken = {str(player.get("selectedPosition") or "").upper() for player in side if isinstance(player, dict)}
        open_roles = [lane for lane in LANES if lane not in taken]
        side.append({"puuid": puuid if puuid == own_puuid else "", "hidden": puuid != own_puuid, "championId": pick.get("championId"),
                     "selectedPosition": open_roles[0] if len(open_roles) == 1 else ""})
        listed.add(puuid)
    return sides


def own_champion_record(lcu, champion_id: int) -> Optional[tuple]:
    """(wins, losses) on a champion in the user's own last ranked games, of the 20 games the League client
    lists; None when the client doesn't give them. The user's account is never sent to deeplol, so this is
    what its card shows instead of a season's record."""
    history = lcu.get("/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=19", timeout=5.0)
    try:
        won = []
        for game in history["games"]["games"]:
            mine = game["participants"][0]
            if game.get("queueId") in RANKED_QUEUES and int(mine.get("championId") or 0) == champion_id:
                won.append(bool((mine.get("stats") or {}).get("win")))
        return sum(won), len(won) - sum(won)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None  # an answer in another shape: no record, never a failed collection


def read_players(lcu) -> Optional[dict]:
    """{"gameId", "region", "teams": [my team, the other team]} from the client, each team in role order and
    each player with champion, name, level and solo queue numbers; None when the client lists no players."""
    game = (lcu.get("/lol-gameflow/v1/session") or {}).get("gameData") or {}
    me = (lcu.get("/lol-summoner/v1/current-summoner") or {}).get("puuid")
    sides = with_unlisted(game, me or "")
    if not any(sides):
        return None
    champions = {int(c["id"]): str(c.get("name") or "") for c in lcu.get("/lol-game-data/assets/v1/champion-summary.json") or []
                 if isinstance(c, dict) and c.get("id") is not None}
    teams = []
    for side in sides:
        team = []
        for listed in side:
            if not isinstance(listed, dict):
                continue
            puuid = listed.get("puuid") or ""
            who = (lcu.get(f"/lol-summoner/v2/summoners/puuid/{puuid}") or {}) if puuid else {}
            ranked = (lcu.get(f"/lol-ranked/v1/ranked-stats/{puuid}") or {}) if puuid else {}
            team.append({"position": str(listed.get("selectedPosition") or "").upper(),
                         "championId": int(listed.get("championId") or 0), "championWins": 0, "championLosses": 0,
                         "championKnown": False, "championRecent": False,
                         "champion": champions.get(int(listed.get("championId") or 0), ""),
                         "name": str(who.get("gameName") or listed.get("summonerName") or ""), "tag": str(who.get("tagLine") or ""),
                         "level": int(who.get("summonerLevel") or 0), "me": bool(puuid) and puuid == me,
                         # hides their name (streamer mode): left off the team list, or listed with no account and no name (a bot has a name)
                         "hidden": bool(listed.get("hidden")) or not (puuid or listed.get("summonerName")),
                         "ladderRank": 0, "ladderPercent": None, "peakLp": 0, **solo_queue(ranked)})
            # The client tells the losses of the user's own account only: without them there is no win rate
            team[-1]["lossesKnown"] = team[-1]["me"] or team[-1]["losses"] > 0
        teams.append(in_role_order(team))
    for player in teams[0] + teams[1]:
        record = own_champion_record(lcu, player["championId"]) if player["me"] and player["championId"] else None
        if record:
            player.update(championWins=record[0], championLosses=record[1], championKnown=True, championRecent=True)
    if any(player["me"] for player in teams[1]):
        teams.reverse()  # my team first
    region = (lcu.get("/riotclient/region-locale") or {}).get("region") or ""
    return {"gameId": game.get("gameId"), "region": str(region), "teams": teams}


def add_extras(stats: dict, lookup: Callable) -> int:
    """Ask *lookup(name, tag, region, champion id)* (deeplol) about every player but the user, a few at a time,
    and add what it knows; returns how many players it knew. A player it doesn't know keeps the client's numbers."""
    others = [player for team in stats["teams"] for player in team if not player["me"] and player["name"] and player["tag"]]
    with ThreadPoolExecutor(max_workers=5) as pool:
        answers = list(pool.map(lambda player: lookup(player["name"], player["tag"], stats["region"], player.get("championId") or 0), others))
    for player, extras in zip(others, answers):
        if extras:
            player.update(ladderRank=extras["ladderRank"], ladderPercent=extras["ladderPercent"], peakLp=extras["peakLp"],
                          peakTier=extras["peakTier"] or player["peakTier"])
            if extras["wins"] + extras["losses"] > 0:
                player.update(wins=extras["wins"], losses=extras["losses"], lossesKnown=True)
            if extras["peakTier"]:
                player["peakDivision"] = ""  # deeplol's peak is a tier and its LP
            if "championWins" in extras:
                player.update(championWins=extras["championWins"], championLosses=extras["championLosses"], championKnown=True)
    return sum(1 for extras in answers if extras)


def save(stats: dict) -> None:
    """Write the stats for the strip's program, whole or not at all (it may be reading at this moment)"""
    folder = guide_dir()
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / (STATS_FILE + ".part")
    partial.write_text(json.dumps(dict(stats, savedAt=time.time())), encoding="utf-8")
    os.replace(partial, folder / STATS_FILE)


def load() -> Optional[dict]:
    """The saved stats, or None when there are none (or they can't be read)"""
    try:
        stats = json.loads((guide_dir() / STATS_FILE).read_text(encoding="utf-8"))
        return stats if isinstance(stats.get("teams"), list) else None
    except (OSError, ValueError, AttributeError):
        return None


def collect(lcu, log, lookup: Optional[Callable] = None, wait: Callable = time.sleep) -> bool:
    """Save the stats of the game that is starting: the client's at once, then deeplol's extras. Run in a
    thread of its own when a game starts; False when the client never listed the players."""
    try:
        (guide_dir() / STATS_FILE).unlink(missing_ok=True)  # the last game's players are not this game's
    except OSError:
        pass
    stats = None
    for _ in range(SESSION_TRIES):
        stats = read_players(lcu)
        if stats is not None:
            break
        wait(SESSION_WAIT_S)
    if stats is None:
        log.info("[STATS] The League client listed no players for this game")
        return False
    save(stats)
    players = sum(len(team) for team in stats["teams"])
    log.info(f"[STATS] Saved rank and win rate of {players} player(s) from the League client")
    if lookup is None:
        from main import deeplol
        session = deeplol.new_session()
        deeplol.current_season(session)  # asked here once, not by each of the players' questions at the same moment
        lookup = lambda name, tag, region, champion_id: deeplol.player_extras(session, name, tag, region, champion_id)
    known = add_extras(stats, lookup)
    if known:
        save(stats)
    with_champion = sum(1 for team in stats["teams"] for player in team if player["championKnown"] and not player["me"])
    log.info(f"[STATS] deeplol added the season's record and peak for {known} player(s), "
             f"and the record on the champion played for {with_champion}")
    return True

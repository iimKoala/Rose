#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What the champ select builds panel shows and imports.

Ties main/onetricks.py (reading the site) to main/build_import.py (writing to the League client). The panel
(a Pengu plugin) sends what it sees in champ select and gets back the three players, the chosen player's
build, the enemies that make sense as lane opponent, and what was imported. Design: docs/champ-select-builds.md.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from main import onetricks
from main.build_import import import_build, page_order
from utils.core.logging import get_logger

log = get_logger()

LCU_LANES = {"top": "top", "jungle": "jungle", "middle": "mid", "bottom": "bot", "utility": "supp"}
PLAYERS_SHOWN = 3
PAGES_TRIED = 8  # players' pages read at most to find three with a build for the champion
AUTO, GENERAL = -1, 0  # "versus" values from the panel: guess the lane opponent / the usual build
UNKNOWN_SHARES = dict.fromkeys(onetricks.LANES, 0.2)  # a champion whose page can't be read may be anywhere
# The needs the panel and the item set offer, by the League client's item categories
NEEDS = (("armor", {"Armor"}), ("magicResist", {"SpellBlock"}), ("damage", {"Damage", "SpellDamage"}))
NEED_ITEMS = 4

# Kept for the Rose session, so each page is read once. Only what Rose uses is kept, not the pages (0.5 MB each).
_rankings = {}  # champion name -> (its major-region players in rank order, its lane shares)
_builds = {}  # (puuid, champion id, matchup name) -> build or None
_other_builds = {}  # (puuid, champion id) -> the player's other builds by first item, read with the usual build
_lock = threading.Lock()


def _ranking(champion: str) -> tuple:
    with _lock:
        if champion in _rankings:
            return _rankings[champion]
    page = onetricks.page_props(onetricks.ranking_path(champion))
    found = (onetricks.top_players(page, count=100000), onetricks.lane_shares(page))
    with _lock:
        _rankings[champion] = found
    return found


def _build(puuid: str, champion_id: int, matchup: str = ""):
    key = (puuid, champion_id, matchup)
    with _lock:
        if key in _builds:
            return _builds[key]
    page = onetricks.page_props(onetricks.player_path(puuid), {"matchup": matchup} if matchup else None)
    found = onetricks.player_build(page, champion_id)
    with _lock:
        _builds[key] = found
        if not matchup:
            _other_builds[(puuid, champion_id)] = onetricks.player_builds(page, champion_id)
    return found


def _others(puuid: str, champion_id: int) -> list:
    """The player's other builds, by the first item built (from the usual build's page, read once). A
    player with a single one has no choice to offer (it is the usual build again): none."""
    _build(puuid, champion_id)
    with _lock:
        builds = _other_builds.get((puuid, champion_id)) or []
    return builds if len(builds) > 1 else []


def _candidates(champion: str, lane: str) -> list:
    """A champion's players in the order Rose tries them: the best who mostly play *lane*, then the best of
    the champion's main lane, then the rest (onetricks.by_lane)"""
    everyone, shares = _ranking(champion)
    return onetricks.by_lane(everyone, shares, lane)


def _players(champion: str, lane: str, champion_id: int) -> list:
    """The three players shown: the first of _candidates whose page has a build for this champion.

    The site's page for a player is about ONE champion, their most played. A player high on two champions'
    lists has a build for one of them only and is passed over on the other (Jeykup tops Jayce's and Qiyana's
    jungle lists; his page is Qiyana's). So is a player whose page can't be read. At most PAGES_TRIED pages
    are read; a second page that can't be read is the site's trouble and is raised.
    """
    ordered = _candidates(champion, lane)[:PAGES_TRIED]

    def read(player: dict):
        try:
            return _build(player["puuid"], champion_id)
        except onetricks.OnetricksError as e:
            return e

    with ThreadPoolExecutor(max_workers=PLAYERS_SHOWN) as pool:  # the first three at once: usually they are the three
        ahead = list(pool.map(read, ordered[:PLAYERS_SHOWN]))
    players, failed = [], []
    for at, player in enumerate(ordered):
        if len(players) == PLAYERS_SHOWN:
            break
        found = ahead[at] if at < len(ahead) else read(player)
        if isinstance(found, onetricks.OnetricksError):
            failed.append(found)
            if len(failed) > 1:
                raise failed[0]
        elif found:
            players.append(player)
    if not players and failed:
        raise failed[0]
    return players


def _lane_shares(champion: str) -> dict:
    try:
        return _ranking(champion)[1]
    except onetricks.OnetricksError as e:
        log.info(f"[BUILDS] No lane data for {champion} ({e}); keeping it as a possible opponent")
        return UNKNOWN_SHARES


def _opponents(enemy_ids: list, names: dict, lane: str) -> list:
    """The enemy champions that make sense in *lane*, likeliest first"""
    known = [enemy for enemy in enemy_ids if names.get(enemy)]
    # Three pages at a time: five one after another took 2.2 s when the enemies locked in (Nov 11)
    with ThreadPoolExecutor(max_workers=3) as pool:
        shares = dict(zip(known, pool.map(lambda enemy: _lane_shares(names[enemy]), known)))
    return onetricks.likely_opponents(shares, lane)


def _situational(players: list, champion_id: int, build: dict, categories: dict) -> dict:
    """What the three players build beyond this build's own items, by what the item gives:
    {"armor": [item ids], "magicResist": [...], "damage": [...]}, the most built first"""
    def shares(player: dict) -> list:
        try:
            return (_build(player["puuid"], champion_id) or {}).get("itemShares") or []
        except onetricks.OnetricksError:
            return []

    built = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for entries in pool.map(shares, players):
            for item, share in entries:
                built[item] = built.get(item, 0) + share
    own = set(build.get("path") or []) | {build.get("boots")}
    ranked = [item for item in sorted(built, key=lambda item: -built[item]) if item not in own]
    found = {}
    for need, gives in NEEDS:
        # an item that gives armour or magic resist is listed there, not again under damage
        found[need] = [item for item in ranked if gives & set(categories.get(item) or ())
                       and (need != "damage" or not {"Armor", "SpellBlock"} & set(categories.get(item) or ()))][:NEED_ITEMS]
    return found


def panel_state(lcu, names: dict, champion_id: int, lcu_lane: str = "", enemy_ids=(), player_index: int = 0,
                versus: int = AUTO, import_parts=(), categories=None, build_index: int = 0) -> dict:
    """Everything the panel shows for one choice of player and opponent, importing the *import_parts* asked for.

    *categories* is {item id: what the item gives} for the shop's finished items; with it the build also
    carries "situational": the top players' items for armour, magic resist and damage.
    *names* is {champion id: the site's spelling} (the League client's champion "alias"). *versus* is an enemy
    champion id, AUTO (the likeliest lane opponent, when the lane is known) or GENERAL (the usual build).
    *build_index* is 0 for that build, or the number of one of the player's other builds ("builds" in the
    answer, by the first item built): the user's own pick, which stands in for the usual or matchup build.
    Raises onetricks.OnetricksError with a message for the user when the site can't give a build.
    """
    champion = names.get(champion_id, "")
    lane = LCU_LANES.get(lcu_lane or "", "")
    players = _players(champion, lane, champion_id)
    ordered = _candidates(champion, lane)
    if not players:
        raise onetricks.OnetricksError("None of the top players' pages on onetricks.gg has a build for this champion"
                                       if ordered else "onetricks.gg lists no players for this champion")
    passed_over = [other["name"] for other in ordered[:ordered.index(players[-1])] if other not in players]
    index = player_index % len(players)
    player = players[index]
    opponents = _opponents(list(enemy_ids), names, lane)
    if versus == AUTO:
        versus = opponents[0] if lane and opponents else GENERAL
    elif versus not in opponents:
        versus = GENERAL

    build, against, note = _build(player["puuid"], champion_id), "", ""
    if versus:
        matchup = _build(player["puuid"], champion_id, names[versus])
        if matchup:
            build, against = matchup, names[versus]
        else:
            note = f"No recent game against {names[versus]}: this is the usual build"
    if not build:
        raise onetricks.OnetricksError(f"{player['name']} has no recent games on this champion")
    others = _others(player["puuid"], champion_id)
    picked = build_index if 0 < build_index <= len(others) else 0
    if picked:  # the user's own pick with the Build arrows stands in for the usual or matchup build
        build = others[picked - 1]
        note = f"Your pick: this build is used instead of the one against {against}" if against else ""
        against = ""
    build = dict(build, perks=page_order(lcu, build))  # the keystone first; a copy, the kept build stays as read
    if passed_over:  # so the list is not a riddle next to the site's own
        note = (note + ". " if note else "") + (f"Not shown: {', '.join(passed_over)} "
                                                "(onetricks.gg's page for them has no build for this champion)")
    if categories:
        build = dict(build, situational=_situational(players, champion_id, build, categories))
    return {
        "players": [{key: p[key] for key in ("name", "region", "tier", "lp", "games", "winrate", "lane")} for p in players],
        "playerIndex": index, "build": build, "opponents": opponents, "versus": versus, "note": note,
        "builds": [{"firstItem": other["firstItem"], "share": other["share"]} for other in others], "buildIndex": picked,
        "imported": import_build(lcu, build, champion_id, player["name"], against, import_parts) if import_parts else None,
    }

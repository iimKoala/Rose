#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Builds of a champion's top players, read from onetricks.gg's public pages.

Two page kinds only, the ones a browser opens: a champion's ranking page and a player's page. The site's
robots.txt allows both and disallows /api/, which Rose never uses. Each page carries its data as JSON in a
<script id="__NEXT_DATA__"> tag. Design and field notes: docs/champ-select-builds.md.
"""

import json
import re
from typing import Optional

import requests

SITE = "https://www.onetricks.gg"
MAJOR_REGIONS = ("KR", "EUW1", "NA1")  # the ranking page's own default tab ("Major")
LANES = ("top", "jungle", "mid", "bot", "supp")
MIN_LANE_SHARE = 0.05  # a champion played in a lane in under 5% of its mains' games is no lane opponent there
MIN_BUILD_SHARE = 0.1  # a setup the player started under a tenth of their games with says little
SKILL_KEYS = "QWE"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Rose"}


class OnetricksError(Exception):
    """The site could not be read. The message is shown to the user."""


def ranking_path(champion_key: str) -> str:
    """Address of a champion's ranking page; *champion_key* as the site spells it ("Talon", "MissFortune")"""
    if not re.fullmatch(r"[A-Za-z]+", champion_key or ""):
        raise OnetricksError("Unknown champion name")
    return f"/champions/ranking/{champion_key}"


def player_path(puuid: str) -> str:
    """Address of a player's page"""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", puuid or ""):
        raise OnetricksError("onetricks.gg's page has changed: a player has no usable id")
    return f"/players/{puuid}"


def page_props(path: str, params: Optional[dict] = None, timeout: float = 10.0) -> dict:
    """The data a onetricks.gg page carries (its pageProps); *path* from ranking_path() or player_path()"""
    if not path.startswith(("/champions/ranking/", "/players/")):
        raise OnetricksError("Rose only reads onetricks.gg's ranking and player pages")
    try:
        response = requests.get(SITE + path, params=params, headers=_HEADERS, timeout=timeout)
    except requests.RequestException as e:
        raise OnetricksError(f"onetricks.gg can't be reached ({type(e).__name__})") from e
    if response.status_code != 200:
        raise OnetricksError(f"onetricks.gg answered {response.status_code}")
    found = _NEXT_DATA.search(response.text)
    try:
        props = json.loads(found.group(1))["props"]["pageProps"] if found else None
    except (ValueError, KeyError, TypeError):
        props = None
    if not isinstance(props, dict):
        raise OnetricksError("onetricks.gg's page has changed: its data wasn't found")
    return props


def _season_players(ranking: dict) -> list:
    """The current season's players of a ranking page, in the page's rank order"""
    for key, table in (ranking.get("rankings") or {}).items():
        if key.startswith("S") and isinstance(table, dict):  # "S2026_1"; "small_all_time" is another table
            return [player for player in table.get("mainsData") or [] if isinstance(player, dict)]
    return []


def main_lane(player: dict) -> str:
    """The lane a ranked player plays the champion in most; "" if the page doesn't say"""
    positions = player.get("mainPositions") or {}
    lanes = [lane for lane in LANES if positions.get(lane)]
    return max(lanes, key=lambda lane: positions[lane]) if lanes else ""


def top_players(ranking: dict, lane: str = "", count: int = 3) -> list:
    """The first *count* players of a ranking page as the site lists them by default (major regions);
    with *lane*, only players who mostly play that lane."""
    found = []
    for player in _season_players(ranking):
        if player.get("region") not in MAJOR_REGIONS or not player.get("puuid"):
            continue
        if lane and main_lane(player) != lane:
            continue
        found.append({
            "name": player.get("player", ""), "region": player.get("region", ""), "tier": player.get("tier", ""),
            "lp": player.get("lp", 0), "puuid": player["puuid"], "games": player.get("mainGames", 0),
            "winrate": player.get("winrate", 0), "lane": main_lane(player),
        })
        if len(found) == count:
            break
    return found


def champion_key(ranking: dict, champion_id: int) -> str:
    """The site's spelling of a champion's name (any ranking page lists them all); "" if unknown"""
    return str((ranking.get("championKeys") or {}).get(str(champion_id)) or "")


def lane_shares(ranking: dict) -> dict:
    """How a champion's games split over the lanes, from its ranking page: {lane: share from 0 to 1}"""
    totals = dict.fromkeys(LANES, 0)
    for player in _season_players(ranking):
        for lane in LANES:
            totals[lane] += (player.get("mainPositions") or {}).get(lane) or 0
    games = sum(totals.values())
    return {lane: (totals[lane] / games if games else 0.0) for lane in LANES}


def likely_opponents(shares_by_champion: dict, lane: str) -> list:
    """The enemy champions that make sense in *lane*, most likely first.

    *shares_by_champion* is {champion id: lane_shares(its ranking page)}. A champion hardly ever played in
    that lane is left out (Braum top). With no lane known, or nobody fitting, all are kept in the order given.
    """
    if lane not in LANES:
        return list(shares_by_champion)
    fitting = [champion for champion, shares in shares_by_champion.items() if shares.get(lane, 0) >= MIN_LANE_SHARE]
    fitting.sort(key=lambda champion: -shares_by_champion[champion][lane])
    return fitting or list(shares_by_champion)


def _most_used(entries):
    """The value of the most used entry of a [[value, share], ...] list, or None for an empty list"""
    return max(entries, key=lambda entry: entry[1])[0] if entries else None


def _early_skills(paths) -> str:
    """The keys of the most used first three skill points, as "W Q E" ("" when the page gives none)"""
    levels = _most_used(paths) or []
    slots = [str(level[0].get("skillSlot")) for level in levels if level and isinstance(level[0], dict)]
    return " ".join("QWER"[int(slot) - 1] for slot in slots if slot in ("1", "2", "3", "4"))


def player_build(player_page: dict, champion_id: int, first_item: str = "all") -> Optional[dict]:
    """A player's most used setup on a champion, from their page (also one filtered with ?matchup=<name>).
    With *first_item* (an item id): their setup in the games they started with that item.

    None when the page has no game on that champion (or none in that matchup). Rune ids come as the site
    gives them: "perks" are the six runes without an order, "shards" the three stat shards top to bottom.
    """
    games = (player_page.get("games") or {}).get(str(champion_id)) or {}
    stats = ((games.get("firstItemStats") or {}).get("all") or {}).get(str(first_item)) or {}
    try:
        keystone = _most_used(stats.get("popKeystone"))
        rune_sets = (stats.get("popRunes") or {}).get(str(keystone)) or []
        if not games.get("matchHistory") or not rune_sets:
            return None
        perks, _share, (primary, secondary, _keystone) = max(rune_sets, key=lambda rune_set: rune_set[1])
        paths = [path for group in stats.get("popClassicPath") or [] for path in group]
        path = [int(item) for item in _most_used(paths) or _most_used(stats.get("popCore")) or []]
        other = [int(item) for item, share in stats.get("popularItems") or [] if share >= 0.1 and int(item) not in path]
        order = (stats.get("maxSkillOrders") or [{}])[0].get("order") or []
        boots = int(_most_used(stats.get("boots")) or 0)
        timing = [int(item) for item in (stats.get("bootsTimingSequences") or {}).get(str(boots)) or []]
        return {
            "games": len(games["matchHistory"]),
            "keystone": int(keystone), "primaryStyle": int(primary), "subStyle": int(secondary),
            "perks": [int(perk) for perk in perks], "shards": [int(shard) for shard in stats.get("popStat") or []],
            "spells": [int(spell) for spell in _most_used(stats.get("sSpells")) or []],
            "startItems": [int(item) for item in _most_used(stats.get("startingItems")) or []],
            "path": path, "boots": boots, "bootsAfter": timing.index(boots) if boots in timing else len(path),
            "otherItems": other,
            "itemShares": [[int(item), float(share)] for item, share in stats.get("popularItems") or []],
            "skillOrder": " > ".join(SKILL_KEYS[slot] for slot in order if slot in (0, 1, 2)),
            "earlySkills": _early_skills(stats.get("earlySkillPaths")),
        }
    except (IndexError, KeyError, TypeError, ValueError) as e:
        raise OnetricksError("onetricks.gg's page has changed: a build couldn't be read") from e


def player_builds(player_page: dict, champion_id: int) -> list:
    """A player's other setups on a champion, as the site splits them: by the first item built, the most
    played first. Each is a build as player_build gives it, with "firstItem" and "share" (the part of the
    player's games that started with that item). A setup of under MIN_BUILD_SHARE of the games is left out,
    and so is one that can't be read: the usual build still shows. Never raises."""
    try:
        by_item = player_page["games"][str(champion_id)]["firstItemStats"]["all"]
        # the other keys are "all", "top" (which first item is built most) and pairs of items
        splits = [(item, stats) for item, stats in by_item.items() if str(item).isdigit() and isinstance(stats, dict)]
    except (AttributeError, KeyError, TypeError):
        return []
    builds = []
    for item, stats in splits:
        try:
            share = sum(float(part) for _keystone, part in stats.get("popKeystone") or [])
            build = player_build(player_page, champion_id, item) if share >= MIN_BUILD_SHARE else None
        except (OnetricksError, TypeError, ValueError):
            continue
        if build:
            builds.append(dict(build, firstItem=int(item), share=share))
    return sorted(builds, key=lambda build: -build["share"])

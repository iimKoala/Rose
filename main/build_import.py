#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Put a build (main/onetricks.py's player_build) into the League client: rune page, summoner spells, item set.

Only the League client's own local API is used, as its own screens use it. Rose owns one rune page and one
item set, both named "Rose: ...", and overwrites them; the user's other pages and sets are left alone.
Endpoints and fields: docs/champ-select-builds.md.
"""

import uuid
from typing import Optional

from utils.core.logging import get_logger

log = get_logger()

OWN_PREFIX = "Rose: "  # Rose's own rune page and item set start with this
NAME_LIMIT = 32
FLASH = 4
STAT_SLOT = "kStatMod"
PARTS = ("runes", "spells", "items")  # what can be imported; the panel has a button for each


class BuildImportError(Exception):
    """A part of the build could not be imported. The message is shown to the user."""


def _read(lcu, path: str):
    """Fresh data from the League client (never Rose's short cache), or None"""
    return lcu.get(path, use_cache=False)


def _send(lcu, method: str, path: str, body) -> bool:
    """One change in the League client; True if it was accepted"""
    try:
        response = lcu.s.request(method, (lcu.base or "") + path, json=body, timeout=5.0)
    except Exception as e:
        log.warning(f"[BUILDS] {method} {path} failed ({type(e).__name__})")
        return False
    api = getattr(lcu, "_api", None)
    if api is not None:
        api.invalidate(path)  # Rose's cached copy of what was just changed
    log.info(f"[BUILDS] {method} {path} -> {response.status_code}")
    return 200 <= response.status_code < 300


def own_name(player: str, versus: str = "") -> str:
    """Name of Rose's rune page or item set: "Rose: Poo of Death vs Yasuo" (the player's tag is left out)"""
    name = OWN_PREFIX + player.split("#")[0].strip() + (f" vs {versus}" if versus else "")
    return name[:NAME_LIMIT].rstrip()


def ordered_perks(build: dict, styles: list) -> list:
    """The nine rune ids in the order the League client wants: the main tree's four top to bottom, the
    second tree's two, the three stat shards. The site gives the six runes without an order."""
    trees = {style.get("id"): style.get("slots") or [] for style in styles or []}
    chosen = set(build.get("perks") or [])
    ordered = []
    for style, wanted in ((build.get("primaryStyle"), 4), (build.get("subStyle"), 2)):
        rows = [slot for slot in trees.get(style) or [] if slot.get("type") != STAT_SLOT]
        picked = [perk for slot in rows for perk in slot.get("perks") or [] if perk in chosen]
        if len(picked) != wanted:
            raise BuildImportError("These runes don't fit the game's current rune trees")
        ordered += picked
    shard_rows = [slot.get("perks") or [] for slot in trees.get(build.get("primaryStyle")) or [] if slot.get("type") == STAT_SLOT]
    shards = build.get("shards") or []
    for row, perks in enumerate(shard_rows[:3]):
        # a shard the site doesn't give, or one this row no longer has: the row's first shard
        ordered.append(shards[row] if row < len(shards) and shards[row] in perks else perks[0])
    if len(ordered) != 9:
        raise BuildImportError("These runes don't fit the game's current rune trees")
    return ordered


def page_order(lcu, build: dict) -> list:
    """The six runes as a rune page shows them: the keystone, the main tree's three, the second tree's two.
    The site lists them by number, which puts the keystone anywhere. As the site lists them when the
    client's rune trees can't be read or the runes don't fit them."""
    try:
        return ordered_perks(build, _read(lcu, "/lol-perks/v1/styles"))[:6]
    except BuildImportError:
        return list(build.get("perks") or [])


def import_runes(lcu, build: dict, name: str) -> str:
    """Write the build's runes to Rose's rune page and select it. Returns what was done."""
    page = {"name": name, "primaryStyleId": build.get("primaryStyle"), "subStyleId": build.get("subStyle"),
            "selectedPerkIds": ordered_perks(build, _read(lcu, "/lol-perks/v1/styles")), "current": True}
    pages = _read(lcu, "/lol-perks/v1/pages")
    if not isinstance(pages, list):
        raise BuildImportError("The League client didn't list your rune pages")
    target = next((p for p in pages if str(p.get("name", "")).startswith(OWN_PREFIX)), None)
    done = "Runes imported"
    if target is None:
        own = [p for p in pages if p.get("isDeletable")]
        owned = (_read(lcu, "/lol-perks/v1/inventory") or {}).get("ownedPageCount") or 0
        if own and len(own) >= owned:
            # No free page. The user allowed overwriting the selected one (Nov 11).
            target = next((p for p in own if p.get("current")), own[0])
            done = f"Runes imported over your page \"{target.get('name', '')}\" (no free rune page)"
    if target is None:
        if not _send(lcu, "POST", "/lol-perks/v1/pages", page):
            raise BuildImportError("The League client refused the rune page")
        return done
    if not _send(lcu, "PUT", f"/lol-perks/v1/pages/{target['id']}", page):
        raise BuildImportError("The League client refused the rune page")
    _send(lcu, "PUT", "/lol-perks/v1/currentpage", target["id"])
    return done


def import_spells(lcu, build: dict) -> str:
    """Set the two summoner spells; Flash stays on the key it is on now. Returns what was done."""
    spells = build.get("spells") or []
    if len(spells) != 2:
        raise BuildImportError("This build has no summoner spells")
    first, second = spells
    now = _read(lcu, "/lol-champ-select/v1/session/my-selection") or {}
    if FLASH in spells:
        other = second if first == FLASH else first
        if now.get("spell2Id") == FLASH:
            first, second = other, FLASH
        elif now.get("spell1Id") == FLASH:
            first, second = FLASH, other
    if not _send(lcu, "PATCH", "/lol-champ-select/v1/session/my-selection", {"spell1Id": first, "spell2Id": second}):
        raise BuildImportError("The League client refused the summoner spells")
    return "Summoner spells set"


def _block(title: str, items: list) -> Optional[dict]:
    """One block of an item set (a repeated item becomes one entry with a count), or None with no items"""
    counts = {}
    for item in items:
        if item:
            counts[str(item)] = counts.get(str(item), 0) + 1
    return {"type": title, "items": [{"id": item, "count": count} for item, count in counts.items()]} if counts else None


def import_items(lcu, build: dict, champion_id: int, title: str) -> str:
    """Add the build as Rose's item set for the in-game shop, replacing Rose's earlier one. Returns what was done."""
    summoner_id = (_read(lcu, "/lol-summoner/v1/current-summoner") or {}).get("summonerId")
    path = f"/lol-item-sets/v1/item-sets/{summoner_id}/sets"
    current = _read(lcu, path) if summoner_id else None
    if not isinstance(current, dict) or not isinstance(current.get("itemSets"), list):
        # The whole list is sent back: without the user's own sets in hand, sending would delete them
        raise BuildImportError("The League client didn't give your item sets, so nothing was changed")
    needs = build.get("situational") or {}  # what the top players build when they need it
    # the skill order rides on the first two titles, where the shop shows it (the user, Nov 14: "comments
    # about skill order in shop. eg. level 1 - 3 qwe. max skill order wqe")
    early, order = build.get("earlySkills"), build.get("skillOrder")
    blocks = [_block("Start" + (f" (levels 1-3: {early})" if early else ""), build.get("startItems") or []),
              _block("Build in this order" + (f" (max {order})" if order else ""), build.get("path") or []),
              _block("Boots", [build.get("boots")]), _block("Also built in these games", build.get("otherItems") or []),
              _block("If you need armour", needs.get("armor") or []),
              _block("If you need magic resist", needs.get("magicResist") or []),
              _block("More damage", needs.get("damage") or [])]
    item_set = {"title": title, "uid": str(uuid.uuid4()), "type": "custom", "map": "any", "mode": "any",
                "associatedChampions": [champion_id], "associatedMaps": [11, 12], "sortrank": 0, "startedFrom": "blank",
                "preferredItemSlots": [], "blocks": [block for block in blocks if block]}
    kept = [s for s in current["itemSets"] if not str(s.get("title", "")).startswith(OWN_PREFIX)]
    if not _send(lcu, "PUT", path, {**current, "itemSets": kept + [item_set]}):
        raise BuildImportError("The League client refused the item set")
    return "Item set added to the shop"


def import_build(lcu, build: dict, champion_id: int, player: str, versus: str = "", parts=PARTS) -> dict:
    """Import the *parts* asked for (the panel has a button for each). One part failing never stops the others.

    Returns {part: {"ok": bool, "text": what happened}} for each part asked for.
    """
    name = own_name(player, versus)
    result = {}
    for part, run in (("runes", lambda: import_runes(lcu, build, name)), ("spells", lambda: import_spells(lcu, build)),
                      ("items", lambda: import_items(lcu, build, champion_id, name))):
        if part not in parts:
            continue
        try:
            result[part] = {"ok": True, "text": run()}
        except BuildImportError as e:
            result[part] = {"ok": False, "text": str(e)}
        except Exception as e:  # a part must never take Rose's champ select down
            log.warning(f"[BUILDS] Importing the {part} failed: {type(e).__name__}: {e}")
            result[part] = {"ok": False, "text": f"Couldn't import the {part}"}
    return result

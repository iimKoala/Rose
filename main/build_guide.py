#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-game build guide: which item of the build comes next, and what the player's gold buys of it now.

No game and no window here: main/build_overlay.py feeds this the game's numbers and draws the answer.
Design: docs/in-game-build-guide.md.
"""

from collections import Counter
from typing import Optional

COMPONENTS_SHOWN = 3
RECIPE_DEPTH = 6  # no item is built deeper than this; stops a recipe that loops


def build_order(build: dict) -> list:
    """A build's items in buying order: its path, with the boots where the player usually buys them (last if unknown)"""
    order = [item for item in build.get("path") or [] if item]
    boots = build.get("boots") or 0
    if boots and boots not in order:
        after = build.get("bootsAfter")
        order.insert(min(after, len(order)) if isinstance(after, int) and after >= 0 else len(order), boots)
    return order


def _parts(item: int, recipes: dict) -> list:
    return list((recipes.get(item) or {}).get("from") or [])


def _total(item: int, recipes: dict) -> int:
    return int((recipes.get(item) or {}).get("priceTotal") or 0)


def _is_or_holds(item: int, wanted: int, recipes: dict, depth: int = 0) -> bool:
    """Whether *item* is *wanted* or was made from it: an item that was upgraded or transformed still counts"""
    if item == wanted or (recipes.get(item) or {}).get("specialRecipe") == wanted:
        return True
    return depth < RECIPE_DEPTH and any(_is_or_holds(part, wanted, recipes, depth + 1) for part in _parts(item, recipes))


def _paid_toward(item: int, have: Counter, recipes: dict, depth: int = 0) -> int:
    """Gold the player has already spent toward *item*: the item itself or parts of it, taken out of *have*"""
    if have[item] > 0:
        have[item] -= 1
        return _total(item, recipes)
    if depth >= RECIPE_DEPTH:
        return 0
    return sum(_paid_toward(part, have, recipes, depth + 1) for part in _parts(item, recipes))


def next_step(order: list, owned: list, gold: float, recipes: dict) -> Optional[dict]:
    """What the strip shows: the first item of *order* the player doesn't have yet, its direct components,
    and what *gold* buys now. None when the player has every item of the order.

    *owned* is the item ids in the player's inventory, repeats as they are. *recipes* is the client's game
    data by item id: {"from": [component ids], "priceTotal": gold, "specialRecipe": the item it came from}.
    """
    inventory = list(owned)
    target = None
    for item in order:
        held = next((have for have in inventory if _is_or_holds(have, item, recipes)), None)
        if held is None:
            target = item
            break
        inventory.remove(held)  # one item in the bag answers one step of the order
    if target is None:
        return None
    have = Counter(inventory)
    parts = _parts(target, recipes)
    owned_now = []
    for part in parts:  # a part in the bag is first of all that component itself, before it counts inside another
        owned_now.append(have[part] > 0)
        if owned_now[-1]:
            have[part] -= 1
    components, paid = [], 0
    for index, part in enumerate(parts):
        part_paid = _total(part, recipes) if owned_now[index] else _paid_toward(part, have, recipes)
        paid += part_paid
        cost = max(0, _total(part, recipes) - part_paid)
        if index < COMPONENTS_SHOWN:
            components.append({"id": part, "owned": owned_now[index], "cost": cost,
                               "affordable": not owned_now[index] and part in recipes and gold >= cost})
    cost = max(0, _total(target, recipes) - paid)
    return {"target": target, "cost": cost, "affordable": target in recipes and gold >= cost, "components": components}

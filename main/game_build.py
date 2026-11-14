#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The build the in-game guide follows in the coming game.

Saved while the League client is open (the builds panel shows a build), read by main/build_overlay.py during
the game: the items in buying order, every item's recipe and the icons the strip draws.
Design: docs/in-game-build-guide.md.
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from main.build_guide import build_order
from utils.core.logging import get_logger
from utils.core.paths import get_state_dir

log = get_logger()

ITEMS_PATH = "/lol-game-data/assets/v1/items.json"  # the client's own item data: recipes, prices, icons
ICON_PREFIX = "/lol-game-data/assets/"  # icons are only ever fetched from the client's game data
FRESH_S = 30 * 60  # a build saved longer ago than this belongs to an earlier game
# Runs main/build_overlay.py with an empty stand-in for the main package, as the Account window is started:
# main/__init__.py, which loads all of Rose, is not run for a strip of four icons
OVERLAY_START = (
    "import sys, types; package = types.ModuleType('main'); package.__path__ = ['main']; "
    "sys.modules['main'] = package; import runpy; runpy.run_module('main.build_overlay', run_name='__main__')"
)


def guide_dir() -> Path:
    return get_state_dir() / "build_guide"


def _recipes(items: list) -> dict:
    """{item id: what the guide needs of its recipe} from the client's item data"""
    return {
        int(item["id"]): {"from": [int(part) for part in item.get("from") or []],
                          "priceTotal": int(item.get("priceTotal") or 0), "specialRecipe": int(item.get("specialRecipe") or 0)}
        for item in items if isinstance(item, dict) and item.get("id")
    }


def save_game_build(lcu, build: dict, champion_id: int, player: str) -> bool:
    """Save the build for the coming game; False (and nothing saved) when the client gives no item data"""
    items = lcu.get(ITEMS_PATH)
    if not isinstance(items, list) or not items:
        return False
    recipes = _recipes(items)
    order = build_order(build)
    order += [item for item in build.get("otherItems") or [] if item not in order]  # then the player's other usual items
    icons = guide_dir() / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    wanted = set(order) | {part for item in order for part in (recipes.get(item) or {}).get("from") or []}
    for item in items:
        icon_path = str(item.get("iconPath") or "") if isinstance(item, dict) else ""
        if item.get("id") not in wanted or not icon_path.startswith(ICON_PREFIX):
            continue
        target = icons / f"{int(item['id'])}.png"
        if target.exists():
            continue
        try:
            response = lcu.s.get((lcu.base or "") + icon_path, timeout=5.0)
            if response.status_code == 200:
                target.write_bytes(response.content)
        except Exception as e:  # a missing icon is drawn as a plain square: never worth failing the save
            log.info(f"[GUIDE] No icon for item {item['id']} ({type(e).__name__})")
    saved = {"championId": champion_id, "player": player, "order": order, "savedAt": time.time(),
             "recipes": {str(item): recipe for item, recipe in recipes.items()}}
    (guide_dir() / "game_build.json").write_text(json.dumps(saved), encoding="utf-8")
    log.info(f"[GUIDE] Saved the build for the game: {len(order)} items from {player}")
    return True


def load_game_build() -> Optional[dict]:
    """The saved build with numbers as numbers again, or None when there is none to follow"""
    try:
        saved = json.loads((guide_dir() / "game_build.json").read_text(encoding="utf-8"))
        order = [int(item) for item in saved["order"]]
        recipes = {int(item): recipe for item, recipe in saved["recipes"].items()}
        if time.time() - float(saved.get("savedAt") or 0) > FRESH_S:
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return {"championId": saved.get("championId"), "player": saved.get("player", ""), "order": order, "recipes": recipes} if order else None


def save_item_prices(lcu) -> bool:
    """Save what every item costs in the shop, for the gold board; False when the client gives no item data"""
    items = lcu.get(ITEMS_PATH) if lcu is not None else None
    if not isinstance(items, list) or not items:
        return False
    guide_dir().mkdir(parents=True, exist_ok=True)
    prices = {str(item): recipe["priceTotal"] for item, recipe in _recipes(items).items()}
    (guide_dir() / "item_prices.json").write_text(json.dumps(prices), encoding="utf-8")
    return True


def load_item_prices() -> dict:
    """{item id: its price in the shop}, as last saved; {} when Rose never saved them"""
    try:
        saved = json.loads((guide_dir() / "item_prices.json").read_text(encoding="utf-8"))
        return {int(item): int(price) for item, price in saved.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def end_running_overlays() -> int:
    """End every strip program that still runs, whichever game or Rose started it; returns how many.

    One that outlives its game draws a second strip and gold board, with what it last knew (Nov 13: the
    board of a Practice Tool game drew its empty rows over the next game)."""
    import psutil  # here, not at the top: the strip's program imports this file and has no use for psutil

    ended = 0
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").lower().startswith("python") and "main.build_overlay" in " ".join(process.cmdline()):
                process.terminate()
                ended += 1
        except (psutil.Error, OSError):
            pass  # gone already, or not a program Rose may look at
    return ended


def _save_player_stats(lcu) -> None:
    """The players' rank and win rate for the Ctrl+X panel (main/player_stats.py). In a thread of its own:
    asking deeplol about nine players takes a second or more, and the game's start must not wait for it."""
    try:
        from main import player_stats

        player_stats.collect(lcu, log)
    except Exception as e:
        log.info(f"[STATS] Could not save the players' stats ({type(e).__name__}: {e})")


def start_overlay(lcu=None) -> bool:
    """Start the strip's program (the build guide and the gold board) for the game that is starting, in place
    of any that still runs; it ends by itself when the game has gone. False when there is neither a fresh
    build to follow nor item prices for the gold board."""
    try:
        ended = end_running_overlays()
        if ended:
            log.info(f"[GUIDE] Ended {ended} in-game program(s) that were still running")
    except Exception as e:  # never a reason not to start this game's
        log.info(f"[GUIDE] Could not look for in-game programs still running ({type(e).__name__})")
    try:
        save_item_prices(lcu)  # prices change with a patch: read from the client again for every game
    except Exception as e:  # the gold board then uses the prices saved for the last game
        log.info(f"[GUIDE] Could not save the item prices ({type(e).__name__})")
    if load_game_build() is None and not load_item_prices():
        return False
    subprocess.Popen(
        [sys.executable, "-c", OVERLAY_START],
        cwd=str(Path(__file__).resolve().parent.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log.info("[GUIDE] Started the in-game build guide and gold board")
    if lcu is not None:
        threading.Thread(target=_save_player_stats, args=(lcu,), daemon=True, name="PlayerStats").start()
    return True

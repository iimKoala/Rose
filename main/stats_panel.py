#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The player stats panel: both teams in role order, a card a player, over the game.

Each card looks like an account card of the account switcher (main/account_web): the rank's emblem, the tier
in gold, the LP with its bar, and to the right the season's win rate and the win rate on the champion being
played. Ctrl+X shows it: a tap keeps it open until the next tap, holding the keys shows it only while they
are held. Part of the in-game strip's program (main/build_overlay.py); the numbers are saved by Rose when the
game starts (main/player_stats.py). Like the strip it never touches the game: always on top, lets the mouse
through, never takes the keyboard. Design: docs/player-stats-panel.md.
"""

import ctypes
import os
import time
import tkinter as tk
from pathlib import Path
from typing import Optional

from main.game_build import guide_dir
from main.gold_board import GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, GoldBoard
from main.player_stats import STATS_FILE, load

VK_CONTROL, VK_X = 0x11, 0x58
HOLD_S = 0.35  # the keys held at least this long: the panel was only being peeked at, and hides on release
SIDE, ROW, HEAD, PAD, GAP = 490, 78, 30, 12, 6  # a card's width and height, the heading's height, the edge, between cards
RECORDS = 192  # the width of a card's right side: the season's record and the champion's
WIDTH = 2 * SIDE + 3 * PAD
EMBLEM = 52  # the rank emblem's side on a card
# The account switcher's colours (main/account_web/style.css)
DARK, PANEL, CARD, EDGE = "#010a13", "#0a1428", "#0b1621", "#1e2d3d"
GOLD, GOLD_DARK, TEXT, GREY, GREEN, RED = "#c8aa6e", "#785a28", "#f0e6d2", "#a09b8c", "#0ac8b9", "#e84057"
TRACK = "#2d312f"  # the LP bar's empty part: the card's colour under 18% gold, as on the account cards
ROLES = {"TOP": "TOP", "JUNGLE": "JNG", "MIDDLE": "MID", "BOTTOM": "BOT", "UTILITY": "SUP"}
APEX = ("MASTER", "GRANDMASTER", "CHALLENGER")  # no divisions, and a full LP bar, as on the account cards
SMALL_SAMPLE = 5  # a win rate over fewer games than this keeps the plain colour: it says little
ASSETS = Path(__file__).resolve().parent / "account_web"  # the account switcher's emblems and font
FR_PRIVATE = 0x10
LWA_ALPHA = 0x2


class Hotkey:
    """Whether the panel is open, from the keys being down or up at each tick: a tap opens it and the next
    tap closes it; keys held for HOLD_S or longer only peek, so it closes when they are let go."""

    def __init__(self):
        self.open, self.was_down, self.pressed_at, self.opened_by_this_press = False, False, 0.0, False

    def update(self, down: bool, now: float) -> bool:
        if down and not self.was_down:
            self.opened_by_this_press = not self.open
            self.open = not self.open
            self.pressed_at = now
        elif not down and self.was_down:
            if self.opened_by_this_press and now - self.pressed_at >= HOLD_S:
                self.open = False
            self.opened_by_this_press = False
        self.was_down = down
        return self.open


def title_font() -> str:
    """The account switcher's title font, loaded for this program only (nothing is installed); Segoe UI
    when it can't be loaded"""
    path = ASSETS / "fonts" / "BeaufortforLOL-Bold.ttf"
    try:
        if path.exists() and ctypes.windll.gdi32.AddFontResourceExW(str(path), FR_PRIVATE, 0):
            return "Beaufort for LOL"
    except (AttributeError, OSError):
        pass
    return "Segoe UI"


def tier_text(player: dict) -> str:
    """ "DIAMOND III", "MASTER", or "UNRANKED": the tier as an account card writes it"""
    tier = (player.get("tier") or "").upper()
    if not tier:
        return "UNRANKED"
    return tier if tier in APEX or not player.get("division") else f"{tier} {player['division']}"


def lp_share(player: dict) -> float:
    """How full the LP bar is, 0 to 1: the LP out of 100, and full from Master up (as the account cards)"""
    if (player.get("tier") or "").upper() in APEX:
        return 1.0
    return min(max(int(player.get("lp") or 0), 0), 100) / 100


def win_rate(player: dict) -> Optional[float]:
    """The season's win rate in solo queue; None before the first game, and while the losses are not known
    (the League client tells them for the user's own account only; deeplol for the others)"""
    games = int(player.get("wins") or 0) + int(player.get("losses") or 0)
    return 100 * player["wins"] / games if games and player.get("lossesKnown") else None


def record_parts(wins, losses, known: bool = True, recent: bool = False) -> tuple:
    """(win rate or None, the big text, the small text, the games) of a record: (58.3, "58%", "120 games",
    120). While the losses are not known only the wins: (None, "35", "wins", 0). No game: (None, "-", "", 0).
    *recent*: the games are among the last the client lists, not a season's: "3 recent"."""
    wins, losses = int(wins or 0), int(losses or 0)
    if not known:
        return (None, str(wins), "wins", 0) if wins else (None, "-", "", 0)
    games = wins + losses
    if not games:
        return None, "-", "", 0
    rate = 100 * wins / games
    return rate, f"{round(rate)}%", f"{games} recent" if recent else f"{games} game" + ("" if games == 1 else "s"), games


def season_parts(player: dict) -> tuple:
    """The season's solo queue record, as record_parts gives it"""
    return record_parts(player.get("wins"), player.get("losses"), bool(player.get("lossesKnown")))


def champion_parts(player: dict) -> tuple:
    """The record on the champion being played: the season's in solo queue (deeplol), or for the user's own
    account the last ranked games the client lists. (None, "-", "", 0) while it is not known; a player with
    no game on the champion says so, which is worth knowing"""
    if not player.get("championKnown"):
        return None, "-", "", 0
    parts = record_parts(player.get("championWins"), player.get("championLosses"), True, bool(player.get("championRecent")))
    return parts if parts[3] else (None, "-", "none recent" if player.get("championRecent") else "no games", 0)


def rate_colour(rate: Optional[float], games: int) -> str:
    """Teal for a winning record, red for a losing one, plain otherwise and for a handful of games"""
    if rate is None or games < SMALL_SAMPLE:
        return TEXT
    return GREEN if rate >= 55 else RED if rate <= 45 else TEXT


def peak_text(player: dict) -> str:
    """The season's highest rank when it is known and not the rank the player has now: "Peak Emerald 77 LP" """
    tier = player.get("peakTier") or ""
    if not tier:
        return ""
    tier = " ".join([tier.split()[0].title()] + tier.split()[1:])  # "DIAMOND IV" -> "Diamond IV": the division stays capitals
    peak = " ".join(part for part in (tier, player.get("peakDivision") or "", f"{player['peakLp']} LP" if player.get("peakLp") else "") if part)
    now = " ".join(part for part in ((player.get("tier") or "").title(), player.get("division") or "") if part)
    return "" if peak == now else f"Peak {peak}"


def ladder_text(player: dict) -> str:
    """ "Top 12%" of the ladder (deeplol), or "" when it isn't known"""
    percent = player.get("ladderPercent")
    return f"Top {percent:.2g}%" if isinstance(percent, (int, float)) and percent > 0 else ""


class StatsPanel:
    def __init__(self, root: tk.Tk):
        self.hotkey, self.visible, self.stats, self.stamp, self.checked_at = Hotkey(), False, None, None, 0.0
        self.family, self.emblems = title_font(), {}
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.height = HEAD + 5 * ROW + 4 * GAP + 2 * PAD
        self.canvas = tk.Canvas(self.top, width=WIDTH, height=self.height, bg=DARK, highlightthickness=1, highlightbackground=EDGE)
        self.canvas.pack()
        # above the scoreboard's place, in the middle
        self.top.geometry(f"{WIDTH + 2}x{self.height + 2}+{(root.winfo_screenwidth() - WIDTH) // 2}+{round(root.winfo_screenheight() * 0.03)}")
        self.top.withdraw()
        self.top.update_idletasks()
        user32 = ctypes.windll.user32
        window = user32.GetParent(self.top.winfo_id())
        user32.SetWindowLongW(window, GWL_EXSTYLE, user32.GetWindowLongW(window, GWL_EXSTYLE)
                              | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        # Windows draws a layered window only once it has been told how solid it is (Nov 14: without this
        # line the panel never appeared). 255: fully solid, a see-through panel is hard to read over a game
        user32.SetLayeredWindowAttributes(window, 0, 255, LWA_ALPHA)

    def _keys_down(self) -> bool:
        user32 = ctypes.windll.user32
        return bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000 and user32.GetAsyncKeyState(VK_X) & 0x8000)

    def _reload(self) -> bool:
        """Read the stats again when Rose saved new ones (deeplol's extras arrive after the client's); whether they changed"""
        now = time.monotonic()
        if now - self.checked_at < 1.0:
            return False
        self.checked_at = now
        try:
            saved = os.stat(guide_dir() / STATS_FILE)
            stamp = (saved.st_mtime_ns, saved.st_size)
        except OSError:
            stamp = None
        if stamp == self.stamp:
            return False
        self.stamp, self.stats = stamp, load() if stamp else None
        return True

    def _emblem(self, tier: str):
        """The tier's emblem at the card's size, read once; None for no tier or when it can't be read"""
        if tier not in self.emblems:
            try:
                from PIL import Image, ImageTk
                picture = Image.open(ASSETS / "emblems" / f"{tier.lower()}.png").convert("RGBA")
                self.emblems[tier] = ImageTk.PhotoImage(picture.resize((EMBLEM, EMBLEM), Image.LANCZOS), master=self.top)
            except Exception:  # noqa: BLE001 - a card without its emblem still says the tier in words
                self.emblems[tier] = None
        return self.emblems[tier]

    def _badge(self, x: int, y: int, text: str) -> int:
        """A small label like the account cards' region and level; returns where it ends"""
        item = self.canvas.create_text(x + 5, y, text=text, anchor="w", fill=GREY, font=("Segoe UI", 7))
        box = self.canvas.bbox(item)
        self.canvas.tag_lower(self.canvas.create_rectangle(x, box[1] - 1, box[2] + 5, box[3] + 1, fill=PANEL, outline=""), item)
        return box[2] + 5

    def _record(self, left: int, y: int, label: str, parts: tuple) -> None:
        """One line of the card's right side: a small label, then the win rate and the games, right-aligned"""
        rate, big, small, games = parts
        right = left + SIDE - 12
        self.canvas.create_text(left + SIDE - RECORDS, y, text=label, anchor="w", fill=GREY, font=("Segoe UI", 7, "bold"))
        if small:
            right = self.canvas.bbox(self.canvas.create_text(right, y + 1, text=small, anchor="e", fill=GREY, font=("Segoe UI", 8)))[0] - 6
        self.canvas.create_text(right, y, text=big, anchor="e", fill=rate_colour(rate, games), font=(self.family, 12, "bold"))

    def _card(self, left: int, top: int, player: dict) -> None:
        canvas, middle = self.canvas, top + ROW // 2
        canvas.create_rectangle(left, top, left + SIDE, top + ROW, fill=CARD, outline=GOLD_DARK if player.get("me") else EDGE)
        if player.get("hidden"):  # streamer mode: the slot stays, with the champion and the role only
            canvas.create_oval(left + 18, middle - 18, left + 54, middle + 18, outline=EDGE, width=2)
            end = canvas.bbox(canvas.create_text(left + 20 + EMBLEM, top + 16, text=player.get("champion") or "?", anchor="w", fill=TEXT, font=(self.family, 12, "bold")))[2] + 8
            if ROLES.get(player.get("position") or ""):
                self._badge(end, top + 16, ROLES[player["position"]])
            canvas.create_text(left + 20 + EMBLEM, top + 46, text="STREAMER MODE", anchor="w", fill=GREY, font=(self.family, 13, "bold"))
            canvas.create_text(left + 20 + EMBLEM, top + 64, text="Name and stats are hidden by this player", anchor="w", fill=GREY, font=("Segoe UI", 8))
            return
        tier = (player.get("tier") or "").upper()
        emblem = self._emblem(tier) if tier else None
        if emblem:
            canvas.create_image(left + 10 + EMBLEM // 2, middle, image=emblem)
        else:
            canvas.create_oval(left + 18, middle - 18, left + 54, middle + 18, outline=EDGE, width=2)
        x = left + 20 + EMBLEM
        champion = player.get("champion") or "?"
        end = canvas.bbox(canvas.create_text(x, top + 16, text=champion, anchor="w", fill=TEXT, font=(self.family, 12, "bold")))[2] + 8
        for badge in (ROLES.get(player.get("position") or "", ""), f"Lv {player['level']}" if player.get("level") else ""):
            if badge:
                end = self._badge(end, top + 16, badge) + 4
        name = (player.get("name") or "")[:20] + (f" #{player['tag']}" if player.get("tag") else "")
        canvas.create_text(left + SIDE - 12, top + 16, text=name, anchor="e", fill=GOLD if player.get("me") else GREY, font=("Segoe UI", 9))
        end = canvas.bbox(canvas.create_text(x, top + 39, text=tier_text(player), anchor="w", fill=GOLD if tier else GREY, font=(self.family, 13, "bold")))[2]
        if tier:
            canvas.create_text(end + 10, top + 40, text=f"{int(player.get('lp') or 0)} LP", anchor="w", fill=TEXT, font=("Segoe UI", 9))
            canvas.create_rectangle(x, top + 52, x + 150, top + 55, fill=TRACK, outline="")
            if lp_share(player) > 0:
                canvas.create_rectangle(x, top + 52, x + round(150 * lp_share(player)), top + 55, fill=GOLD, outline="")
        below = " · ".join(text for text in (peak_text(player), ladder_text(player)) if text)
        if below:
            canvas.create_text(x, top + 66, text=below, anchor="w", fill=GREY, font=("Segoe UI", 8))
        self._record(left, top + 40, "SEASON", season_parts(player))
        self._record(left, top + 60, champion.upper()[:12], champion_parts(player))

    def _draw(self) -> None:
        self.canvas.delete("all")
        teams = (self.stats or {}).get("teams") or []
        if not any(teams):
            self.canvas.create_text(WIDTH // 2, self.height // 2, text="Player stats are not ready yet", fill=GREY, font=("Segoe UI", 11))
            return
        for column, (title, team) in enumerate(zip(("YOUR TEAM", "ENEMY TEAM"), teams)):
            left = PAD + column * (SIDE + PAD)
            self.canvas.create_text(left, PAD + HEAD // 2, text=title, anchor="w", fill=GOLD, font=(self.family, 11, "bold"))
            for index, player in enumerate(team[:5]):
                self._card(left, PAD + HEAD + index * (ROW + GAP), player)

    def tick(self) -> None:
        """Called by the strip's program many times a second"""
        front = GoldBoard._game_in_front()
        if not (self.hotkey.update(front and self._keys_down(), time.monotonic()) and front):
            if self.visible:
                self.visible = False
                self.top.withdraw()
            return
        if self._reload() or not self.visible:
            self._draw()
        if not self.visible:
            self.visible = True
            self.top.deiconify()
            self.top.attributes("-topmost", True)

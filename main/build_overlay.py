#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The in-game build guide's strip: the next item of the build and its components, over the game.
The same program draws the gold board over the scoreboard while Tab is held (main/gold_board.py) and the
player stats panel on Ctrl+X (main/stats_panel.py).

A small program of its own, started by Rose when a game starts (main/game_build.py saved the build before).
It asks the game's own local "Live Client Data" address once a second for the player's gold and items, and
draws what main/build_guide.py answers. It never touches the game: the window is always on top, lets the
mouse through and never takes the keyboard. Hold Ctrl+Alt to drag it. Design: docs/in-game-build-guide.md.

Above the icons a row of text says the player's CS a minute (main/cs_rate.py; Ctrl+Shift+C in the game turns
it off and on, and that is remembered). Design: docs/cs-per-minute.md.
"""

import ctypes
import json
import sys
import threading
import time
import tkinter as tk
import traceback
import warnings
from typing import Optional

import requests
import urllib3
from PIL import Image, ImageEnhance, ImageTk

from main.build_guide import COMPONENTS_SHOWN, next_step
from main.cs_rate import CsRate, label, read_cs
from main.game_build import guide_dir, load_game_build, load_item_prices
from main.gold_board import GoldBoard
from main.gold_compare import lane_gold
from main.stats_panel import StatsPanel

GAME_API = "https://127.0.0.1:2999/liveclientdata/allgamedata"  # Riot's documented local address of a running game
TARGET, PART, PAD = 44, 34, 6  # icon sizes and spacing, in pixels
WIDTH, HEIGHT = PAD + TARGET + 14 + COMPONENTS_SHOWN * (PART + PAD), TARGET + 2 * PAD
ROW = 16  # the CS readout's row above the icons, in pixels
DARK, GOLD, DIM, GREEN = "#010a13", "#c8aa6e", "#3c3c41", "#3ddc97"
WAIT_FOR_GAME_S, GAME_GONE_S = 900, 20
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
VK_CONTROL, VK_MENU, VK_SHIFT, VK_C = 0x11, 0x12, 0x10, 0x43
CS_OFF = "cs_readout_off"  # this file in the guide's folder: the user turned the CS readout off (Ctrl+Shift+C)


_noted = ""  # the last error written down


def note_error() -> None:
    """Write the error being handled to state/build_guide/overlay_error.txt: this program has no log and no
    console, so that file is the only place it can say what went wrong."""
    global _noted
    error = traceback.format_exc()
    if error == _noted:
        return  # the same error every second is written once
    _noted = error
    try:
        (guide_dir() / "overlay_error.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S\n") + error, encoding="utf-8")
    except OSError:
        pass


def read_game(data: dict) -> Optional[tuple]:
    """(gold, the item ids in the bag) of the player at this computer, from the game's data; None if it isn't in it"""
    active = data.get("activePlayer") or {}
    me = active.get("riotId") or active.get("summonerName")
    for player in data.get("allPlayers") or []:
        if me and me in (player.get("riotId"), player.get("summonerName")):
            items = [int(item["itemID"]) for item in player.get("items") or [] for _ in range(max(1, int(item.get("count") or 1)))]
            return float(active.get("currentGold") or 0), items
    return None


class Strip:
    def __init__(self, build: Optional[dict], api: str, seconds: float = 0, place: Optional[tuple] = None,
                 prices: Optional[dict] = None, board_always: bool = False):
        self.build, self.api, self.prices = build, api, prices or {}  # no build: only the gold board shows
        self.stop_at = time.monotonic() + seconds if seconds else 0
        self.step, self.shown, self.running, self.grab = None, "nothing yet", True, (0, 0)
        self.gold = None  # the gold board's numbers
        self.cs_rate, self.cs = CsRate(), None  # the CS readout's text; None until the game answers
        self.cs_on, self.cs_key = not (guide_dir() / CS_OFF).exists(), False
        self.top = 0  # how far the icons are below the window's top: the readout's row, when it shows
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT, bg=DARK, highlightthickness=1, highlightbackground=DIM)
        self.canvas.pack()
        # The place is the icons' top left corner, as before the readout: its row is drawn above it
        self.place = place or self._saved_place() or (int(self.root.winfo_screenwidth() * 0.66), self.root.winfo_screenheight() - HEIGHT - 12)
        self.root.geometry(f"{WIDTH + 2}x{HEIGHT + 2}+{self.place[0]}+{self.place[1]}")
        self.root.withdraw()  # nothing to show until the game answers
        self.root.update_idletasks()
        self.window = ctypes.windll.user32.GetParent(self.root.winfo_id())
        self.through = None
        self._let_mouse_through(True)
        self.canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "grab", (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())))
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._save_place())
        self.images = {}
        self.board = GoldBoard(self.root, board_always) if self.prices else None
        self.stats_panel = StatsPanel(self.root)
        threading.Thread(target=self._watch_game, daemon=True).start()
        self.root.after(100, self._tick)

    def _let_mouse_through(self, through: bool) -> None:
        """Clicks go to the game under the strip, except while Ctrl+Alt is held (then the strip can be dragged)"""
        if through == self.through:
            return
        self.through = through
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(self.window, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style = style | WS_EX_TRANSPARENT if through else style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.window, GWL_EXSTYLE, style)
        self.canvas.configure(highlightbackground=DIM if through else GOLD)

    def _saved_place(self) -> Optional[tuple]:
        try:
            place = json.loads((guide_dir() / "position.json").read_text(encoding="utf-8"))
            return int(place["x"]), int(place["y"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _drag(self, event) -> None:
        x, y = event.x_root - self.grab[0], event.y_root - self.grab[1]
        self.root.geometry(f"+{x}+{y}")
        self.place = (x, y + self.top)  # a redraw during the drag must not put the window back

    def _save_place(self) -> None:
        try:
            (guide_dir() / "position.json").write_text(json.dumps({"x": self.place[0], "y": self.place[1]}), encoding="utf-8")
        except OSError:
            pass  # the strip just opens in its default place next time

    def _toggle_cs(self) -> None:
        """Ctrl+Shift+C in the game: the CS readout off or on, remembered for the next games"""
        self.cs_on = not self.cs_on
        try:
            if self.cs_on:
                (guide_dir() / CS_OFF).unlink(missing_ok=True)
            else:
                (guide_dir() / CS_OFF).write_text("", encoding="utf-8")
        except OSError:
            pass  # it is off or on for this game only

    def _watch_game(self) -> None:
        """Ask the game once a second. Ends the program when no game comes, or the game has gone."""
        started, last_answer = time.monotonic(), None
        # One kept connection: a new one for every question cost this program and the game a handshake each
        # second (27 ms a question against 5, measured in a game, Nov 13)
        asking = requests.Session()
        # shortcut: no certificate check, as for Rose's League client connection: the address is always
        # 127.0.0.1 (see main), only gold and items are read, nothing is sent. Check Riot's root
        # certificate (riotgames.pem) here if this ever reads anything that matters.
        asking.verify = False
        while self.running:
            game = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
                    data = asking.get(self.api, timeout=2.0).json()
                game = read_game(data)
                if game is not None:
                    if self.build:
                        self.step = next_step(self.build["order"], game[1], game[0], self.build["recipes"]) or "done"
                    self.gold = lane_gold(data, self.prices) if self.prices else None
                    cs = read_cs(data)
                    self.cs = label(self.cs_rate.update(*cs)) if cs else None
            except (requests.RequestException, ValueError):
                game = None  # no game yet, or no game any more
            except Exception:
                # An answer this program can't use must never end this loop: the program would not notice
                # the game going, would never close, and would draw what it last knew over the next game
                game = None
                note_error()
            now = time.monotonic()
            if game is not None:
                last_answer = now
            elif (last_answer is None and now - started > WAIT_FOR_GAME_S) or (last_answer is not None and now - last_answer > GAME_GONE_S):
                self.running = False
            time.sleep(1.0)

    def _icon(self, item: int, size: int, brightness: float):
        key = (item, size, brightness)
        if key not in self.images:
            try:
                image = Image.open(guide_dir() / "icons" / f"{item}.png").convert("RGB").resize((size, size))
            except (OSError, ValueError):
                image = Image.new("RGB", (size, size), DIM)  # no icon saved: a plain square
            self.images[key] = ImageTk.PhotoImage(ImageEnhance.Brightness(image).enhance(brightness))
        return self.images[key]

    def _draw(self, step: Optional[dict], text: Optional[str]) -> None:
        """The readout's row (when there is *text*) and under it the step's icons (when there is a *step*).
        The icons stay where they are: the row is added above them."""
        self.top = ROW if text else 0
        height = self.top + (HEIGHT if step else 0)
        self.canvas.delete("all")
        self.canvas.configure(height=height)
        self.root.geometry(f"{WIDTH + 2}x{height + 2}+{self.place[0]}+{self.place[1] - self.top}")
        if text:
            self.canvas.create_text(PAD, ROW // 2 + 1, anchor="w", text=text, fill=GOLD, font=("Segoe UI", 9, "bold"))
        if not step:
            return
        y = self.top + PAD + 1
        self.canvas.create_image(PAD, y, anchor="nw", image=self._icon(step["target"], TARGET, 1.0 if step["affordable"] else 0.55))
        self.canvas.create_rectangle(PAD, y, PAD + TARGET, y + TARGET, outline=GOLD if step["affordable"] else DIM, width=2)
        self.canvas.create_text(PAD + TARGET + 7, y + TARGET // 2, text="‹", fill=GOLD, font=("Segoe UI", 12, "bold"))
        x = PAD + TARGET + 14
        for part in step["components"]:
            top = y + (TARGET - PART) // 2
            lit = part["affordable"]
            self.canvas.create_image(x, top, anchor="nw", image=self._icon(part["id"], PART, 1.0 if lit else 0.6 if part["owned"] else 0.3))
            self.canvas.create_rectangle(x, top, x + PART, top + PART, outline=GOLD if lit else GREEN if part["owned"] else DIM, width=2 if lit else 1)
            if part["owned"]:
                self.canvas.create_text(x + PART - 7, top + PART - 8, text="✓", fill=GREEN, font=("Segoe UI", 11, "bold"))
            x += PART + PAD

    def _tick(self) -> None:
        if not self.running or (self.stop_at and time.monotonic() > self.stop_at):
            self.running = False
            self.root.destroy()
            return
        try:
            self._frame()
        except Exception:  # one bad frame must not stop the ticking: the program could then never close
            note_error()
        self.root.after(50, self._tick)  # the gold board follows the Tab key: twice as often as the strip needed

    def _frame(self) -> None:
        """What one tick draws: the strip when its step changed, and the gold board"""
        user32 = ctypes.windll.user32
        moving = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000 and user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        self._let_mouse_through(not moving)
        keys = all(user32.GetAsyncKeyState(key) & 0x8000 for key in (VK_CONTROL, VK_SHIFT, VK_C)) and GoldBoard._game_in_front()
        if keys and not self.cs_key:
            self._toggle_cs()
        self.cs_key = keys
        step = self.step if isinstance(self.step, dict) else None
        text = self.cs if self.cs_on else None
        shown = json.dumps([step, text], sort_keys=True)
        if shown != self.shown:
            self.shown = shown
            if step or text:
                self._draw(step, text)
                self.root.deiconify()
                self.root.attributes("-topmost", True)
            else:
                self.root.withdraw()  # no answer from the game yet, or every item is bought and the readout is off
        if self.board:
            self.board.tick(self.gold)
        self.stats_panel.tick()


def main() -> int:
    build, prices = load_game_build(), load_item_prices()
    if build is None and not prices:
        return 0  # no build was on the panel and no prices for the gold board: nothing to show
    args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)  # for tests: api=..., seconds=..., place=x,y, board=always
    place = tuple(int(n) for n in args["place"].split(",")) if "place" in args else None
    api = args.get("api", GAME_API)
    if not api.startswith(("https://127.0.0.1:", "http://127.0.0.1:")):
        return 2  # only ever a game on this computer
    strip = Strip(build, api, float(args.get("seconds", 0)), place, prices, args.get("board") == "always")
    strip.root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

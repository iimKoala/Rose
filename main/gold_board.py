#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The gold board: each lane's gold difference in items, over the middle of the game's scoreboard while Tab is held.

Part of the in-game strip's program (main/build_overlay.py); the numbers come from main/gold_compare.py.
Like the strip it never touches the game: always on top, lets the mouse through, never takes the keyboard.
To set it up, hold Ctrl as well as Tab: drag it with the left button, drag up or down with the right button
to change the distance between the rows, double-click if your team's numbers are on the wrong side (it switches
between the blue team on the left and your own team on the left). Design: docs/in-game-gold-board.md.
"""

import ctypes
import json
import tkinter as tk

from main.game_build import guide_dir
from main.gold_compare import compare

WIDTH, ROW, GAP = 150, 22, 6  # the board's width, a row's height, half the space between a row's two numbers
MIN_PITCH, MAX_PITCH = ROW, 200  # the distance from one row's top to the next
CLEAR, DARK, GOLD, DIM, GREY, GREEN, RED = "#010203", "#010a13", "#c8aa6e", "#3c3c41", "#a09b8c", "#3ddc97", "#e84057"
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
VK_TAB, VK_CONTROL, VK_MENU = 0x09, 0x11, 0x12
GAME_WINDOW_CLASS = "RiotWindowClass"  # the game's own window (the League client's is another class)


class GoldBoard:
    def __init__(self, root: tk.Tk, always: bool = False):
        self.always = always  # for tests: shown without Tab and without the game in front
        self.drawn, self.visible, self.through, self.rows = None, False, None, 5
        self.grab, self.stretch = (0, 0), (0, 0)
        saved = self._saved()
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        # shortcut: the defaults are measured for HUD scale 100% only (the user's scoreboard, 2560x1440, Nov 13:
        # rows 0.0697 of the screen's height apart, the free band at the top of the first row at 0.3464 of it,
        # the line between the teams 0.009 of it right of the middle); another HUD scale needs the one-time
        # set up (Ctrl+Tab, see above). Read the game's GlobalScale here if that ever matters.
        self.pitch = int(saved.get("pitch") or round(screen_h * 0.0697))
        self.mine_left = bool(saved.get("mine_left"))  # the left column: False the blue team, True my own team
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-transparentcolor", CLEAR)  # only the rows show: the scoreboard stays visible between them
        self.canvas = tk.Canvas(self.top, width=WIDTH, height=ROW, bg=CLEAR, highlightthickness=0)
        self.canvas.pack()
        x, y = saved.get("x", round(screen_w / 2 + screen_h * 0.009) - WIDTH // 2), saved.get("y", round(screen_h * 0.3464))
        self.top.geometry(f"{WIDTH}x{ROW}+{int(x)}+{int(y)}")
        self.top.withdraw()
        self.top.update_idletasks()
        self.window = ctypes.windll.user32.GetParent(self.top.winfo_id())
        self._let_mouse_through(True)
        self.canvas.bind("<ButtonPress-1>", lambda e: setattr(self, "grab", (e.x_root - self.top.winfo_x(), e.y_root - self.top.winfo_y())))
        self.canvas.bind("<B1-Motion>", lambda e: self.top.geometry(f"+{e.x_root - self.grab[0]}+{e.y_root - self.grab[1]}"))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._save())
        self.canvas.bind("<ButtonPress-3>", lambda e: setattr(self, "stretch", (e.y_root, self.pitch)))
        self.canvas.bind("<B3-Motion>", self._stretch)
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._save())
        self.canvas.bind("<Double-Button-1>", self._swap)

    def _saved(self) -> dict:
        try:
            saved = json.loads((guide_dir() / "gold_board.json").read_text(encoding="utf-8"))
            return saved if isinstance(saved, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        try:
            place = {"x": self.top.winfo_x(), "y": self.top.winfo_y(), "pitch": self.pitch, "mine_left": self.mine_left}
            (guide_dir() / "gold_board.json").write_text(json.dumps(place), encoding="utf-8")
        except OSError:
            pass  # the board just opens as it did before next time

    def _stretch(self, event) -> None:
        """The right button, dragged down or up: the last row follows the mouse, the rows between spread evenly"""
        start_y, start_pitch = self.stretch
        self.pitch = max(MIN_PITCH, min(MAX_PITCH, start_pitch + round((event.y_root - start_y) / max(1, self.rows - 1))))

    def _swap(self, _event) -> None:
        self.mine_left = not self.mine_left
        self._save()

    def _let_mouse_through(self, through: bool) -> None:
        """Clicks go to the game under the board, except while it is being set up"""
        if through == self.through:
            return
        self.through = through
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(self.window, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style = style | WS_EX_TRANSPARENT if through else style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.window, GWL_EXSTYLE, style)

    @staticmethod
    def _game_in_front() -> bool:
        user32 = ctypes.windll.user32
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(user32.GetForegroundWindow(), name, 64)
        return name.value == GAME_WINDOW_CLASS

    def _draw(self, gold: dict, setup: bool) -> None:
        swap = self.mine_left and gold["mine"] == "right"  # my team on the left: the columns change places on the red team
        rows = [row[::-1] for row in gold["rows"]] if swap else gold["rows"]
        mine_left = gold["mine"] == "left" or swap
        self.rows = len(rows)
        height = (len(rows) - 1) * self.pitch + ROW
        self.top.geometry(f"{WIDTH}x{height}")
        self.canvas.configure(height=height, bg=DARK if setup else CLEAR)  # set up: one solid block to grab
        self.canvas.delete("all")
        middle = WIDTH // 2
        for index, (left, right) in enumerate(rows):
            top = index * self.pitch
            if setup:  # set up: every row's place, full width
                self.canvas.create_rectangle(0, top, WIDTH - 1, top + ROW - 1, fill=DARK, outline=GOLD)
            if left is None or right is None:
                continue  # no opponent in this lane: nothing to compare
            texts = []
            for own, other, x, anchor, mine in ((left, right, middle - GAP, "e", mine_left), (right, left, middle + GAP, "w", not mine_left)):
                sign = compare(own, other)
                if mine:  # how far ahead or behind my team's player is, and the sign
                    lead = f"{own - other:+d}" if own != other else "0"
                    text = f"{lead} {sign}" if anchor == "e" else f"{sign} {lead}"
                    colour = {">": GREEN, "<": RED}.get(sign, GOLD)
                else:  # the opponent's side: the opposite sign alone
                    text, colour = sign, GREY
                texts.append(self.canvas.create_text(x, top + ROW // 2, text=text, anchor=anchor, fill=colour, font=("Segoe UI", 10, "bold")))
            if not setup:  # a dark box only as wide as the row's text, so little of the scoreboard is hidden
                boxes = [self.canvas.bbox(item) for item in texts]
                self.canvas.tag_lower(self.canvas.create_rectangle(
                    min(box[0] for box in boxes) - 5, top, max(box[2] for box in boxes) + 5, top + ROW - 1, fill=DARK, outline=DIM))

    def tick(self, gold) -> None:
        """Called by the strip's program many times a second with the latest numbers (None: none yet)"""
        user32 = ctypes.windll.user32
        held = lambda key: bool(user32.GetAsyncKeyState(key) & 0x8000)
        # Alt+Tab is Windows changing programs, not the scoreboard
        show = bool(gold and gold["rows"]) and (self.always or (held(VK_TAB) and not held(VK_MENU) and self._game_in_front()))
        if not show:
            if self.visible:
                self.visible = False
                self.top.withdraw()
            return
        setup = held(VK_CONTROL)
        self._let_mouse_through(not setup)
        wanted = json.dumps([gold, self.pitch, self.mine_left, setup])
        if wanted != self.drawn:
            self.drawn = wanted
            self._draw(gold, setup)
        if not self.visible:
            self.visible = True
            self.top.deiconify()
            self.top.attributes("-topmost", True)

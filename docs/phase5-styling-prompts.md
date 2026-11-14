# ROSE-AccountSwitcher: Phase 5 prompts (styling)

> **Replaced on Nov 8:** steps 39–45 below were built (theme, sidebar, header). From there, Phase 5 follows
> the CustomTkinter plan in the "ROSE-AccountSwitcher Build Prompts" doc (Phase 5A prompts 39–47 and
> Phase 5B prompts 48–56). Steps 46–58 below were not used.

Phase 5 restyles Rose's account window (main/account_gui.py) to look like the inspiration recording in
`C:\Program Files\Rose\_internal\docs\demo.gif`: a dark League-client theme, a rank sidebar, account cards
with rank crests and LP bars, and a step-by-step login screen. Nothing in it changes how accounts are saved
or how signing in works.

Run the steps in order, one per new chat, in Agent mode. Each step leaves the window working, so you can stop
after any of them. After each step: run the syntax check, open the window from the tray, and commit.

```
.venv\Scripts\python.exe -m compileall -q -x "\.venv" .
```

## Before Phase 5

Add these to `C:\Program Files\Rose\_internal\.continue\rules\mod.md` (done on Nov 8). The model can't see the gif, and the first two are the mistakes it
made in steps 36 and 37:

- Tiers are saved in capitals ("SILVER"). Compare with `(account.tier or "").strip().capitalize()`; empty or anything unknown means "Unranked". Division is "I" to "IV", or "" for Master, Grandmaster and Challenger.
- Each row or card on screen maps to `self._shown_accounts` (search, region filter and sort already applied). Never look an account up by position in `get_all_accounts()`.
- An account that has never signed in has `riot_id == ""`: show its `username` and "Sign in once to see rank".
- Use tkinter and ttk only. Add no new packages.
- Never show, copy or log passwords in the account window.

## Phase 5A: Theme

### 39. Colours and font

```
In Rose source, main/account_gui.py: below `log = get_logger()`, add these two dicts and this function exactly as written, and add `from utils.core.paths import get_asset_path` to the imports. Don't call anything yet. Change nothing else. Stop there.

THEME = {
    "bg": "#010a13", "panel": "#0a1428", "card": "#0b1621", "border": "#1e2d3d",
    "gold": "#c8aa6e", "gold_dark": "#785a28", "text": "#f0e6d2", "muted": "#a09b8c",
    "teal": "#0ac8b9", "teal_dark": "#005a82", "danger": "#e84057",
}
TIER_COLORS = {
    "Challenger": "#f4c874", "Grandmaster": "#cd4545", "Master": "#9d48e0", "Diamond": "#576bce",
    "Emerald": "#2c9a6b", "Platinum": "#4e9996", "Gold": "#cd8837", "Silver": "#8a9ba8",
    "Bronze": "#8c5a3c", "Iron": "#6b6461", "Unranked": "#5b5a56",
}


def load_league_font() -> str:
    """Load Rose's Beaufort font for this process only; fall back to Georgia"""
    try:
        import ctypes
        for name in ("BeaufortforLOL-Bold.ttf", "BeaufortforLOL-Regular.ttf"):
            ctypes.windll.gdi32.AddFontResourceExW(str(get_asset_path(name)), 0x10, 0)  # 0x10 = FR_PRIVATE
        return "Beaufort for LOL"
    except Exception as e:
        log.debug(f"[AccountGUI] League font not loaded: {e}")
        return "Georgia"
```

### 40. Dark window

```
In Rose source, main/account_gui.py, _create_window only: at the very top call load_league_font() and keep the result in self.title_font. Make the window 1000x650 (centre it with those numbers), minsize 820x520, background THEME["bg"]. Restyle the ttk styles it already configures with THEME colours: frames and labels on THEME["bg"] with THEME["text"]; Title.TLabel in (self.title_font, 22, "bold") with THEME["text"]; Subtitle.TLabel in THEME["muted"]. Add Kicker.TLabel (Segoe UI 9 bold, THEME["gold"]), Gold.TButton (THEME["panel"] background, THEME["gold"] text) and Teal.TButton (THEME["panel"] background, THEME["teal"] text), and style TEntry and TCombobox fields with THEME["panel"] and THEME["text"]. Change nothing else. Stop there.
```

Check: the window opens dark, bigger, and everything still works.

## Phase 5B: Layout

### 41. Two columns

```
In Rose source, main/account_gui.py: in _create_window, after _create_menu() and before _create_header(), create self.sidebar = tk.Frame(self.window, bg=THEME["panel"], width=220), pack it side=tk.LEFT, fill=tk.Y, and call self.sidebar.pack_propagate(False). Then create self.main_area = ttk.Frame(self.window) packed side=tk.LEFT, fill=tk.BOTH, expand=True, and inside it self.accounts_view = ttk.Frame(self.main_area) packed fill=tk.BOTH, expand=True. In _create_header, _create_search_bar, _create_account_list and _create_buttons change only the parent of their outer frame from self.window to self.accounts_view. In _create_status_bar change it to self.main_area and pack the status frame with side=tk.BOTTOM. Change nothing else. Stop there.
```

### 42. Sidebar: Add account and rank list

```
In Rose source, main/account_gui.py: at the top of self.sidebar add an "+  ADD ACCOUNT" button (style Gold.TButton, fill X, padx 12, pady (16, 12)) that calls self._on_add_account, then a "RANK DISTRIBUTION" label (style Kicker.TLabel, background THEME["panel"]). In _create_account_list, create self.tier_sidebar inside self.sidebar (below that label) instead of inside main_container. Keep the existing Add Account button at the bottom for now. Change nothing else. Stop there.
```

### 43. Tier rows

```
In Rose source, main/account_gui.py, _update_tier_sidebar only: replace each tier label with a row (tk.Frame, bg THEME["panel"], fill X, padx 12, pady 2) holding: a 12x12 tk.Canvas (bg THEME["panel"], highlightthickness 0) with a diamond polygon (6,0 12,6 6,12 0,6) filled with TIER_COLORS[tier]; the tier name on the left in THEME["text"]; and the count on the right in THEME["gold"], or THEME["muted"] when it is 0. Keep the counting code as it is. Change nothing else. Stop there.
```

### 44. Import and Export in the sidebar

```
In Rose source, main/account_gui.py: at the bottom of self.sidebar (pack side=tk.BOTTOM) add two flat buttons, "Export" and "Import", that call self._on_export and self._on_import. Keep the File menu as it is. Change nothing else. Stop there.
```

### 45. Header

```
In Rose source, main/account_gui.py, _create_header: show a small "RANKED SOLO / DUO" label (style Kicker.TLabel) above the title, and change the title text to "ACCOUNTS" (style Title.TLabel). Keep self.account_count_label but pack it on the right. In _load_accounts change only the count text to f"{len(accounts)} of {len(all_accounts)} accounts". Change nothing else. Stop there.
```

Check: sidebar on the left with Add account, the tier list with diamonds and counts, and Import/Export at the bottom.

## Phase 5C: Cards

### 46. Select accounts by id

```
In Rose source, main/account_gui.py: add self._selected_id = None in __init__. Add _select(self, account) that sets self._selected_id = account.id and calls self._on_account_select(). Change _selected_account to return the account in self._shown_accounts whose id equals self._selected_id, or None. In _on_account_select, when it is called with an event from the listbox, first set self._selected_id from the selected row: self._shown_accounts[index].id, or None if nothing is selected. Change nothing else. Stop there.
```

### 47. Card: name and details

```
In Rose source, main/account_gui.py: add _create_account_card(self, parent, account) that returns a tk.Frame (bg THEME["card"], highlightthickness=1, highlightbackground=THEME["border"], padx 12, pady 10). First row: the part of account.riot_id before "#" in (self.title_font, 13, "bold") THEME["text"], then "#" plus the part after it in THEME["muted"]. If riot_id is empty, show account.username and "Sign in once to see rank" in THEME["muted"] instead. Second row: the region in a small bordered label, "Level N" when level > 0, and account.username on the right in THEME["muted"]. Inside cards use tk.Label and tk.Frame with bg=THEME["card"], not ttk, so they take the card colour. Don't call it anywhere yet. Change nothing else. Stop there.
```

### 48. Card: rank crest and LP bar

```
In Rose source, main/account_gui.py: add _draw_crest(self, canvas, tier, size) that draws a diamond filling the canvas in TIER_COLORS[tier] with a smaller diamond inside it in THEME["card"] and a smallest one in TIER_COLORS[tier]. In _create_account_card, below the second row, add a rank block: a 64x64 canvas with _draw_crest; next to it the tier in capitals plus the division (for example "PLATINUM II", or "UNRANKED") in (self.title_font, 16, "bold") THEME["text"]; under it f"{account.lp} LP" in THEME["gold"] (leave it out when unranked); under that a 160x4 canvas LP bar with a THEME["border"] background, filled with TIER_COLORS[tier] to min(lp, 100) / 100 of its width, full for Master, Grandmaster and Challenger, empty when unranked. Tiers are saved in capitals: look the colour up with (account.tier or "").strip().capitalize() and use "Unranked" when it isn't in TIER_COLORS. Change nothing else. Stop there.
```

### 49. Card: footer and buttons

```
In Rose source, main/account_gui.py, _create_account_card: below the rank block add a 1px THEME["border"] line, then "Last season " plus account.last_season if it is set, then account.note in THEME["muted"] if it is set. Last, a button row: "›  LOG IN" (style Teal.TButton) that runs self._select(account) then self._on_switch_account(); "Edit" that runs self._select(account) then self._on_edit_account(); "Copy ID" that copies account.riot_id with self.window.clipboard_clear() and clipboard_append() (disabled when riot_id is empty); and "Remove" that runs self._select(account) then self._on_remove_account(). Never copy or show the password. Change nothing else. Stop there.
```

### 50. Card grid

```
In Rose source, main/account_gui.py, _create_account_list: replace the packing of the listbox container with a scrollable card area: a tk.Canvas (bg THEME["bg"], highlightthickness 0) with a vertical ttk.Scrollbar, and self.card_grid = tk.Frame inside it through canvas.create_window. Update the canvas scrollregion when card_grid changes size, keep card_grid as wide as the canvas, and scroll with the mouse wheel. Leave the listbox created but not packed. In _load_accounts, after the listbox is filled, destroy card_grid's children and add self._create_account_card(self.card_grid, account) for each account in self._shown_accounts with grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew"), and give the three columns weight 1. Change nothing else. Stop there.
```

### 51. Remove the old list

```
In Rose source, main/account_gui.py: remove the listbox, its scrollbar and its two bindings from _create_account_list, the listbox lines from _load_accounts, and the listbox branch from _on_account_select. Make a click anywhere on a card call self._select(account), and a double-click call self._select(account) then self._on_switch_account(). Give the selected card highlightbackground=THEME["gold"] and the others THEME["border"]. Change nothing else. Stop there.
```

### 52. Remove the bottom button row

```
In Rose source, main/account_gui.py: remove _create_buttons and its call; the cards and the sidebar now have every action. Then remove every use of self.switch_btn, self.remove_btn and self.edit_btn: in _on_account_select drop the state changes; in _on_switch_account add self._switching = True before the switch starts and set it back to False in done(), and return at the start of _on_switch_account if self._switching is already True. Add self._switching = False in __init__. Change nothing else. Stop there.
```

Check: cards in three columns, highest rank first; Log In, Edit, Copy ID and Remove work on the card you clicked, with search and the region filter on.

## Phase 5D: Login screen

### 53. Login screen layout

```
In Rose source, main/account_gui.py: add _create_login_view(self) that builds self.login_view = ttk.Frame(self.main_area) without packing it. Left half: a 120x120 canvas (self.login_crest), a title label (self.login_title, (self.title_font, 20, "bold")) and the Riot ID under it in THEME["gold"] (self.login_name). Right half: a 300x3 progress canvas (self.login_bar), then one row per step in LOGIN_STEPS, each an icon label and a text label kept in self.login_rows, then a message label (self.login_message) and a Close button (self.login_close) that calls self._show_accounts_view(). Add LOGIN_STEPS as a module constant: ["Closing League", "Starting the Riot Client", "Signing out of the Riot Client", "Filling in the sign-in", "Waiting for the sign-in", "Starting League"]. Add _show_login_view(self, account), which calls self.accounts_view.pack_forget(), resets every row to "○" in THEME["muted"], sets the title to "LOGGING IN" and the name to account_label(account), hides Close and packs self.login_view with fill=tk.BOTH, expand=True; and _show_accounts_view(self), which calls self.login_view.pack_forget(), packs self.accounts_view with fill=tk.BOTH, expand=True and calls self._load_accounts(). Call _create_login_view() at the end of _create_window. Don't use it yet. Change nothing else. Stop there.
```

### 54. Show progress while logging in

```
In Rose source, main/account_gui.py, _on_switch_account only: after the confirmation, call self._show_login_view(account). In progress(message), find the LOGIN_STEPS entry the message starts with; mark every earlier step "✓" in THEME["gold"], that step "…" in THEME["text"], and fill self.login_bar to (step index + 1) / len(LOGIN_STEPS). Steps can be skipped (the Riot Client may already be running or signed out), so always mark every earlier step done. In done(ok, message): if ok, mark every step "✓", fill the bar and set the title to "YOU'RE IN!" in THEME["teal"]; otherwise set the title to "COULDN'T SIGN IN" in THEME["danger"]. Show the message in self.login_message and show the Close button. Drop the failure messagebox. Keep every Tk call inside on_ui_thread as it is now. Change nothing else. Stop there.
```

### 55. Spinner

```
In Rose source, main/account_gui.py: while the login view shows "LOGGING IN", rotate a gold diamond outline on self.login_crest by 6 degrees every 50 ms using self.window.after and canvas.coords. Stop when done() runs or the view is hidden, and then draw the account's crest with self._draw_crest instead. Change nothing else. Stop there.
```

Check: Log In on a card shows the login screen, ticks the steps off, and ends on "YOU'RE IN!" or a clear error with Close.

## Phase 5E: Extras

### 56. Refresh every minute

```
In Rose source, main/account_gui.py: while the window is open, call self._load_accounts() every 60 seconds with self.window.after, except while self._switching is True. Keep the search text, region and selection. Stop the timer when the window closes. Under the title add "Ranks update every minute while League is open" in THEME["muted"]. Change nothing else. Stop there.
```

### 57. Click a tier to filter

```
In Rose source, main/account_gui.py: clicking a tier row in the sidebar sets self._tier_filter to that tier, or back to None if it is already selected, then calls self._load_accounts(). In _load_accounts, after the region filter, keep only accounts whose (account.tier or "").strip().capitalize() equals self._tier_filter, counting empty or unknown tiers as "Unranked". Highlight the selected row with THEME["gold_dark"]. Add self._tier_filter = None in __init__. Change nothing else. Stop there.
```

### 58. Real rank emblems (optional)

```
In Rose source, main/account_gui.py, _draw_crest only: if Rose's assets folder has ranks\<tier in lowercase>.png (use get_asset_path("ranks/" + name)), show that image on the canvas with tk.PhotoImage, scaled down with subsample to fit the canvas, and keep a reference in self._images so it isn't garbage-collected. Otherwise draw the diamonds as now. Change nothing else. Stop there.
```

Then put PNGs named `challenger.png` to `iron.png` and `unranked.png` in `Rose\assets\ranks`. Rose doesn't
ship Riot's emblem art, and the League client keeps it packed in `.wad` files.

## Left out on purpose

- **TFT tab, Friend elo filter, ban badge:** Rose doesn't save TFT ranks, friend data or ban status.
- **Cancel on the login screen:** signing in can't be stopped halfway yet (`main/account_login.py` has no cancel). It needs its own backend step first.
- **Lock icon:** in the inspiration it handles the password. The window never shows or copies passwords.
- **In-client panel restyle:** Phase 5 is only Rose's window. The panel in the League client could follow the same theme later.

# Test list (next session, after Nov 10: Rose 1.5.6)

About 20 minutes. Tell me what happens at each step (a photo is enough). League and the Riot Client are closed.

Already working live: the account window, switching to the right player, filling the sign-in behind other windows,
a wrong password caught in 4 s, Rose's restart of an "unknown player" League (now fast), skin mods read their
champion from the file, the Install mod window for an announcer.

## 1. Start Rose 1.5.6
Tray > **Quit** the old Rose, then double-click **rose.bat** on the Desktop (accept the admin prompt).
Never start Rose from the Start menu or `C:\Program Files\Rose\Rose.exe`: that is the old v1.5.2 build, and if you
accept its "update to 1.5.6" offer it mirrors the release over the install and deletes our source folder
(`_internal\Rose`, with 94 commits that exist nowhere else). The tray must say **Rose v1.5.6** and show Account Switcher.
On this first start 1.5.6 moves your map, font and announcer mods into LTK Manager's own library (LTK Manager may
start hidden for it). It asks once: "Do you want a backup of your mods on your desktop first?" (about 460 MB):
either answer is fine. Rose's copies of those four go; nothing else changes.

## 2. No more "unknown player" (Rose restarts the Riot Client for each switch)
Tray > Account Switcher > **LOG IN** on an account that is not signed in. Don't touch anything.
Rose signs the old account out, then **closes the Riot Client and starts it again** (a few seconds), signs in and
presses Play. That's on purpose: Riot's own logs (Nov 10) show a Riot Client that already held one account starts
League wrong for the next one ("unknown player" in 12 switches of 16), while a freshly started one worked 3 times
in 3. The 20 s wait is gone: it waited 28 s at 20:34 and still failed.
Check two things:
- The **first** League opens with the right player: no "unknown player", no restart by Rose.
- **Start Game / Find Match works** (the ready check is accepted). On Nov 10 it failed 4 times in a row after a
  switch from the EU account to the NA one: do at least one switch between those two.
Send me the Rose log line `[AccountLogin] Closed the Riot Client (...)` and what happened. Do it 4 times
(different accounts, some from the League client's own account panel).
Logging in to the account that is already signed in doesn't restart anything.
After a switch, the client's Troubleshooting panel must NOT show "League runs as administrator": the first
version of this restart (21:22-22:20 on Nov 10) started the Riot Client with Rose's administrator rights, so
no mod could be applied. It now starts through Explorer with normal rights. If the panel still shows it, quit
the Riot Client from the system tray, start it from the Start menu, and tell me.
Rose also closes old Account and Mod store windows when it starts, so a window always runs the current code.

## 3. Mod store: Installed, broken mods and Fix
Open the Mod store from the new **shopping-bag button** in the League client's top bar (next to the new Account
Switcher icon, a person with two arrows), then its **Installed** tab: all 6 store mods are listed once (Talon
Mahoraga, Coven Qiyana ASU, Map Forcer, Rift of the Unbound, Original TF2 Font, The Administrator Announcer).
Under each, after a few seconds: "Works with this patch", "Kept in LTK Manager's library" (the four moved in step 1),
or for Talon and Qiyana "Needs a repair: N problem(s) that can crash the game" with a **Fix** button.
Press Fix on Talon: it should say "Fixed 28 problem(s): works with this patch".

Then click on the League client so the store is behind it, and press the shopping-bag button again: the store
should come to the front (it used to do nothing). It also opens about 0.3 s sooner.

## 4. Mod store: Qiyana by reinstalling, then a game
Install **Coven Qiyana** again from the store instead of pressing Fix: Rose repairs it on the way in (79 fixes; the
log says "Repaired ... problem(s)"), names it after the mod, and the old code-named copy ("b0c9e0a4...") is replaced:
Installed still lists it once.
Then play a game (Practice Tool is enough) with Talon Mahoraga: no crash while loading (on Nov 10 it crashed 4 of 4
with "Missing Game Data"). If a mod ever crashes a game again, Troubleshooting now says "The game crashed while
loading a mod" with the mods' names, instead of "Injection failed".

## 5. Maps (optional)
Rose picks one map mod at a time. Map Forcer is not needed (Nov 10): Rift of the Unbound works without it.
Three more maps were checked against this patch on Nov 10 with Rose's own checker (not played in a game yet):
- **DARK Mode Summoner's Rift** (p1mek, built for patch 16.1): 200 problems that crash the game. Rose repairs all
  200 when you install it from the store; the repaired map then passes the check.
- **Winter Rift 2025 (Season 25 Version)** (TheKillerey) and **Hexed Rift** (Aropatnik): pass as they are.
All of their files replace files the game still has. Install one from the store, pick it as the map, and try it in
the Practice Tool. If a map crashes, send me the newest folder in LTK Manager's incidents (path below).

## 6. Builds in champ select (Nov 11: the panel worked in your first test; Import is now a button)
Restart Rose (quit from the tray, then Start Rose.bat) so the League client loads the changed ROSE-Builds plugin.
Lock a champion: the panel "Builds · onetricks.gg" shows the first of the top 3 players for your lane with
their runes, spells, items and skill order. The arrows beside the name step through the 3 players; the arrows
beside "Usual build" / "vs <champion>" step through the enemies that make sense in your lane.
**Nothing is imported until you press a button.** There are three (Nov 13): **Runes**, **Spells** and
**Items**. Each imports only its part; the panel lists what was done and ticks that button. Stepping to another
player or opponent clears the ticks, and nothing changes in the client until you press a button again.
Under the build the panel also shows what the top 3 players build when they need it: rows **Armour**,
**Magic res.** and **Damage**. Pressing Items puts them in the shop's item set as three blocks.
Check: locking a champion and using the arrows must NOT change your rune page, spells or item sets.
The panel can be **dragged by its title bar**; it stays inside the client window and opens in the same place
next time.

## 7. In-game build guide (new, Nov 11; never run in a real game yet)
Restart Rose. In champ select lock a champion so the builds panel shows a build (Import or not), then play the
game (a Practice Tool game is fine). A few seconds after the game starts, a small dark strip appears near the
bottom of the screen, right of the abilities bar: the next item of the build, an arrow, and its components.
- A component your gold can buy now has a **gold border**; one you own has a green tick; the others are dim.
- When your gold covers the whole item, the item itself gets the gold border.
- After you buy the item the strip moves to the next one. After the core build it goes on with that player's
  other usual items (Nov 13); after the last it disappears.
- The mouse goes through it to the game. **Hold Ctrl+Alt** (its border turns gold) and drag it where you want
  it, between the minimap and the abilities; it remembers the place.
Tell me: whether it shows at all (it needs borderless or windowed mode, which you use), where it first
appears, whether the lit components match what the shop lets you buy, and whether it ever takes a click or the
keyboard from the game. Rose's log has a line `[GUIDE] Started the in-game build guide`.

## 8. Accounts: divisions, card height and the client panel (Nov 13)
Restart Rose with League open and signed in.
- **Divisions.** Within about a minute Rose looks up the rank of your other saved accounts through the account
  that is signed in (the client's own player lookup; nothing is signed in or out). Open the account window:
  the accounts that showed only "GOLD" or "SILVER" should now show their division. Rose's log has a line
  `[LCU] Looked up the rank of N other saved account(s)`. It repeats every 30 minutes, never during a game.
  An account on another server than the signed-in one keeps what Rose had.
- **Card height.** With few accounts the cards keep their natural height: no tall gap above LOG IN.
- **Client panel** (the Account Switcher button in the League client): the Active badge sits under the name
  beside the region tag, the rank and level text is smaller than the name, and ranked accounts show the
  client's own rank emblem where the letter was (unranked accounts keep the letter).

## 9. Reconnect screen: choose which mods to disable (new, Nov 13; never run on a real crash yet)
Restart Rose so the client loads the new ROSE-ReconnectMods plugin. Use a **Practice Tool** game (nothing at
stake) with a skin and at least one other mod (a map, a font...).
1. In the game, close it the hard way: Task Manager > "League of Legends (TM) Client" > End task. The League
   client shows its reconnect screen.
2. Next to RECONNECT there is **Disable mods ▾** (Rose's old "Disable Rose mods" button is gone: it is the
   last row of the drop-down). Click it: this game's mods are listed by name, each with a tick box.
3. Tick one mod (the map, say) and press **Disable selected**. It says "Turning them off... wait before you
   press Reconnect", then **"Done: press Reconnect"** (the overlay is built again: a few seconds to half a
   minute). The mod now shows "(off)".
4. Press RECONNECT. The game should load **without that mod and with the others**.
5. Next game: every mod is on again (the choice lasts for one match).
Also worth one try: with the game still running, the drop-down answers "The game is still running: close it
first" and changes nothing; and "All Rose mods" does what the old button did.
Rose's log has `[INJECT] Reconnect: leaving out <names>` and `[INJECT] Reconnect: the LTK patcher is ready
without them`. If you press RECONNECT before "Done", Rose holds the game until the overlay is built and
restarts it once, as at the start of a game.

## 10. Gold board on the scoreboard (new, Nov 13; never run in a real game yet)
Restart Rose. Start any game (Practice Tool is fine; a real Summoner's Rift game shows all five lanes).
1. Hold **Tab**: over the scoreboard there are small rows like `+2500 >   <`, one per lane from top to
   support: on your side how much gold in items that lane is ahead (green, +) or behind (red, -), and only
   the opposite sign on the enemy's side. Release Tab: they are gone. They follow purchases within a second
   or two.
2. **Place it once.** The first place is a guess (Rose cannot see your scoreboard). Hold **Ctrl as well as
   Tab**: the rows turn into one block with gold edges. Drag it with the left mouse button to the middle of
   the scoreboard; drag up or down with the **right** button until the rows sit on the scoreboard's rows;
   if your team's numbers are on the wrong side, **double-click** it. Let go: it is saved.
3. Clicks go through it to the game (except while Ctrl is held), and Alt+Tab does not show it.
4. It needs no build: with nothing imported in champ select the build strip stays away and the board still
   shows. Rose's log has `[GUIDE] Started the in-game build guide and gold board`.
A screenshot of your scoreboard with the board placed would let the first place be right for everyone with
your screen and HUD scale. Design: `docs/in-game-gold-board.md`.

## 11. Mod store: Fix on a mod with loose files, and Rename (Nov 13, evening)
- **Fix.** Mod store > Installed > Noxus Rift: Original > **Fix**: "Fixed 65 problem(s): works with this
  patch" (this needs no restart of Rose). A Fix that repairs nothing now says "Couldn't repair it (the reason
  is in Rose's log)" instead of showing the same line again.
- **Rename** (restart Rose first, then open the store again). Each card has **Rename** between Open page and
  Delete: it opens a text box under the name; Enter or Save keeps the new name, Esc cancels. Only the name
  Rose shows changes (on this page and in Rose's own mod lists in the client), never the mod's file. A mod you
  already renamed in Rose ("Night", "Day") shows that name here. Updating a renamed mod from the store
  installs a new copy, which starts with the store's name again.

## 12. Player stats panel, Ctrl+X (new, Nov 14; never run in a real game yet)
Restart Rose, then play a game (a ranked or normal game shows the most; Practice Tool has no opponents).
1. In the game, tap **Ctrl+X**: a panel opens over the top of the screen with your team on the left and the
   enemy team on the right, top to support: champion, name, rank and LP, the season's win rate and games,
   the peak. Tap Ctrl+X again: it closes. Hold Ctrl+X instead: it shows only while you hold.
2. Your own row has your full record. The others' win rates come from deeplol and appear a few seconds
   after the game starts; a player deeplol doesn't know shows only "N wins".
3. Clicks go through it to the game, and it hides when you alt-tab away.
4. The new look (Nov 14): a card a player like the account switcher's, with the rank's emblem, the tier in
   gold and an LP bar. On the right of each card: SEASON, and under it the champion's name with the win
   rate on that champion ("no games" when the player has none on it in solo queue this season). Your own
   card has a gold edge and counts your last ranked games on the champion ("3 recent").
Rose's log has `[STATS] Saved rank and win rate of 10 player(s) from the League client` and
`[STATS] deeplol added the season's record and peak for N player(s)`. Your own account is never sent to
deeplol. Design: `docs/player-stats-panel.md`.

## 13. Mod store: Divine Skins as a second shop (first step, Nov 14)
Restart Rose and open the Mod store. The bar at the bottom now has **RuneForge** and **Divine Skins** beside
Back and Installed.
1. Press **Divine Skins**: the site opens in the store window (its cookie box and any sign-in are yours to
   answer; Rose reads nothing of them).
2. Open a League mod's page and press the site's own download. If the site hands over a mod file (.fantome,
   .zip, .modpkg), Rose checks it, asks where it goes, and installs it: it then shows in the same Installed
   list, with Open page, Rename, Delete and Fix.
3. Second step (Nov 14, after three real downloads): the mod is named without "Download " in front, the
   browser's own Downloads box no longer appears (its "Open file" started LTK Manager on the file while Rose
   was installing it: four LTK Manager windows, one hung, the next game unmodded), and no LTK Manager window
   opens during an install. If one still opens, tell me what you pressed just before.
4. The call back (Nov 14): start a download, then click into the League client while the site's wait runs.
   When the mod is downloaded and checked, Windows' notification sound plays and the store's taskbar button
   flashes: it is asking where the mod goes. It does the same when the install is done. With the store in
   front there is no sound and no flash, and the store never jumps in front of what you are doing.
5. The "Tired of waiting?" box (Nov 14): after a download starts on Divine Skins, the box that offers
   Divine+ should close by itself within a second. The shop's wait is not changed. The closer was written
   from a picture of the box, not from the page, so if the box stays open, tell me: its X is built another
   way than guessed.
Not yet for Divine Skins: "Check for updates" (RuneForge only). Rose installs only what the site lets you
download yourself.

## 14. Builds panel: other builds, role buttons, skill notes (new, Nov 14; never seen in the client yet)
Restart Rose, then lock a champion in champ select.
1. **Runes row**: the keystone is the first icon.
2. **Role**: five buttons at the top, yours marked. Press another (as after a swap): the three players change
   to that lane's. Press your own again to go back.
3. **Build arrows** (third pair, only for a player with two or more builds): "Automatic build" first, then
   "Build 1 of N" with its first item and share of games. Runes, spells and items change with it. Press an
   Import button: that build is imported, not the matchup's. Stepping the player or opponent arrows goes
   back to automatic.
4. Import **Items**, then open the shop in game: the set's first two titles carry the skill order, like
   "Start (levels 1-3: W Q E)" and "Build in this order (max W > Q > E)".

If anything goes wrong: tray > Open Logs folder. The account window's log is `account_window_*.log`;
the store's is `mod_store_*.log` (never contains the signed download links). LTK Manager's crash reports are in
`%APPDATA%\dev.leaguetoolkit.manager\incidents`.

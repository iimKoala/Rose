# In-game build guide (design, Nov 11)

What the user asked for (their words, Nov 11): "in-game build guide. Takes the items in order from build and
will display the smaller components highlighting it when available to purchase/enough gold. Should be small,
but big enough to fit 3 components in. Should fit between minimap and abilities ui."

## Facts checked

- The user's game: 2560x1440, `WindowMode=2` (borderless), HUD scale `GlobalScale=0.0` (smallest), minimap on
  the right (`FlipMiniMap=0`) at `MinimapScale=3.0` (`Config/game.cfg`). Borderless matters: a small always-on-top
  window shows over a borderless or windowed game, not over exclusive fullscreen.
- Riot's own local "Live Client Data API" (developer.riotgames.com/docs/lol, Game Client API) runs while a game
  runs: `https://127.0.0.1:2999/liveclientdata/activeplayer` gives `currentGold`,
  `/liveclientdata/playeritems?riotId=<name#tag>` gives the items owned (`itemID`, `count`, `slot`), and
  `/liveclientdata/allgamedata` gives both. Nothing is read from or written to the game's memory.
- Riot's developer policy lists "Game overlays that provide static data that is available prior to the game" as
  an approved use, and forbids "game-session-specific information that would be previously unknown to the"
  player. A build order chosen before the game, plus whether the player's own gold covers a component, is both.
- Item recipes (`from`, `price`, `priceTotal`, `iconPath`) are in the League client's game data
  (`/lol-game-data/assets/v1/items.json`), which Rose can read while the client is open.

## Design

1. **The build.** The build that is on the builds panel when champ select ends (imported or not). Its order is
   the path, with the boots where that player usually buys them (the site's boots timing), last if unknown.
2. **What is shown.** A strip about 190x56 px: the next item of the order that the player doesn't own yet, and
   to its right its direct components (up to 3). A component the player owns is ticked; one the player's gold
   can buy now is lit in gold; the others are dim. When the gold covers the whole item, the item itself is lit.
   When the item is bought, the strip moves on to the next one; after the last, it hides.
3. **Where.** Between the abilities bar and the minimap, computed from the screen size; the mouse goes straight
   through it to the game. Holding **Ctrl+Alt** makes it draggable; its place is remembered.
4. **How.** A small program of its own (`main/build_overlay.py`, tkinter, always on top, never takes the
   keyboard from the game), started by Rose when a game starts and gone when it ends. It asks the game's local
   API once a second. The logic (which item is next, what the gold buys) is `main/build_guide.py`, tested
   without a game.

## Build steps (all written Nov 11; step 6 is the user's)

1. Reader: where the boots come in the order (`main/onetricks.py`, `bootsAfter`).
2. Logic: `main/build_guide.py` (a part in the bag is first that component itself, then counts inside others).
3. Saving: `main/game_build.py`, called each time the builds panel gets a build
   (`pengu/communication/build_handlers.py`). A build saved over 30 minutes ago is ignored.
4. The strip: `main/build_overlay.py`, 184x56 px, tested against a fake game on this computer.
5. Start: `threads/handlers/phase_handler.py` calls `start_overlay()` when the phase becomes InProgress.
6. Live test by the user: step 7 of `docs/home-test-checklist.md`. Never run in a real game yet.

## Known limits

- Exclusive fullscreen: the strip would not show (the user plays borderless).
- Items that change id after buying (an upgraded or transformed item) count as owned through their recipe.
- The first place of the strip is a guess for this screen and HUD scale; Ctrl+Alt and drag fixes it once.
- The game's local address is read without a certificate check (127.0.0.1 only, gold and items only).

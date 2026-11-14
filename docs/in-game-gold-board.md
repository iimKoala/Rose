# In-game gold board (built Nov 13; never run in a real game yet)

What the user asked for (their words, Nov 13): "total gold based off items when tab is held in game. Compared
each lane top and top, JG and JG, etc... like say Im jg and have $2250 in items and my enemy jg has $1500 it'll
show the gold and a greater than symbol on my side, as well as a less than symbol on his. Should be placed
where in the middle of the scoreboard (once tab is held). And show for all lanes".

## What it does

While Tab is held in a game, five small rows appear over the middle of the scoreboard, one per lane (top,
jungle, mid, bot, support):

    -50 <   >
    +2500 >   <

The number, on the user's side of the row, is the lane's gold difference: the shop price of everything the
user's player holds minus the lane opponent's (the user corrected the first version, which showed the two
totals: "should be difference, not total"). `>` ahead (green), `<` behind (red), `0 =` even (gold); the
enemy's side shows only the opposite sign, in grey. A lane without an opponent shows nothing.

## How

- **The numbers** (`main/gold_compare.py`): the game's own local "Live Client Data" address
  (`https://127.0.0.1:2999/liveclientdata/allgamedata`, Riot's documented one, already read once a second by
  the build strip) lists every player's team, lane (`position`) and items: the same items the scoreboard
  shows. Each item counts its full shop price (`priceTotal` in the League client's item data), not the game's
  own `price` field, which is only the combine cost (Rabadon's: 1100 instead of 3500).
- **Prices** (`main/game_build.py`): `start_overlay(lcu)` saves `{item id: priceTotal}` to
  `state/build_guide/item_prices.json` when a game starts; if the client gives none, the last saved are used.
- **Lanes**: a team is sorted top to support when the game names each of the five lanes once; otherwise
  (ARAM, Practice Tool) the players are paired in the order the game lists them. The blue team (`ORDER`) is
  the left column, the red team (`CHAOS`) the right.
- **The window** (`main/gold_board.py`), part of the strip's program (`main/build_overlay.py`, which now also
  runs when there is no build to follow): always on top, lets the mouse through, never takes the keyboard,
  transparent between the rows. Shown only while Tab is down (`GetAsyncKeyState`), Alt is not (Alt+Tab), and
  the game's window (`RiotWindowClass`) is the one in front.
- **Where it is.** Measured on the user's scoreboard (a picture of the screen, 2560x1440, HUD scale 100%,
  Nov 13): the scoreboard's rows are 100.3 px apart (0.0697 of the screen's height), the line between the two
  teams is 13 px right of the screen's middle (0.009 of the height), and each row has a free band about 33 px
  high above its item icons, the first at 0.3464 of the height. The board's rows sit in those bands, centred
  on that line, and each row's dark box is only as wide as its text, so no item or portrait is covered. These
  are the defaults for HUD scale 100%; the first guess (rows 55 px apart, for a small HUD) drifted off the
  lanes.
- **Moving it** (another HUD scale, or taste): hold **Ctrl as well as Tab**: the board turns into one solid
  block; drag it with the left button, drag up or down with the right button to change the distance between
  the rows, double-click if the user's numbers are on the wrong side. Saved in
  `state/build_guide/gold_board.json`. Never tried in a real game yet.
- **Which team is the left column.** Not confirmed for the scoreboard, so the double-click switches between
  the two possible layouts: the blue team on the left (the default), or the user's own team on the left
  (`mine_left`: the columns then change places when the user is on the red team). Either way it stays right
  on both sides once set.

## Not checked, and risks

- The default place is measured for HUD scale 100% on one screen; another HUD scale needs the one-time
  move. Whether the scoreboard shows blue on the left for a red-side player is not confirmed (hence the
  double-click): the picture was of a blue-side game.
- The game with a scoreboard key other than Tab is not covered.
- Like the strip, the window is drawn by Windows over a borderless or windowed game; exclusive full screen
  hides it.

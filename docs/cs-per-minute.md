# CS a minute on the build strip

Asked for on Nov 21: a CS-per-minute readout on the in-game build strip.

## What it shows

- A 16 px row of text above the strip's icons: `CS/min 7.4`. That is the player's creep score (minions and monsters) divided by the minutes of game time. During the first 90 seconds it says `CS/min –`: no minion can have died yet.
- The icons stay where they were. The strip's place, saved or default, is still the icons' corner, and the row is added above it.
- When every item of the build is bought, or there is no build, the row stays alone.
- **Ctrl+Shift+C** in the game turns the row off and on. The choice is remembered for the next games (an empty file `cs_readout_off` in the guide's folder, `%LOCALAPPDATA%\Rose\state\build_guide`). The keys count only while the game's window is in front, so a copy in a terminal does nothing.

## Where the numbers come from

Riot's own local Live Client Data, the address the strip already asks once a second: `allPlayers[].scores.creepScore` of the player at this computer and `gameData.gameTime`. Both numbers are on the player's own screen in the game, the count and the clock at the top right. The readout is the division. Nothing is read from the game's memory.

## A count that may move in tens

It has been reported that the game moves `creepScore` only in steps of 10. A web search on Nov 21 found nothing for or against it, and only a game can show it. So `main/cs_rate.py` (`CsRate`) is right for both:

- The first time it sees a count that is not a multiple of 10, it knows the game counts every minion, and from then on the rate is the count over the minutes.
- Until then it takes the count as possibly moving in tens. At the moment the count moves it is exact, so the rate of that moment is kept. After that up to 9 more minions may have died: the rate falls only once even `count + 9` over the minutes is less.

A count in tens makes the number late by one step at most, never wrong by a whole step for long.

## Who wrote what

`main/cs_rate.py` was written by the local Continue model from a brief with worked examples. The wiring in `main/build_overlay.py`, the tests and this note are Claude's.

## Checked, and not

- `test/test_cs_rate.py`: reading the count and the time (and data without them), both kinds of count, the first 90 seconds, a strip started in the middle of a game, the text.
- The real strip was shown over a stand-in game and photographed in its states: icons with the row, the row alone, icons alone after turning it off, and back on. The window's place and size were read back from Windows in each.
- **Not checked: a real game.** Whether the count moves by one or by ten there, how the row looks over the HUD, and Ctrl+Shift+C itself (the key check needs the game's window in front; the test called what the keys call).

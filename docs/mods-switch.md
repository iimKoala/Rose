# Mods in game: a switch (Nov 25)

## Why

On Nov 25, 2026 the developer's game showed a Riot Vanguard window: "the following software is interrupting the game regularly, consider disabling it to improve performance", naming `ltk_patcher_dll.dll` in LTK Manager's `patcher` folder. That evening, five games out of five that had LTK Manager's patcher in them closed by themselves 1.5 to 5 seconds into play (`Quit Game Confirmed` in the game's own log, each time right after LTK Manager's `game found; hook installed`). A game started without Rose stayed open.

What had changed: Riot Vanguard's files were dated that morning. LTK Manager (v1.33.0, the newest release) and its patcher (delivered Nov 18) were the ones that ran a 35-minute game on Nov 21.

The patcher is LTK Manager's. Rose's source never names it and sets none of its options: Rose asks LTK Manager to start and stop it. So there is nothing in Rose to repair, and hiding a module from an anti-cheat is not something this fork does. What Rose can do is not load anything: until then it had no way to run without putting mods in the game, so every game was closed and the fork's other features (account switcher, builds, in-game panels, auto accept) were only usable by closing Rose.

## What it is

- **Tray icon > Mods in game**, a ticked item. A press turns it off or on and says so in a notification.
- **Off**: Rose starts no patcher, installs no mod into LTK Manager and holds no game. Nothing of Rose's or LTK Manager's is loaded into the game. The player's own pick in champion select is left alone (no base skin is forced for a skin that will not be injected). Everything else in Rose works as before.
- **On** (the default, and what a new install has): as before.
- It is kept as a file, `mods-off.txt` in Rose's data folder (`%LOCALAPPDATA%\Rose`): there while mods are off, with the reason and the time in it. No update writes that folder.
- A switch turned off during champion select counts from that game on: a patcher the countdown had already started is dropped when the injection would begin. Turned off during a game, it counts from the next one.

## How

- `injection/core/mods_switch.py`: the file (`is_off`, `reason`, `turn_off`, `turn_on`), written by the local Continue model from a brief; and `arm` / `off_now`, added in review: only a Rose that armed the switch at its own start obeys it, so the tests and tools that build the injection on the developer's PC are never reached by that PC's file.
- Every way to the patcher goes through four methods of `OverlayManager` (`start_patcher_early`, `open_staging`, `stage_mods`, `mk_run_overlay`): each asks the switch first. The game is only ever held inside the sessions those start.
- `InjectionTrigger.trigger_injection` asks it too, before it looks at the pick, and drops a patcher the countdown started.
- `utils/integration/tray_manager.py`: the item. `main/__init__.py`: arms the switch at Rose's start and logs a warning when it is off.

## Checked, and not

- `injection/tests/test_mods_switch.py`: the file's behaviour; armed and not armed; off, none of the four methods asks LTK Manager for anything, and on they do; the trigger leaves the pick alone and drops an early patcher; the tray item's tick, press and notification. The gate test was also run with the gates taken out: it fails there.
- **Not checked: a game.** Rose with the switch off has not been run through a champion select and a game yet.
- Not built: turning the switch off by itself after games that close at their start. Until then the player has to do it.

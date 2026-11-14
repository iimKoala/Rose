# Choosing which mods to disable on reconnect (built Nov 13; not yet run on a real crash)

What the user asked for (their words, Nov 13): "if the game crashes, the user can choose which mods to
disable on reconnect, instead of disable rose, its a drop down of mods to disable on reconnect".

## What Rose does today (upstream)

- `Pengu Loader/plugins/ROSE-SettingsPanel/index.js` (`addStopInjectionButton`): on the client's reconnect
  screen (`.reconnect-button-container`) it adds one button, "Disable Rose mods". It sends `stop-injection`.
- `pengu/communication/message_handler.py` `_handle_stop_injection` → `injection_manager.stop_injection_by_user()`
  → the LTK patcher is stopped for the rest of the match. The user then presses the client's Reconnect and
  plays with no mods at all.

## How a game's mods are applied (what the feature has to work with)

- The mods of a game are chosen in the shared state: the Riot skin (the name the loadout ticker passes to
  `InjectionTrigger.trigger_injection`), `selected_custom_mod`, `selected_map_mod`, `selected_font_mod`,
  `selected_announcer_mod`, `selected_other_mods`. With nothing picked, the last used map / font / announcer is
  picked again (the "historic" mod).
- Every path ends in `OverlayManager.mk_run_overlay(mod_names)` (`injection/overlay/overlay_manager.py`): it
  installs the mods into LTK Manager, starts LTK Manager's patcher and stays in the session until the game is
  over. The names are readable: the map's, font's, announcer's and other mods' names, `Skin Carrier (...)` for
  the Riot skin, `Loading screen name`, and a 32-character id for a custom skin.
- After the install the extracted folders are wiped, but the mods stay in LTK Manager's library until the
  session ends: turning one off there is enough, nothing has to be installed again.
- The session loop ends the session when it sees a stopped patcher and no game, and the bridge to LTK Manager
  is not shared between threads: the patcher is stopped and started again only by the session's own thread,
  between two looks at its status.
- A game that starts before the patcher is ready is held (suspended) by Rose until it is, so an early press on
  Reconnect is safe.

## Design (as built)

1. **The list.** On the reconnect screen, in place of the one button: a drop-down "Disable mods" that lists
   this game's mods by the names LTK Manager shows, each with a tick box (what Rose imported for the game and
   the saved mods it switched on; never the user's own LTK Manager mods), and "All Rose mods" (what the button
   did: `stop-injection`, unchanged).
2. **Apply.** "Disable selected" sends the ticked ids to Rose. The game session itself (its loop, its thread:
   the bridge to LTK Manager is not shared between threads) stops the patcher, turns those mods off in LTK
   Manager, starts the patcher and waits until it is ready: the same order `_install_mods` uses when the mods
   change. Nothing is installed again and `trigger_injection` is not run again. The drop-down asks Rose every
   second and shows "Turning them off...", then "Done: press Reconnect".
3. **A running game is never touched.** With the game still running the request is refused ("close it
   first"): starting the patcher would otherwise hold and restart that game.
4. **An early Reconnect.** A game the client starts while the overlay is being built is held and restarted
   once when the patcher scans, as at the start of a game (the session's restart count is set back for this).
5. **Scope.** The choice lasts for this match: the session's end removes or switches off its mods as always,
   and the next game installs them again. Nothing is deleted or unselected.
6. **Reconnect** stays the user's press.

## Where the code is

- `injection/overlay/reconnect_choice.py`: `ReconnectChoiceMixin` (in `OverlayManager`): `reconnect_mods()`,
  `leave_out_on_reconnect(ids)` for other threads; `_serve_reconnect_screen` runs in `_run_session`'s loop.
- `injection/overlay/overlay_manager.py`: four small edits (the import, the class line, two in `_run_session`).
- `pengu/communication/reconnect_handlers.py`: the `reconnect-mods` message (answer `reconnect-mods-response`:
  `active`, `mods` [{id, name, off}] or null while they are read, `status` "", applying, ready, failed,
  game-running, unknown). Wired into `message_handler.py` (import, class line, one route).
- `Pengu Loader/plugins/ROSE-ReconnectMods`: the button and the drop-down. Its style hides upstream's
  `.rose-stop-injection` button; upstream's code in ROSE-SettingsPanel is untouched.
- Tests: `injection/tests/test_reconnect_choice.py` (a whole fake game session per test).

## Risks

- This changes what the session does in the middle of a match, next to upstream's most delicate code
  (`overlay_manager.py` is too long for the local model, so its four edits are by hand).
- It can only be proven by a real crash and reconnect; tests can cover the list, the leaving-out and the
  messages, not LTK Manager's behaviour on a second run in the same match.

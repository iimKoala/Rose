# Other players' skins: pick what each champion shows on this PC

Asked for on Nov 14: in champ select, a drop-down by each champion picked (not the user's own) to choose a Riot
skin or a custom skin for it, which stands in for the skin that player has on, with a choice to use no skin.

## What the user gets

- A panel in champ select, "Other players' skins" (`Pengu Loader/plugins/ROSE-OtherSkins`): one row per other
  player's champion, teammates first, enemies as soon as champ select shows their pick. It can be dragged and
  folded; both are remembered.
- A row's list: **Their own skin** (Rose changes nothing, the start), **No skin (default look)**, the **skins**
  Rose has a file for, and **your custom skins** of that champion.
- A pick is for one champ select and only changes this PC's picture. Nothing is sent to anyone.
- A pick is for the champion, so it covers every player on it (a champion both teams play has one row). The
  user's own champion has no row. A friend in party mode whose champion has a pick does not get the skin they
  shared: the pick stands in for it.

## Why it is not just "add the skin's mod"

A skin Rose plays is written for slot 0: `skin0.bin`, the base skin. That works for the user's own champion
because Rose puts it on the base skin first. Another player keeps the skin they chose, and for them the game
reads `skin<N>.bin`. Which N is not known for an enemy until the game starts, too late to build mods.

So a pick becomes two mods (`injection/core/other_skins.py`):

1. `other_<champion id>`: the skin's own mod as it is. It covers a player with no skin on (slot 0).
2. `other_<champion id>_slots`: made on the spot (`injection/baseskin/slots.py`). The mod's `skin0.bin`, small,
   under every other skin slot the game has for the champion (its skins and chromas: Ahri has 105): the skin
   entry and its resource list under that slot's names, and a link to the bin they came from for everything
   else. It is how the skins Rose ships are built, with N in place of 0. About 5 KB a slot.

"No skin" is only the second mod, made from the game's own `skin0.bin`. For a skin Rose ships, the slot of that
skin itself is left alone: the copies link the game's file there.

What names a slot inside a skin bin was read from the game's own files (Nov 14): the entry
`Characters/<X>/Skins/Skin<N>`, its `.../Skin<N>/Resources`, the entry's link to that list
(`mResourceResolver`) and one field that repeats the entry's name. Only a name that is the mod's own slot is
changed: a shipped skin keeps the names of the skin it shows.

## How a pick travels

- The panel asks `other-skins-list` (which skins and custom skins a champion can be given, what is picked) and
  sends `other-skin-set` (`pengu/communication/other_skin_handlers.py`). What it sends is checked against what
  Rose offers: a skin id must be one Rose has a file for, a custom skin one of that champion's saved skins.
- The pick is kept in `state.other_skins` and forgotten by the champ select reset.
- It joins friends' skins everywhere they go (`InjectionTrigger.planned_party_skins`): staged during the
  countdown, restaged when it changes, installed by the injection, alone when the user's own champion keeps its
  default skin.

## Not done, not checked

- **Never seen in a game.** Checked: the files are what the game's own `skin<N>.bin` look like (names, entries),
  LTK Manager's own rules (`rose-mod-check`) call the made mods healthy, the staging and the injection install
  the same files, and the panel works on a stand-in page. Not checked: that the game shows the skin, and what
  the patcher's check inside the game makes of it. If that check objects it switches every mod off for the
  game, the user's own skin too. Try it first in a custom game.
- More mods take the patcher longer to build before a game. Nine picks are eighteen mods.
- Chromas and forms are not in the list, only skins. Rift Classic and Swiftplay are left out.
- A custom skin kept as an unpacked WAD folder is not read: it only shows on a player without a skin on.
- A player who changes champion loses the pick within two seconds; one who does it in the last second of champ
  select may keep a mod for a champion nobody plays, which changes nothing.
- Tests: `injection/tests/test_skin_slots.py`, `injection/tests/test_other_skins.py`,
  `pengu/tests/test_other_skin_handlers.py`, two cases in `injection/tests/test_staging.py`, and
  `node --test test/other_skins_ui.test.cjs`.

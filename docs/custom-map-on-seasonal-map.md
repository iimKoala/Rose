# A custom map on the season's map (built Nov 18; never run in a real game yet)

Asked for on Nov 18: "latest league patch put winter map, can you look into custom maps overriding it?" and
"they made the winter map the official standard map, i still want to use custom".

## What happened

- The game's `data/maps/shipping/map11/map11.bin` lists 30 **map skins** of Summoner's Rift (`Default`,
  `Milkshake_SRS`, `URF`, `Arcade`...). The server names the one a game loads; the game's log says which:
  `GameStartInfo ... mapskin = Milkshake_SRS`.
- Each map skin links a **map container** by name (`mMapContainerLink`). `Default` links
  `Maps/MapGeometry/Map11/Base_SRX`, the standard map. `Milkshake_SRS`, Riot's name for the winter map, links
  its own geometry, materials and textures.
- Until patch 16.22 every game of this PC was `mapskin = Default`. Since patch 16.23 (Nov 18, 2026) every
  game is `mapskin = Milkshake_SRS`.
- A custom map replaces the standard map's files (or the textures they use). Under the winter skin the game
  never loads them, so the winter map shows.

## What Rose does

With a custom map selected, Rose adds a small mod made on the spot, `rose_map_force`, right after the map mod
(`injection/core/map_force.py`). It declares an edit of `map11.bin`: each seasonal map skin gets `Default`'s
container as its `mMapContainerLink`. This is what the community's "Map Forcer" mod does (by TheKillerey; its
16.22 version covers four skins, none of them the winter one). LTK Manager applies such an edit when it builds
the overlay: it is declared in the mod's `META/info.json` under `Layers.base.GameData`, and the mod ships an
empty `WAD/Map11.wad.client` as Map Forcer does.

The list is read from the game's own `map11.bin` for each game, so a new season needs no new mod.

**The rule: with a custom map selected, a game on a seasonal skin looks as a game on `Default` does.**

- Re-linked: a skin that is another look of `Default`'s playfield, which means the same objects file
  (`mMapObjectsCFG`) and the same navigation grid. On patch 16.23 these are 11: `Milkshake_SRS`,
  `Milkshake_Swiftplay`, `Worlds_SR_Seasonal`, `Sodapop_SRS`, `Bloom`, `A22`, `SocialSR`, `ContentCapture`,
  `Spectator_Only_Banners`, `Tutorial`, `ULTBOOK`.
- Left alone: a mode with objects or a grid of its own (`URF`, `Arcade`, `Ruby_SR`, `Boba_SRS`, `10Year`...).
- Left alone: a skin whose own map the selected mod replaces (a winter-map mod ships
  `milkshake_srs.mapgeo`: it is made for that skin).
- Nothing is added when the selected mod declares edits of its own (Map Forcer, the winter-rift mods): it
  says itself which map a skin loads.
- A mod with a `map11.bin` of its own replaces the game's, so its skins are read from that file. The two
  Noxus Rift mods link every skin to their map already: nothing to add.

## Where it is hooked

- `InjectionTrigger._run_mod_injection`: after the map mod is put into the injection's mods folder.
- `InjectionTrigger._custom_mod_plan`: a `MapForceStep` after the map's `ModStep`, so the countdown stages the
  same mods the injection installs (`injection/core/stage_plan.py`).

## Not done, not checked

- **Never seen in a game.** Checked: the logic on the real game files and on the user's 12 map mods (7 get the
  forcer, 5 rightly get none), the made mod against the community Map Forcer's form, and LTK Manager's own
  rules on it ("healthy"). Not checked: that LTK Manager applies the edit in a game started through Rose, and
  what the game shows.
- The winter skin changes more than the map: the grass tint, and winter looks for minions, towers and
  monsters. Those stay. Resetting them needs properties whose names are not known.
- Only Summoner's Rift (map 11). ARAM and the other maps have their own files.
- Tests: `injection/tests/test_map_force.py`, three cases in `injection/tests/test_staging.py`.

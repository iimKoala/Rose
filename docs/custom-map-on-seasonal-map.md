# A custom map under the season's map (an experiment: off; on for every game on the developer's PC)

Asked for on Nov 18: "latest league patch put winter map, can you look into custom maps overriding it?" and
"they made the winter map the official standard map, i still want to use custom". After the first try made
the game quit, on Nov 19: "Yes, try it" (the harder way).

## What happened in the game

- The game's `data/maps/shipping/map11/map11.bin` lists 30 **map skins** of Summoner's Rift (`Default`,
  `Milkshake_SRS`, `URF`, `Arcade`...). The server names the one a game loads; the game's log says which:
  `GameStartInfo ... mapskin = Milkshake_SRS`.
- Each map skin links a **map container** by name (`mMapContainerLink`). `Default` links
  `Maps/MapGeometry/Map11/Base_SRX`, the standard map. `Milkshake_SRS`, Riot's name for the winter map, links
  its own.
- Until patch 16.22 every game of this PC was `mapskin = Default`. Since patch 16.23 (Nov 18, 2026) every
  game is `mapskin = Milkshake_SRS`.
- A container is two files: `<name>.mapgeo`, what is drawn, and `<name>.materials.bin`, the materials the
  geometry names plus the container itself with the map's **placed objects** in named groups.
- A custom map replaces the standard map's files, or the textures its materials use. Under the winter skin
  the game does not load them, so the winter map shows.

## First try (Nov 18-19): link the winter skin to the standard container. Dropped.

A mod made on the spot declared an edit of `map11.bin` that gave the winter skin `Default`'s container, the
way the community's "Map Forcer" does.

1. It did nothing in two games. LTK Manager refused the edit: `Game data: Layer declarations refused: missing
   field 'origin'`. The module needs an `origin`; only two of the Map Forcer's three keys had been copied.
2. With the `origin`, LTK Manager applied the edit, and the game quit the moment it spawned the world, in
   every game (`Received StartSpawn packet`, then `SentryHandleException`).

The reason for 2: the winter container's placed objects differ from the standard one's. It has a **train**
(`Characters/SRU_Train`, with the points it moves along) and the **shops** under other names
(`OrderShopAreaLimits1`); 6 groups only winter has, 2 only the standard map has, 15 that point elsewhere. The
server runs a winter game and names those objects. A client that loaded the standard container lacks them.
"The same objects file and navigation grid" was the wrong test for "the same playfield".

## Second try (Nov 19): the winter container stays, the standard map is drawn under it

`injection/core/map_force.py`. Nothing in `map11.bin` is touched. A mod made on the spot, `rose_map_force`,
gives the game, under the **winter** container's file names:

- `milkshake_srs.mapgeo`: the standard map's geometry, the game's own `base_srx.mapgeo` copied as its WAD
  stores it (23 MB, nothing unpacked; the way the original's `skin_sounds.py` copies sound banks);
- `milkshake_srs.materials.bin`: the winter file plus the standard map's materials it lacks. On patch 16.23
  that is 28 of 192: the other 164 are in the winter file already, byte for byte. Entries are moved as
  bytes, so the winter container and all its placed objects are exactly what they were.

Which season is ported: the map skin the newest game log of this PC names, when it has `Default`'s objects
file and navigation grid and another container.

Not ported in this version: a mod that says itself which map loads (declared edits: Map Forcer, the
winter-rift mods; or a `map11.bin` of its own: the two Noxus Rift mods), and a mod that ships map geometry or
materials of its own (Anima Squad). Of the user's 12 maps, 6 get the port.

Expected to look wrong even if it works: winter's decorations (snow, lights, the train) are placed objects,
so they show on the standard map; the grass tint and the winter looks of minions and towers stay.

### Off unless this PC asks, and first only in the Practice Tool

Two versions of the first try went into every game on offline checks alone. This one is made only when the
file `.git/rose-map-port.txt` of this copy says so: `practice` (only for a Practice Tool game) or `on` (for
every game). `.git` is never published and an installed copy has none, so it is off everywhere else.

- To try: the file says `practice`. Start Rose, open a Practice Tool lobby, select a custom map, start.
  Rose's log says `[MAP] A custom map is selected and the game runs Milkshake_SRS: the standard map is drawn
  under it`.
- If the game quits: Rose's reconnect leaves the newest mod out and the game runs. Delete the file.
- Only after a Practice Tool game has shown the custom map: `on`.

### Checked offline, on the real game files

- The made mod: 2 files, 23.4 MB, written in 0.05 s.
- The geometry under the winter name is the standard geometry (same SHA-256, 92 MB unpacked).
- The materials file: 841 winter entries, every one byte for byte, plus 28 added. All 184 materials the
  standard geometry names are defined in it, identical to the standard map's.
- No name that only the winter geometry has is spelled out, or hashed, in winter's placed objects.
- LTK Manager's rules call the packed mod healthy (they read its bin; they do not read the geometry).

**Not checked offline, and only a game can: whether the game loads it, and what it then shows.**

### Seen in a game (Nov 19, 02:12)

The user's Practice Tool game with Hell Rift selected, mode `practice`: "Custom map shows".

- Rose: `[MAP] A custom map is selected and the game runs Milkshake_SRS: the standard map is drawn under it
  (28 material(s) added to the season's; mode practice)`, staged and injected, overlay built in 3.6 s.
- The game ran 19 seconds and was closed by the user. Its log has no error line, and LTK Manager recorded
  "Game ended clean, no incident".

What that shows: the game loads the port and spawns the world, which is where the first way died. What it
does not show: a whole game (minions from 0:30 on, the shop, the drakes changing the terrain, the train
moving, other players), and the five other maps that get the port.

### On for every game on the developer's PC (Nov 21)

Asked on Nov 19 whether to turn it on for all games on this PC, the user answered on Nov 21: "Yes, all
games". `.git/rose-map-port.txt` says `on` there. It is still off everywhere else: the file is not published.
A whole game with it has not been seen yet. If a game quits at its start, Rose's reconnect leaves the newest
mod out and the game runs on the winter map; the file then goes back to `practice` or is deleted.

Tests: `injection/tests/test_map_force.py`, three cases in `injection/tests/test_staging.py`.

# Champ select builds from onetricks.gg (design, Nov 10)

What the user asked for (their words, Nov 10): "in champ select auto build/rune import", builds from
`https://www.onetricks.gg/champions/ranking/<Champion>`, "switch through the top 3. Every time you switch it
shows their build, name, runes. After the enemy locks in it looks for which champion you're likely to vs and a
build/runes against that champion". Import all three: rune page, summoner spells, item set.

## What onetricks.gg publishes (checked in a browser, Nov 10)

Both pages are ordinary public pages with their data embedded as JSON in `<script id="__NEXT_DATA__">`
(`props.pageProps`). `robots.txt` allows `/champions/` and `/players/` and disallows `/api/`: Rose reads only the
two page kinds below, never `/api/`.

**Ranking page** `/champions/ranking/<Champion>` → `rankings.S2026_1.mainsData`: a list already in rank order
(374 players for Talon). Per player: `player` (name #tag), `region`, `tier`, `lp`, `puuid`, `mainGames`,
`winrate`, `mainPositions` (`{top, jungle, mid, bot, supp}` game counts), `rune` (keystone id), `runeStyle`
("secondary tree id,keystone id"), `sumSpell` ("11,4"), `boots`, `startItem`, `firstItem`, `path` (three core
item ids), `skill` ("W-Q").
Lookup tables on the same page: `runes`, `itemData`, `summonerSpells`, `championKeys` (id → name).

**Player page** `/players/<puuid>` → `games.<championId>`:
- `matchHistory` (40 games): `p` (patch), `gameRoles` (`playerRole`, `enemyChampion` id),
  `details.playerData.stats` (`item0..item6`, `perk0` keystone, `perkSubStyle`, `win`),
  `details.playerData.spell1Id/spell2Id`, `timeline.orderedItems`.
- `firstItemStats.<patch or "all">.<first item id or "top">`: `popularItems`, `boots`, `startingItems`,
  `skillPaths`, and `popRunes`: `{keystone id: [[[six rune ids], share of games, [primary tree, secondary tree,
  keystone]], ...]}`. This is where the full rune set comes from. The page also shows three stat shards; their
  field is still to be found.
- The page has filters `season`, `role`, `matchup` (how they go in the address is still to be found).

## Design

1. **Who.** Top 3 of the ranking list. When League gives an assigned lane, only players who mostly play that
   lane count (Talon's #1 is a jungler: his runes and Smite are wrong for mid). Since Nov 16 (the user: "the
   build should find the top players for that specific lane on that champion. defaults to main lane if there
   are no players for that lane"): when that lane has fewer than three such players, or no lane is known, the
   list goes on with the best players of the champion's own main lane (the lane it is played in most), and
   only then with the rest (`onetricks.by_lane`). Before, it went on with the next players of any lane.
2. **What is shown.** A small panel in champ select: player name, rank and region, keystone and runes, spells,
   start items, core items, skill order, and arrows to switch between the 3. Nothing is imported until the
   user presses the panel's **Import** button (the user after the first live test, Nov 11: "it shouldn't just
   auto import. should be a clickable button"); stepping to another player or opponent brings the button back.
   The panel is dragged by its title bar and remembers its place (the user, Nov 11: "window should be draggable").
   The Runes row is in rune-page order: the keystone first, the main tree's three, the second tree's two, the
   shards (`build_import.page_order`). The site lists the six runes by number, and drawn that way the keystone
   sat wherever its number fell (the user, Nov 14: "sometimes the keystone doesnt show").
3. **What is imported**, through the League client's own local API, as other build tools do:
   rune page (one page Rose owns and overwrites, named after the player), summoner spells (Flash stays on the
   key it is on now), an item set for the in-game shop.
4. **Matchup** (the user, Nov 10: "Guess on who's most likely, but can click through (clickable arrows) in
   case someone else is in that lane. You can skip matchups that don't make sense (e.g. vs Braum top)").
   Once enemies lock in, Rose guesses the lane opponent and shows "vs <champion>" with its own arrows to step
   through the other enemies. An enemy makes sense in the user's lane when at least 5% of that champion's
   ranked mains' games are in that lane (from the enemy champion's own ranking page: Braum is 99% support, so
   "vs Braum top" is skipped); the likeliest is the one with the biggest share. With no lane known, all five
   enemies can be stepped through. The build against the chosen enemy is the same player's page with
   `?matchup=<ChampionName>` (their games against that champion only, up to 40); with no such game the panel
   says so and keeps the general build.
5. **Polite reading.** One ranking page per champion and at most 3 player pages, only when the user locks a
   champion; kept for the Rose session; no personal details are sent; on any failure the panel says so and
   nothing is changed.

## Found on Nov 11 (tested with plain `requests`; each page answers in under a second)

- Stat shards: `firstItemStats.all.all.popStat` (three ids, top row to bottom row). The same block has
  `popKeystone`, `popRunes`, `sSpells`, `startingItems`, `popCore`, `popClassicPath` (full item paths), `boots`,
  `popularItems`, `maxSkillOrders`.
- Matchup: `/players/<puuid>?matchup=Graves` (the site's champion name; an id gives 404) returns only the
  games against that champion with the same blocks. `?role=jungle` also works on player pages. The ranking
  page ignores both (it filters in the browser), so Rose filters the list itself by `mainPositions` and by
  region (the page's default "Major" tab: KR, EUW1, NA1).
- The reader is `main/onetricks.py` (Continue created it from Claude's tested code): `page_props`,
  `top_players`, `lane_shares`, `likely_opponents`, `player_build`, `champion_key`.

## The League client's side (from the community schema of its local API, and names found in LeagueClient.exe)

- Rune pages: `GET /lol-perks/v1/pages` (each: `id`, `name`, `isEditable`, `isDeletable`, `current`,
  `primaryStyleId`, `subStyleId`, `selectedPerkIds`), `POST /lol-perks/v1/pages`, `PUT` and `DELETE
  /lol-perks/v1/pages/{id}`, `PUT /lol-perks/v1/currentpage` (the page id), `GET /lol-perks/v1/inventory`
  (`ownedPageCount`), `GET /lol-perks/v1/styles` (each tree's `slots[].perks`: the order `selectedPerkIds`
  needs, since the site gives the six runes unordered).
- Item sets: `GET` and `PUT /lol-item-sets/v1/item-sets/{summonerId}/sets` (`itemSets[]`: `title`, `uid`,
  `associatedChampions`, `associatedMaps`, `blocks[] {type, items[] {id, count}}`, `map`, `mode`, `type`,
  `sortrank`, `startedFrom`, `preferredItemSlots`). PUT replaces the whole list: keep the user's own sets.
- Spells: `PATCH /lol-champ-select/v1/session/my-selection` with `spell1Id`, `spell2Id`.

## Changes after the user's games (Nov 13)

The user: "auto import should have a button for each, rune, summoner spells, and build. the ingame build should
include optional items ... include items like if you need armour, damage, magic resist, that the top players
are taking".

- **Three import buttons** (Runes, Spells, Items). Each imports only its part; what was imported stays listed,
  and its button is ticked, until another build comes on screen. The `builds-get` message's `import` is now the
  list of parts; nothing is imported without one.
- **Situational items.** What the three players build beyond the build's own items (their item shares added
  up, the most built first, four per need), grouped by what the League client's item data says the item gives:
  armour (`Armor`), magic resist (`SpellBlock`), damage (`Damage`, `SpellDamage`; an item that gives armour or
  magic resist is not repeated there). Shown as three rows on the panel and as three blocks in the shop's item
  set ("If you need armour", "If you need magic resist", "More damage").
- **The in-game strip** goes on, after the core build, with the chosen player's other usual items.

## Changes on Nov 14 (the user's requests while playing)
- **Other builds** ("there should be another arrow for other builds ... clicking the arrow for these builds
  override the runes based on matchup"). The site splits a player's games by the first item built:
  `firstItemStats.all.<item id>` has the same fields as `firstItemStats.all.all` (the other keys are `all`,
  `top`, which names the most built first item, and pairs of items). `onetricks.player_builds` reads one build
  per first item that started at least a tenth of the player's games, the most played first; its share is the
  sum of its `popKeystone` shares. The panel gets a third pair of arrows: "Automatic build" (the usual or
  matchup build, as before), then each of those. A picked build stands in for the matchup's (Rose's note says
  so) and is imported under the player's name alone. Picking another player or opponent goes back to
  automatic. A player with a single build by first item gets no arrows: it is the usual build again.
- **Role buttons** ("an option to choose role, incase of swap or something"). Five buttons at the top of the
  panel; champ select's own role is marked. A picked role is sent to Rose in place of champ select's, stays
  through a champion trade, and ends with the champ select. Rose's side needed no change.
- **Skill order in the shop** ("level 1 - 3 qwe. max skill order wqe"). The shop shows an item set's block
  titles, so the first three skill points (`earlySkillPaths`, most used; `skillSlot` counts from 1) go on the
  Start block's title and the max order on the build block's: "Start (levels 1-3: W Q E)", "Build in this
  order (max W > Q > E)".

- **A player's page is about one champion** (the user's Jayce jungle game: "Jeykup #xie has no recent games
  on this champion", though he tops Jayce's jungle list). `/players/<puuid>` carries `games` for ONE champion,
  the player's most played (`championKey`); the ranking page links to the others as `/players/<puuid>#Jayce`,
  a part of the address a page request does not send, and no address parameter changes it (tried: champion,
  championKey, champ, championId, key). The page does hold a short summary of the other champions
  (`profiles.<season>.championMains.<id>.build`: keystone, items, spells per game) but not the six runes, so
  no rune page can be made from it. So `_players` passes such a player over and shows the next ones whose
  page has a build, reading at most `PAGES_TRIED` pages; the panel's note names who is not shown. On Jayce
  jungle that is three of the list's first four.

## Build steps (all written Nov 11; step 5 is the user's)

1. Reader: `main/onetricks.py`.
2. Import: `main/build_import.py` (tested on a fake League client).
3. Choice of players, opponent and build: `main/build_service.py`; the `builds-get` message:
   `pengu/communication/build_handlers.py`, wired into `message_handler.py` (by hand: that file is too big
   for the local model).
4. The panel: `Pengu Loader/plugins/ROSE-Builds` (tested on a fake client; never run in the real client yet).
5. Live test by the user: step 6 of `docs/home-test-checklist.md`. Unknowns until then: where the panel
   sits, whether the client's icon paths show, and whether the client takes the rune page and item set as sent.

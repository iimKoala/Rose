# Player stats panel, Ctrl+X in game (built Nov 14; never run in a real game yet)

What the user asked for (their words, Nov 14): "the next feature is like porofessor. a hotkey thatll show
stats of teamates and enemies in order of their position/role. shows their rank, winrate etc... i'd preferr
if it took the stats from deeplol na". Their choices when asked: stats from "Client + deeplol", hotkey
"ctrl + x".

## What it does

Ctrl+X in a game shows a panel over the top of the screen: your team on the left, the enemy team on the
right, each from top to support. For each player: champion, name, solo queue rank and LP (in the tier's
colour), the season's win rate and games (green from 55%, red up to 45%), the season's peak, and the ladder
position for the players deeplol has one for (the top of the ladder).

A tap on Ctrl+X opens it and the next tap closes it; holding the keys shows it only while they are held.
It hides while another window is in front. Like the strip and the gold board it lets the mouse through and
never takes the keyboard.

## Where the numbers come from

Checked in a real ranked game (Nov 14), field names only:

- **The League client**, the moment the game starts (the loading screen): `/lol-gameflow/v1/session` lists
  both teams with every player's `puuid`, `championId` and `selectedPosition`; `/lol-ranked/v1/ranked-stats/
  {puuid}` gives tier, division, LP, wins and the season's highest tier; `/lol-summoner/v2/summoners/puuid/
  {puuid}` the name and tag. All ten players took 1.8 s.
- **The client hides the other players' losses**: `losses` was 0 for all nine others and right only for the
  user's own account. A win rate from the client alone would read 100% for everybody.
- **deeplol.gg** fills that in. Its pages hold no data; everything comes from the data service the site
  itself asks (`b2c-api-cdn.deeplol.gg`: `summoner/summoner`, then `summoner/summoner-realtime`). That is not
  an official API, so it can change or stop answering. It gave wins and losses, the peak with its LP
  ("PLATINUM I", 34) and, for the top of the ladder only, the ladder position (it answers -1 for a Platinum
  player). Nine players took 3.9 s, five at a time.
- **The user's own account is never sent to deeplol**: its record comes from the client, which has it whole.
- A player deeplol doesn't know shows the rank and "35 wins" (no rate) from the client.
- **The win rate on the champion being played** (the user, Nov 14: "Should also show winrate on current
  playing champ"). deeplol's own Champions tab asks `summoner/champion-stat?puu_id&season&platform_id`
  (the season's number from `common/season-list`, asked once). The answer is large, 2 MB unpacked for a
  player with 1,400 games and 266 KB on the wire, because it also holds the record against every enemy
  champion. Only one entry is used:
  `counter_champion_stats.ranked_solo_5x5.enemy_champion_stats.All[]` with the champion's `champion_id`
  (`wins`, `losses`; the entry with id 0 is all champions). A player with no entry has no solo queue game
  on the champion this season, and the card says "no games". It is a third question per player (about 1.5 s
  each, five at a time).
- **The user's own champion record** is not a season's: the account is never sent to deeplol, so the card
  counts the solo and flex games on the champion among the 20 games the client's match history lists
  (`/lol-match-history/v1/products/lol/current-summoner/matches`) and says "3 recent".

- **Streamer mode** (the user, Nov 14: "their slot should be filled still, but blank with streamer mode note
  inside"). The client leaves a player who hides their name off `teamOne`/`teamTwo` and names them only in
  `playerChampionSelections` (a real ranked game listed four players on one team). Their account id is in
  that list, and for a few hours on Nov 14 Rose looked them up with it and showed their name and rank after
  all. Now such a player is marked `hidden`: the slot is theirs (on the shorter team, in its one open role),
  with the champion and the role, and nothing is asked about them, from the client or from deeplol. A listed
  player with no account id and no name is hidden the same way; a bot has a name. The user's own account is
  never hidden from the user.

## The look (Nov 14: "Style same way as account switcher")

A card a player, as the account window's cards (`main/account_web/style.css`): the same colours, the rank's
emblem from `main/account_web/emblems`, the tier in gold in the Beaufort title font (loaded for this program
only with `AddFontResourceEx`, nothing is installed), the LP with a thin gold bar (LP out of 100, full from
Master up), role and level as small badges. The right side of a card has two records: SEASON, and the
champion's name. A rate is teal from 55%, red to 45%, and plain for fewer than five games. The user's own
card has a gold edge. The panel is 1016 x 468 at the top of the screen.

## How

- `main/player_stats.py` (in Rose, started in a thread of its own by `game_build.start_overlay`): reads the
  client, saves `state/build_guide/player_stats.json` at once, asks deeplol, saves again.
- `main/deeplol.py`: the three questions per player and what is taken from the answers.
- `main/stats_panel.py` (in the strip's program): the window, the Ctrl+X tap/hold logic (`Hotkey`), the
  texts. It reads the saved file again when it changes, so deeplol's part appears without a key press.
- Tests (scratch, no window, no network): the lookup with a fake client and a fake deeplol; the panel's keys,
  texts and drawing.
- The panel is fully solid (Nov 14). Its window is "layered" so that clicks pass through it, and Windows
  draws a layered window only after `SetLayeredWindowAttributes`. Tk made that call itself while the panel
  had an `-alpha`; when the `-alpha` was removed the panel stopped appearing, in two games, until the call
  was added by hand. `test/test_stats_panel.py` guards it (the window is made, never shown).

## Not checked, and risks

- Never seen on screen in a game: the tests draw into a window that is never shown.
- Ctrl+X while the game is in front also reaches the game; League has no default action on it.
- ARAM and other modes without roles list the players in the client's order. Bots have no account and show
  as unranked.
- If deeplol changes its service, the others' win rates and peaks go missing until `main/deeplol.py` is
  updated; ranks keep working.

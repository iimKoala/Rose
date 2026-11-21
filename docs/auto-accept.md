# Auto accept

Asked for on Nov 21: "in league client add a plugin for auto accept, also a setting to turn on and off".

## What it does

`Pengu Loader/plugins/ROSE-AutoAccept` (written by the local Continue model from a brief, reviewed and tested
by Claude):

- **The setting** is a check mark button in the client's top bar, built like the account switcher's buttons.
  Grey is off, gold is on. A press flips it, and the choice is kept in the client's `localStorage`
  (`rose-auto-accept`), so it survives a restart. It is **off until the user turns it on**: a plugin that
  arrives with an update must not start accepting matches for someone who never asked.
- **While on**, once a second, it asks the client for its phase (`GET /lol-gameflow/v1/gameflow-phase`). Only
  in `ReadyCheck` it asks for the ready check (`GET /lol-matchmaking/v1/ready-check`), and when that says
  `state: InProgress` and `playerResponse: None`, it accepts (`POST .../ready-check/accept`): the call the
  original's own auto accept addon makes.
- **One accept per match found.** An accept the client refuses is tried again at the next look. A match the
  user declined is left alone.
- While off it asks the client nothing.

Why the phase is asked first: outside a ready check the ready check's address answers 404, and one 404 a
second would fill the client's log. The phase always answers.

Nothing here touches Rose's Python side or the original's files.

## Not in it

- No wait before accepting, no sound, no hiding of the window. It accepts as soon as it sees the match.
- The original ships its own auto accept inside its `ROSE-Jade` plugin (`config/js/addons/AA.js`), which is
  switched off there (`index.js_`) and loads a settings library from the internet. It is left as it is.

## Checked, and not

- `test/auto_accept.test.cjs` runs the plugin's own file against a stand-in page, storage and client: off
  asks nothing; outside a ready check only the phase is asked; a match is accepted once and the next one
  again; a refused accept is retried; a declined match is left alone; the button shows and flips the state.
- **Not checked: the real client.** The button's shape and place are the account switcher's, which work
  there. Whether the check mark sits well in the bar, and one real match found, are still to be seen.

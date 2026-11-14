# Party mode: friends' custom skins arrive by themselves

Asked for on Nov 14: two people connected with the party code, yet neither saw the other's skins in game.
Wanted: the custom skins the party uses are downloaded automatically, champ select shows each member's mod
with a way to switch off the ones you don't want, and the game does not start before the mods are there.

## What was wrong

- The original party mode shares a custom mod's **hash only** ("Mod files never leave the PC",
  `party/discovery/custom_mods.py`). A friend sees the mod when they happen to have the same file; else
  they see the official skin, or nothing when the mod sits on the default skin.
- Party mode talks through a relay (a Cloudflare Worker, `relay-worker/`). Its address is in a file the
  original keeps out of git (`party/network/relay_config.py`). Run from source there is none, and the panel
  says "no party server is configured in this build". This version needs a relay of its own; its address
  goes into that file (added to git here with `git add -f`) once the relay is deployed.

## How it works now

- **One member to one other, through the relay.** `relay-worker/src/room.ts` passes on two new things and
  keeps nothing of them: a `to` message (`{type:"to", to:<summoner id>, data}` arrives as
  `{type:"from", from, data}`), and binary frames whose first 8 bytes name the receiver (the receiver gets
  the sender's id there). Only joined members can send, and only to a member of the same room.
  `PartyRelay.send_to` / `send_binary_to` and `set_direct_callbacks` are the client side.
- **Asking and sending** (`party/network/mod_transfer.py`): `mod-want` with the hash, `mod-start` with the
  size, then pieces of 256 KiB (`RMOD` + 8 bytes of the hash + the piece's number), then `mod-end`.
  60 MB took 4.6 s on a relay running on the same PC; on the internet the sender's upload speed decides.
- **What a member announces** (`ModSharing.announce`): the pick's state gains `custom_mod_size`,
  `custom_mod_ext` and `custom_mod_name`, for a mod that is one file of at most 600 MB. A mod kept as a
  folder is announced as before and cannot be sent.
- **Fetching** (`ModSharing.fetch_missing`, on every change of the room's members): for each friend with a
  custom mod, look for a copy (`find_local_mod`); when there is none, ask that friend for the file.
- **Where received files go**: `%LOCALAPPDATA%\Rose\mods\party-received\<content hash><suffix>`. They are
  not the user's own mods and no mod list shows them. `find_local_mod` looks there first, so a received
  file is used exactly like "our copy of a friend's mod" was before.
- **The panel** (`ROSE-PartyMode`): a friend's row says "Custom skin: <name> (ready / downloading 43% /
  asking your friend for it... / could not be fetched ...)" and has a **Skin on / Skin off** switch
  (`party-peer-skin-off` -> `PartyManager.set_peer_skin_off`). Off means: this friend's skin is not applied
  on this PC and their mod is not fetched. They stay in the party and are not told.
- **The wait** (`PartyInjectionHook.prepare_party_mods`): the injection waits up to 15 s for files still on
  their way (they usually arrive during champ select; a file that got no piece for 20 s no longer counts).
  If the game starts meanwhile, Rose's existing hold of an early game takes over.

## What keeps it safe

- An owner sends only a file whose hash it announced as its own pick; nothing else can be asked for.
- A receiver takes only pieces of a file it asked for, from the member it asked and through the room it
  asked in (the same member id in another room is someone else), in order, up to the size announced. The
  finished file must have the announced content hash or it is deleted.
- The folder of received files never grows past 3 GB (five mods of the largest size): before a file is
  asked for, leftovers of broken downloads are deleted, then the oldest files. One member has one file on
  its way at a time, so a member who keeps changing their pick fills nothing. Both came from the automatic
  security review of the first commit.
- Hashes are hex strings; suffixes are `.fantome`, `.zip`, `.modpkg`; names never become paths.
- The relay refuses binary frames over 1 MiB and passes nothing to anyone but the receiver.

## Not done, not checked

- **The relay is not deployed yet**: it needs a sign-in to Cloudflare on the developer's PC. Everything
  here was tested on a relay running locally (`wrangler dev`) with two of Rose's own party clients, and in
  unit tests with a stand-in room.
- Never run in a real champ select or game. The 15 s wait before a game is a guess.
- Both PCs need this version: an older Rose does not announce the size, so nothing is asked of it.
- Received files are not run through Rose's mod checker. The folder is only cleaned when it is full.
- Nothing limits how often a member can make the party fetch a new file. A party is the people given the
  code; a friend's skin can be switched off.
- Only the skin a friend plays with is shared. Map, font and announcer mods are each player's own.
- A friend who paid for a mod sends it to the party like any other. Switch a friend's skin off, or do not
  play a paid mod in a party, where that is not wanted.
- Tests: `party/tests/test_mod_sharing.py`, `pengu/tests/test_party_mod_handlers.py`, and two cases added
  to `test/party_ui_reconnect.test.cjs` (`node --test`).

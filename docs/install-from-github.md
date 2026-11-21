# Installing this Rose on another PC, with updates from GitHub

Asked for on Nov 14: an installer for this version of Rose that can be sent to someone else, with every later
change reaching that PC by itself, through GitHub. The repository is public by the developer's choice.

## Why not a normal Rose.exe installer

The original project builds `Rose.exe` with PyInstaller and an Inno Setup installer, and its updater reads
GitHub releases. This version's account window, mod store and in-game panels are separate Python programs
(`python -c ...` from `main/account_gui.py` and `main/game_build.py`), which exist only when Rose runs from
its source. In a built `Rose.exe` they do not start. So the other PC runs Rose from source too, as the
developer's PC does.

## How it works

- **The repository**: github.com/iimKoala/Rose, public, a fork of the original. Its `release` branch is what
  other PCs follow: every publish to it is a version, and nothing is built. The fork's `main` stays a copy of
  the original project's.
- **`scripts/Install-Rose.bat`** (the one file to send, also attached to the `tools` release): makes sure
  Python 3.11+ is there (installs Python 3.13 with winget when there is none), downloads
  `scripts/rose_update.py` and runs it with `--install`.
- **`scripts/rose_update.py`** (standard library only):
  - asks GitHub for the newest commit id of `release` (one small request);
  - when it differs from the copy's `.rose-version`, downloads GitHub's zip of that commit and puts it in
    place file by file: only files that differ are written, and files of the last update that are gone are
    removed (`.rose-files` lists them);
  - makes Rose's own Python environment (`.venv`) and installs the packages of `requirements.txt` and
    `requirements-run.txt`, each without its "Build requirements" part, again only when that list changed
    (`.rose-packages`);
  - downloads once the programs that are not in the source: `Pengu Loader.exe`, `LeagueToolFlop.dll`,
    `ltk_launcher.exe` and `rose-mod-check.exe` (built from `vendor/` and `native/`), as `rose-tools.zip` of
    the `tools` release;
  - on install, puts a "Rose" shortcut on the Desktop.
- **`Start Rose.bat`** (what the shortcut starts): asks for administrator rights as Rose needs, closes an
  original `Rose.exe` that is running, runs the updater, then `main.py`.
- The copy lives in `%LOCALAPPDATA%\Programs\Rose`. Accounts, mods and settings are in `%LOCALAPPDATA%\Rose`
  as always, and no update touches them.

## Updates while Rose runs (Nov 19)

Asked for on Nov 19: "setup auto update for anyone that has my version of rose downloaded? downloads any
pushed updates, and notifies after a game/if user is not a game/champ select".

Before, a copy was brought up to date only when it started, so a Rose left open for days never saw a new
version. Now (`main/self_update.py`, for installed copies only):

- **Every 30 minutes** (first after 5) Rose asks GitHub for the newest commit id of `release`: the same one
  small request the start makes. GitHub allows 60 an hour.
- **A new version is downloaded, not installed** (`rose_update.stage`): Rose is running from the files it would
  replace. The zip waits as `.rose-update.zip` with its version in `.rose-update-version`. A download that is
  not a whole zip is not kept.
- **One question a version, when the user is free**: a Yes/No window, "A new version of Rose was downloaded.
  Restart Rose now to install it?". Free means the client's phase is none of Matchmaking, ReadyCheck,
  ChampSelect, GameStart, InProgress, Reconnect, WaitingForStats, PreEndOfGame: so it comes after the game, or
  at once when nothing is on. A version that arrives during a game waits for its end.
- **Yes**: Rose writes the note `.rose-restart` and quits as from the tray. `Start Rose.bat` sees the note,
  runs the updater (which installs the waiting zip without downloading it again) and starts Rose again in the
  same window. A game found while the question stood open is not interrupted.
- **No**: Rose runs on. The next start installs the waiting zip, also without internet.

`Start Rose.bat` is replaced by the updater while cmd is running it, and cmd reads on from where it was. So
every line up to the one that starts Rose stays byte for byte; the new lines are below it (a test pins this).
The first start after this version is published already uses them.

Nothing of this runs in a developer's copy (`.git`) or in a built `Rose.exe`. Whatever fails (no internet,
GitHub's limit, a broken download) is logged and waits for the next look; it never stops Rose.

Tests: `test/test_self_update.py` (the watcher; the updater, the question and Rose's state are stand-ins),
`WhileRoseRunsTests` in `test/test_rose_update.py`. Checked for real: the download step against GitHub in a
scratch folder (10.8 MB in 2.8 s), and the start script's own lines with stand-in programs (updater, Rose,
note, updater, Rose). Not checked: the window and the restart on an installed copy.

## Publishing, and what never leaves the developer's PC

`python scripts/publish.py` is the only way this version is published.

- **One commit, not the history.** It makes one new commit holding the files of the local HEAD, on top of
  what was published before (the first time: on top of the original project's history), and pushes only
  that. The local history, with every old version of every file and every commit message, stays local.
  After a merge of the original, that one commit also names the original's newest commit as a parent
  (`public_parents`): those commits are the original's and public already, and without them GitHub keeps
  counting the `release` branch as behind the original.
- **A check before every publish.** Every file of that commit and its message are searched for the PC's
  private values: the Windows user name, the computer's name, the email addresses of the local commits, the
  names, logins, tags and notes of the accounts saved in the account switcher, and the lines of
  `.git/rose-private.txt`. Also for things shaped like keys and tokens. One hit and nothing is published. A
  hit is told by its kind and its place, never by its value. `--check` runs the check alone.
- **Accounts are local.** The account switcher's list is `%LOCALAPPDATA%\Rose\accounts\accounts.json` and
  its passwords are in Windows Credential Manager, both per Windows user and outside this folder. The
  repository holds only the made-up accounts of the account window's preview (`main/account_web/fake-data.js`).
  A new install starts with an empty list.
- **Built programs carry folder names.** A Rust build writes the paths of its sources into the program, and
  those start with the builder's user folder. `rose-mod-check.exe` was in git with them until Nov 14. It is
  no longer in git; it is built with `RUSTFLAGS=--remap-path-prefix=<user folder>=C:\Users\builder` and
  shipped in `rose-tools.zip`, which is searched the same way before it is uploaded.
- The repository's address shows the developer's GitHub name. Nothing can hide that in a public repository.

## Rules the updater keeps

- A developer's copy (a folder with `.git`) is never updated or changed by the script.
- An update that fails (no internet, GitHub's limit of 60 version questions an hour, a failed download)
  never keeps Rose from starting: it starts as it is and tries again next time.
- `Pengu Loader/datastore` and `Pengu Loader/config` are the plugins' own settings on that PC: written
  once, never replaced.
- A zip can only write inside Rose's folder (names with `..`, a drive or a leading slash are refused).
- Tests: `test/test_rose_update.py` (GitHub and the commands are faked), `test/test_publish.py` (made-up
  private values).

## Not covered

- League of Legends and LTK Manager must be installed on the other PC; Rose says so when LTK Manager is
  missing.
- If the original Rose is installed there too, it shares the same settings folder. The two must not run at
  once; `Start Rose.bat` closes a running `Rose.exe`, but the original's start with Windows should be
  switched off.
- `rose-tools.zip` holds `LeagueToolFlop.dll` and `ltk_launcher.exe` as they came with the original 1.5.2
  install, older than this source; building the current ones needs Visual Studio's compiler
  (`scripts/build_ltf.py`).
- shortcut: `Start Rose.bat` is replaced by an update only when it changed, and Windows reads a running
  .bat as it goes, so an update that changes this one file can make that one start misbehave. Keep it small
  and stable; put new start logic in `scripts/rose_update.py`.

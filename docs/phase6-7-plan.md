# ROSE-AccountSwitcher: Phase 6 (keep it safe) and Phase 7 (mod store)

Written Nov 8, after Phase 5. Phase 6 is small Continue prompts, run the same way as Phases 4 and 5 (one per
chat, Agent mode, check, commit). Phase 7 needs one decision from you first (see "Decide before Phase 7").

## What's already done (Nov 8)

- Backup: `Documents\Rose backup\rose-accountswitcher-<date>.bundle` (every commit, in OneDrive) and
  `uncommitted-login-fixes.patch`. Restore with `git clone <bundle> Rose`.
- Rose's update check is off (`launcher/core/launcher.py`, `UPDATE_CHECK_ENABLED = False`), so it never offers
  the official installer, whose `robocopy /MIR` would delete this code.
- Rose 1.5.5 and later fixes are merged in from GitHub (commit `dcf9dd4a`).

Still open from Phase 4: the switch fixes in `main/account_login.py` (wrong account after "stay signed in",
"unknown player" / "unexpected error") are uncommitted until they're tested with a real switch.

## Phase 6: Keep it safe (Agent)

Two things can still lose this work: starting the installed `Rose.exe` (it's the old 1.5.3 build, with the
update prompt still on) and uninstalling Rose (it deletes `_internal` and `%LOCALAPPDATA%\Rose`). Phase 6 adds
a safe way to start Rose, one-click backups, and updates through git.

Steps 57, 59 and 61 create new files: run them with the Write tool allowed.

### 57. Backup script

```
In Rose source, create scripts/backup_rose.ps1. It saves a backup to the "Rose backup" folder in the user's Documents ([Environment]::GetFolderPath('MyDocuments')), creating it if needed: 1) git bundle create rose-accountswitcher-<yyyy-MM-dd_HHmm>.bundle --all from the Rose source folder (the folder above the script), then git bundle verify it, and delete older rose-accountswitcher-*.bundle files so only the newest 3 stay; 2) git diff > uncommitted-changes.patch; 3) a copy of $env:LOCALAPPDATA\Rose\accounts\accounts.json as accounts.json, if it exists. Print one line per saved file. Stop with an error message if git or the verify fails. Never copy anything else from AppData. Change nothing else. Stop there.
```

### 58. "Back up my Rose" in the tray

```
In Rose source, utils/integration/tray_manager.py: add a tray menu item "Back up my Rose" right below "Account Switcher". It runs scripts/backup_rose.ps1 with powershell -NoProfile -ExecutionPolicy Bypass -File on a background thread (never on the tray thread), then shows self.icon.notify with "Backup saved to Documents\Rose backup" or "Backup failed, see the Rose log" and logs the script's output. Change nothing else. Stop there.
```

### 59. Start Rose from source

```
In Rose source, create scripts/start_rose.ps1: if it isn't running as administrator, start itself again elevated (Start-Process powershell -Verb RunAs with the same -File) and exit; otherwise Set-Location to the Rose source folder (the folder above the script) and run .venv\Scripts\python.exe main.py. Change nothing else. Stop there.
```

Then (not Continue): a desktop shortcut "Rose (my build)" to `powershell -NoProfile -ExecutionPolicy Bypass -File
"...\scripts\start_rose.ps1"` with Rose's icon. Stop using the Start-menu "Rose" shortcut, which starts the
old installed `Rose.exe`.

### 60. Rose icon on the account window

```
In Rose source, main/account_gui.py: give the account window and the Add/Edit dialog Rose's icon with iconbitmap(str(get_asset_path("icon.ico"))). A CTkToplevel sets its own icon 200 ms after it opens, so call it with self.window.after(250, ...) (and dialog.after(250, ...)). Change nothing else. Stop there.
```

### 61. Update script

```
In Rose source, create scripts/update_rose.ps1: 1) run scripts/backup_rose.ps1 first and stop if it fails; 2) git fetch origin; 3) print the new commits (git log --oneline HEAD..origin/main) and stop if there are none; 4) stop if git status --porcelain shows changes other than "Pengu Loader/datastore", telling the user to commit first; 5) check for conflicts without touching files: git merge-tree --write-tree HEAD origin/main; if it reports conflicts, print the conflicting files and stop without merging; 6) otherwise git merge --no-ff origin/main -m "merge: Rose from GitHub"; 7) .venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-run.txt; 8) .venv\Scripts\python.exe -m compileall -q -x "\.venv" . and .venv\Scripts\python.exe -m unittest discover -s test -t .; print PASSED or FAILED. If anything after the merge fails, print how to undo it: git reset --hard ORIG_HEAD. Never run that undo itself. Change nothing else. Stop there.
```

### 62. Check GitHub from the tray

```
In Rose source, utils/integration/tray_manager.py: add two tray items below "Back up my Rose". "Check Rose GitHub for updates" runs git fetch origin and git rev-list --count HEAD..origin/main in the Rose source folder on a background thread and shows self.icon.notify with "Rose is up to date" or "<n> new Rose commits on GitHub". "Update Rose from GitHub" opens scripts/update_rose.ps1 in a new visible PowerShell window (so you see what it does) with -NoExit. Change nothing else. Stop there.
```

Check after Phase 6: the tray shows Back up my Rose, Check Rose GitHub for updates, and Update Rose from GitHub;
a backup lands in Documents\Rose backup; the desktop shortcut starts Rose (with the admin prompt).

## Phase 7: Mod store (plan)

> **Decided Nov 8: plan A** (RuneForge's own pages inside Rose). The detailed plan is in
> `docs/phase7-mod-store-plan.md`; the options below are kept for reference.

Goal: a store inside Rose for RuneForge mods with RuneForge's filters, each mod's description, one-click
install, update checks for installed mods, and LTK Manager's "needs fixing" check.

### What exists to build on

- Rose 1.5.5 imports `.zip`, `.fantome` and `.modpkg` mods (`ModStorageService.import_mod_file` for champion
  skins, `import_category_mod_file` for maps, fonts, announcer, HUD/UI, voice-over, loading screens, VFX, SFX,
  others) and then has LTK Manager check and repair each one (`OverlayManager.check_mod`, run from
  `MessageHandler._check_imported_mods`). The store's installs go through that same path, so "needs fixing"
  comes from LTK Manager itself: healthy / repairable (repaired once) / unrepairable.
- RuneForge's categories match Rose's: Skins, Maps, HUD & UI, Sounds (SFX, announcer, voice-over), VFX, Fonts,
  Loading screens.
- RuneForge's filters on runeforge.dev/mods: search, category, champion, sort (recently updated, trending
  this week / all time, new this week, most downloads), Gilded picks.
- A mod page has description, author, version (release tag), status ("Working"), published/updated dates,
  license and downloads. Releases have a version tag and the file (.fantome or .modpkg).

### What RuneForge allows (checked Nov 8)

- RuneForge has API tokens (runeforge.dev/user-settings/api-tokens) with a `catalog:read` scope, "reading the
  public mod catalog". The API is under `https://runeforge.dev/api/v1` with `Authorization: Bearer <token>`.
  The catalog routes are documented in a RuneForge repo that isn't public, so they aren't known yet.
- robots.txt allows the `/mods` pages, asks for 1 s between requests, and refuses automated downloads
  (`/mods/*/releases/*/artifacts/`). Downloads work through links the site signs for 15 minutes when you
  press Install, which RuneForge sends to a mod manager as `ltk://install?url=...`.
- Mod pages ask people to share the page link, not the file. Each mod has its own licence.

So: no scraping of downloads, no re-hosting files. Installs start from RuneForge's own Install button or from
the official API.

### Decide before Phase 7

**A. RuneForge's own pages inside Rose (works now).** A "Mod store" window in Rose shows runeforge.dev itself
(an embedded browser view, via the pywebview package and Windows' WebView2). You get RuneForge's real filters,
search and descriptions. Pressing Install there produces the signed `ltk://install` link: Rose catches it,
downloads the file, imports it into the right champion or category, and runs LTK Manager's check and repair.
Rose remembers each installed mod's RuneForge id and version, and "Check for updates" compares them with the
mod page's latest release. Needs one new package (pywebview).

**B. A native Rose store on RuneForge's API (later).** Same features, drawn in Rose's own CustomTkinter style
(cards like the account window), using a `catalog:read` token you create on RuneForge. This needs the catalog
API routes. Ask in RuneForge's Discord (linked on runeforge.dev) for the public API docs first.

Recommendation: A now, B once RuneForge shares the catalog API. A's install, update and check pieces carry
over to B unchanged; only the browsing part is replaced.

### Phase 7 outline (for A, prompts written once you decide)

1. `main/mod_store.py`: open a pywebview window on runeforge.dev/mods; catch `ltk://install?url=&name=&author=&source=`
   navigations (only https links on runeforge.dev, like LTK Manager's trusted-domain check).
2. Download the signed link to a temp file (`User-Agent: Rose/<version>`, follow redirects, 1 GB cap, .fantome/.modpkg/.zip only).
3. Ask which champion/skin or category it is for (pre-filled from the RuneForge category), then
   `import_mod_file` / `import_category_mod_file`, then LTK Manager's check and repair; show the verdict.
4. Save the mod's origin (RuneForge id, version, page URL) next to the stored file, like LTK Manager's `ModOrigin`.
5. "Check for updates": for each installed RuneForge mod, read its page's latest release (one request per
   second at most) and list the ones with a newer version; Update opens the page so you press Install again.
6. A "Mod store" button in the tray and in the account window's sidebar.

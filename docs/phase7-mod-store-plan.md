# ROSE-AccountSwitcher: Phase 7, the mod store (plan A)

RuneForge's own site inside a Rose window. You browse with RuneForge's real filters, search and descriptions;
pressing Install (or Download) on a mod puts it straight into Rose, checked and repaired by LTK Manager.
Written Nov 8; nothing in it is built yet. Plan B (a native store on RuneForge's API) is at the bottom, for later.

## What you get

- **Mod store window** ("Rose - Mod store"), opened from the tray and from a button in the account window's
  sidebar. It shows runeforge.dev/mods with everything the site has: search, category, champion, sort, Gilded
  picks, mod pages with description, versions, status ("Working") and licence.
- **A Rose bar on top of the page:** Back, Home, **Installed & updates**, and the result of the last install.
- **Install into Rose:** press Install or Download on any mod. Rose catches it (LTK Manager doesn't pop up), puts
  the file in the right place and has LTK Manager check and repair it, the same way Rose 1.5.5 handles mods you
  add by hand. Skins ask which of the champion's skins the mod is for, pre-filled with the champion from the page.
- **Needs fixing:** LTK Manager's verdict on your machine (healthy / repaired / can't be fixed) shows in the store
  right after the install, and in Rose's mod list. RuneForge's own status is on the page as usual.
- **Updates:** Rose remembers which RuneForge mod and version each install came from. **Installed & updates**
  lists them and checks each mod's page for a newer release; Update opens that page so you press Install again,
  and the new file replaces the old one with your skin choices kept.

## How it works

**1. The store window (`main/mod_store.py`, its own small program).** pywebview with Windows' WebView2 engine
(installed: version 157) opens https://runeforge.dev/mods. It runs as a separate process started by Rose, so the
browser engine never shares a thread with Rose's tray or account window.

**2. Catching Install and Download.** pywebview gives access to the real WebView2 control
(`window.native.webview`, available from the `before_show` event). Two of its events are used:
- An Install press makes the page open `ltk://install?url=<signed https link>&name=&author=&source=` (the link
  format LTK Manager handles). Rose cancels that navigation, so LTK Manager doesn't open, and takes the link,
  but only https links on runeforge.dev (the trusted-site rule LTK Manager uses).
- A Download press is a normal browser download; Rose catches it when it finishes.
At that moment the window is on the mod's page (`/mods/<slug>`), so Rose knows which mod it is.

**3. Downloading.** The signed link works for 15 minutes, so Rose downloads it straight away to
`%LOCALAPPDATA%\Rose\store-downloads\`, with Rose's own User-Agent, and accepts only .fantome, .modpkg and
.zip files up to 1 GB. Rose never downloads anything you didn't press Install or Download for.

**4. Handing it to Rose.** The store connects to Rose's local bridge (`ws://127.0.0.1:<port from
state\bridge_port.txt>`, the same one the in-client plugins use) and sends a new `mod-store-install` message. A
new handler file, `pengu/communication/mod_store_handlers.py` (like `account_handlers.py`):
- accepts only files inside `store-downloads` (so no other program can make Rose import an arbitrary file);
- skins: `ModStorageService.import_mod_file(champion, file, skins)`, with the skin list asked from Rose
  (`mod-store-skins`, read from the League client like Rose's own import, so League must be open);
- everything else: `import_category_mod_file(category, file)`; RuneForge's Maps, HUD & UI, VFX, Fonts, Loading
  screens map to the same Rose categories, and Sounds to SFX, Announcer or Voice-over;
- then LTK Manager's check and repair (`_check_imported_mods` → `OverlayManager.check_mod`), and replies with
  the verdict.

**5. Remembering where it came from.** Next to each stored mod, Rose writes an origin note: RuneForge slug, page
link, release id (from the signed link), version (from the page), file hash and install date, like LTK
Manager's `ModOrigin`.

**6. Updates.** **Installed & updates** reads each installed mod's page (at most one per second, only when you
open that view or press Check) and compares the latest release version with the one installed.

## New packages

pywebview 6.2.1 (BSD licence) and, for Windows, pythonnet plus its small helpers (proxy_tools, bottle,
typing_extensions). Installed into Rose's .venv and pinned in requirements-run.txt, like CustomTkinter.

## Risks

- **The Install button may behave differently in an embedded browser** (for example, the site may only hand
  signed links to LTK Manager). Step 7A checks this first. If Install doesn't work, Download still does, since
  it's a normal browser download.
- **RuneForge changes its pages:** catching Install and Download and the import keep working. The parts that
  read the page (the category and champion pre-fill, the version for update checks) may need fixing; the store
  then asks you instead.
- **Skin mods need League open** to list the champion's skins (Rose's own import works the same way). Without
  it, the store keeps the file and says so.
- **Being a good guest:** the store is a browser you drive. Downloads only happen on your clicks, update checks
  are on demand and slow (one page per second), nothing is re-hosted, and mod pages keep their authors' links and
  licences.

## Build order

| Part | What | Prompts |
|---|---|---|
| 7A | Try-out: store window opens runeforge.dev and logs what Install and Download do. **You press Install and Download once on a mod** (needs you at the PC) | 3 |
| 7B | Rose side: `mod-store-install` and `mod-store-skins` messages, store-downloads only, import, LTK check, origin note, tested with a local file | 5 |
| 7C | Store side: catch Install/Download, download, category/skin picker, hand to Rose, show the verdict | 5 |
| 7D | Installed & updates view, update check, Update | 3 |
| 7E | Mod store button in the tray and the account window; Rose bar polish (THEME colours, League font) | 2 |

About 18 small Continue prompts. Each part is tested before the next, like Phases 4 and 5.

**Status (Nov 8, evening):** 7B-7E built and committed (prompts 63-80, all written by Continue, checked and fixed
here; tests in the commit messages). 7A's live press of Install/Download is still to do, see
docs/home-test-checklist.md. The bar already uses Rose's dark/gold; the League font in the native bar was skipped
(WinForms needs a private font collection for it, little gain).

## Decide before building

1. OK to add pywebview and pythonnet to Rose's environment?
2. Check for updates automatically when the store opens, or only when you press Check?
3. 7A needs you at the PC to press Install and Download once (about 5 minutes). Do that when you're home, then I
   build 7B onwards?

## Later: plan B (native store on RuneForge's API)

If RuneForge publishes its catalog API (`catalog:read` tokens exist; the route docs aren't public), the browsing
part can be replaced with a native CustomTkinter store using that API. Plan A's install, origin, update and LTK
check pieces carry over unchanged.

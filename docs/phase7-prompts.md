# ROSE-AccountSwitcher: Phase 7 prompts (mod store, plan A)

Plan: docs/phase7-mod-store-plan.md. Run one prompt per chat in Agent mode, then check and commit, as before.
Prompts that create a file need the Write tool allowed. pywebview 6.2.1 and pythonnet are installed and pinned.

Facts the prompts rely on (checked Nov 8):
- In pywebview on Windows, `window.native` exists from the `before_show` event; `window.native.webview` is the
  WinForms WebView2 control. Its `CoreWebView2` is None until WebView2 is ready, so subscribe to
  `window.native.webview.CoreWebView2InitializationCompleted` and use `sender.CoreWebView2` inside that handler.
  The handlers run on the UI thread. `CoreWebView2` offers `LaunchingExternalUriScheme`, `NavigationStarting`,
  `DownloadStarting` and `NewWindowRequested`. Don't touch WebView2 objects from other threads.
- Rose imports with `self.mod_storage.import_mod_file(champion_id, path, skin_ids)` (returns folder, manifest,
  name) and `import_category_mod_file(category, path)` (returns folder, name); both copy the file. Then
  `self._check_imported_mods(imported, errors, remove, skins=True/False)` runs the base-skin fix and LTK Manager's
  check (see the two call sites in pengu/communication/message_handler.py around lines 3350 and 3690).
- Rose's local bridge: WebSocket on 127.0.0.1, port in `get_state_dir() / "bridge_port.txt"`; messages are JSON
  with "type" and "requestId"; replies carry the same requestId.

Lesson from 7B (Nov 8): the local model stops silently when a prompt sends it to a big file (message_handler.py, storage.py). Keep prompts self-contained: say which small file to edit and give the names and shapes it needs, instead of "like X in <big file>".

## Part 7B: Rose side

### 63. Mod store handlers file
```
In Rose source, create pengu/communication/mod_store_handlers.py, modelled on pengu/communication/account_handlers.py: a ModStoreHandlersMixin class with _route_mod_store_message(self, payload_type, payload) -> bool routing "mod-store-install", "mod-store-skins", "mod-store-champions" and "mod-store-installed" to _handle_mod_store_install, _handle_mod_store_skins, _handle_mod_store_champions and _handle_mod_store_installed; a _send_mod_store_response(self, request, payload) that copies requestId like _send_account_response; and a module function store_downloads_dir() returning get_user_data_dir() / "store-downloads" (from utils.core.paths), created if missing. Each handler for now replies {"type": <type> + "-response", "success": False, "error": "Not built yet"}. Change nothing else. Stop there.
```

### 64. Route the messages
```
In Rose source, pengu/communication/message_handler.py: do not read the whole file, use Search. 1) Next to the line "from .account_handlers import AccountHandlersMixin" add "from .mod_store_handlers import ModStoreHandlersMixin". 2) Change "class MessageHandler(AccountHandlersMixin):" to "class MessageHandler(AccountHandlersMixin, ModStoreHandlersMixin):". 3) Right after the two lines "elif self._route_account_message(payload_type, payload):" and the line below it, add the same for mod store messages: "elif self._route_mod_store_message(payload_type, payload):" followed by "pass" (copy the exact form the account lines use). Change nothing else. Stop there.
```

### 65. Only files the store downloaded
```
In Rose source, pengu/communication/mod_store_handlers.py: add _store_download_path(raw) that returns a Path only if raw names an existing file inside store_downloads_dir() (compare Path(raw).resolve() with store_downloads_dir().resolve() using is_relative_to) whose suffix is .fantome, .modpkg or .zip, and None otherwise. Log a warning for a refused path. Change nothing else. Stop there.
```

### 66. Origin note beside a stored mod
```
In Rose source, injection/mods/storage.py: add ORIGIN_SIDECAR_SUFFIX = ".origin.json" next to DESCRIPTION_SIDECAR_SUFFIX, add it to the suffixes in sidecar_paths (so it is deleted and renamed with its mod), and add write_origin(self, stored: Path, origin: dict) that writes origin as JSON (utf-8, indent 2) to stored.with_suffix(ORIGIN_SIDECAR_SUFFIX), and read_origin(cls, stored) that returns that dict or None. Change nothing else. Stop there.
```

### 67. Install
```
In Rose source, pengu/communication/mod_store_handlers.py, _handle_mod_store_install(payload): payload has file, kind ("champion" or "category"), championId, skinIds (list of ints), category, and origin (dict: source, slug, pageUrl, releaseId, version, name, author). Refuse unless _store_download_path(file) returns a path. For "champion": self.mod_storage.import_mod_file(championId, path, skinIds) and build the imported item like the champion import in message_handler.py ({fileName, path, modName, targetManifest}); remove = lambda item: self.mod_storage.delete_champion_mod(championId, mod_name=item["modName"]); skins=True. For "category": refuse a category not in self.mod_storage.MOD_CATEGORIES; import_category_mod_file(category, path); remove = lambda item: self.mod_storage.delete_category_mod(category, item["modName"]); skins=False. Then kept = self._check_imported_mods([item], errors, remove, skins=...). If kept, write the origin with self.mod_storage.write_origin(Path(kept[0]["path"]), origin + installedAt (UTC ISO time) + sha256 of the downloaded file). Always delete the downloaded file at the end. Reply {"type": "mod-store-install-response", "success": bool(kept), "modName", "health": kept[0].get("health"), "error": first error}. Never raise. Change nothing else. Stop there.
```

### 68. Champions and skins for the picker
```
In Rose source, pengu/communication/mod_store_handlers.py: _handle_mod_store_champions replies {"success", "champions": [{"id", "name"}]} from the League client's /lol-game-data/assets/v1/champion-summary.json (skip id <= 0), using the LCU class from lcu/core/client.py (LCU().get(path)). _handle_mod_store_skins(payload with championId) replies {"success", "skins": [{"id", "name"}]} from /lol-game-data/assets/v1/champions/{championId}.json (its "skins" list, without chromas). If the client isn't running, reply success False with "Open League to choose skins". Change nothing else. Stop there.
```

### 69. Installed store mods
```
In Rose source, pengu/communication/mod_store_handlers.py, _handle_mod_store_installed: walk self.mod_storage.mods_root for files ending in ORIGIN_SIDECAR_SUFFIX, read each with json, and reply {"success": True, "mods": [origin + "storedFile" (the mod file beside it, same name without .origin.json, any existing suffix)]}. Skip unreadable files with a warning. Change nothing else. Stop there.
```

Check after 7B: a test script sends mod-store-install for a .fantome placed in store-downloads (made-up mod) and gets the
mod imported with an origin note, the download deleted, and a refused install for a file outside store-downloads.

## Part 7C: store window (main/mod_store.py)

### 70. Store window
```
In Rose source, create main/mod_store.py, started with python -m main.mod_store. It opens one pywebview window "Rose - Mod store" (1200x820) on https://runeforge.dev/mods, with webview.start(private_mode=False, storage_path=str(get_user_data_dir() / "store-webview")) so RuneForge sign-ins persist. In window.events.before_show, subscribe to window.native.webview.CoreWebView2InitializationCompleted; in that handler keep sender.CoreWebView2 as self.core and log "WebView2 ready". Log to Rose's logger (utils.core.logging get_logger) with the prefix [ModStore]. Change nothing else. Stop there.
```

### 71. Log what Install and Download do (try-out, 7A)
```
In Rose source, main/mod_store.py: in the WebView2-ready handler, subscribe to self.core.LaunchingExternalUriScheme, self.core.NavigationStarting, self.core.DownloadStarting and self.core.NewWindowRequested, and log one line for each with its Uri (args.Uri, for DownloadStarting args.DownloadOperation.Uri and args.ResultFilePath) and the page you are on (self.core.Source). Don't cancel or change anything yet. Change nothing else. Stop there.
```

(You press Install and Download on one mod; the log shows which events fire and what the links look like. The
next prompts get adjusted to what it shows.)

### 72. Catch Install
```
In Rose source, main/mod_store.py: in the LaunchingExternalUriScheme handler (and NavigationStarting, for a uri starting with "ltk:"), when the uri starts with "ltk://install": set args.Cancel = True, parse url, name, author and source from its query string, and accept it only if url is https and its host is runeforge.dev or ends with ".runeforge.dev". Remember the page you are on (self.core.Source, a /mods/<slug> page) and hand {url, name, author, pageUrl, slug} to self.start_install on a background thread. Log a refused link. Change nothing else. Stop there.
```

### 73. Download the signed link
```
In Rose source, main/mod_store.py: add download_signed(url) -> Path, run on a background thread: requests.get with stream=True, timeout 60, allow redirects, User-Agent f"Rose/{APP_VERSION}" (from config); refuse more than 1 GB; take the file name from Content-Disposition, else the URL path; accept only .fantome, .modpkg or .zip (a file starting with b"PK\x03\x04" and no name counts as .zip); save to store_downloads_dir() / f"{uuid4().hex}{suffix}"; on 403 say the link expired (press Install again), 404/410 say the mod's file is gone, 429 say RuneForge is busy. Change nothing else. Stop there.
```

### 74. Catch Download
```
In Rose source, main/mod_store.py: in the DownloadStarting handler, for a download started on a runeforge.dev page, set args.ResultFilePath to store_downloads_dir() / f"{uuid4().hex}{suffix of the original file name}" (only .fantome, .modpkg or .zip, else let it download normally), and subscribe to args.DownloadOperation.StateChanged; when its State is Completed, hand {file, pageUrl, slug} to self.start_install on a background thread. Change nothing else. Stop there.
```

### 75. Talk to Rose
```
In Rose source, main/mod_store.py: add request_rose(type, data, timeout=120) that reads the port from get_state_dir() / "bridge_port.txt", connects with websocket-client (websocket.create_connection to ws://127.0.0.1:<port>), sends json {**data, "type": type, "requestId": uuid4().hex}, reads messages until one has type + "-response" and the same requestId, and returns it as a dict. If Rose isn't running, raise an error that says "Start Rose first". Change nothing else. Stop there.
```

### 76. Pick where it goes
```
In Rose source, main/mod_store.py: add a picker window (a second pywebview window with HTML and a js_api) that self.start_install opens first, as your confirmation: for an Install link nothing is downloaded until you press Install in the picker (then download_signed runs); for a browser Download the file is already in store-downloads. The picker offers: "Champion skin" or a category from Rose's categories (exactly these names: maps, fonts, announcers, ui, voiceover, loading_screen, vfx, sfx, others), a champion list from request_rose("mod-store-champions"), and the champion's skins as checkboxes from request_rose("mod-store-skins", {"championId": id}). Pre-select from the mod page: read the page title and its category text with self.window.evaluate_js before opening the picker. Install sends request_rose("mod-store-install", {...}) with the origin {source: "runeforge", slug, pageUrl, releaseId (from the signed link's /releases/<id>/ part if present), version (if the page shows one), name, author}. Cancel downloads nothing (Install link) or deletes the downloaded file (browser Download). Change nothing else. Stop there.
```

### 77. Rose bar and install result
```
In Rose source, main/mod_store.py: on every loaded page, add a fixed bar at the top (36 px, background #010a13, gold #c8aa6e text) with Back, Home (runeforge.dev/mods), "Installed & updates" and a status text, pushing the page down by 36 px. Show "Installing <name>...", then "Installed <name> - LTK Manager: <health>" or the error, in the status text. Change nothing else. Stop there.
```

## Part 7D: Installed & updates

### 78. Installed list
```
In Rose source, main/mod_store.py: "Installed & updates" loads a local HTML page in the store window listing request_rose("mod-store-installed") mods (name, author, version, install date, where it is stored) with an "Open page" button each, and a "Check for updates" button. Same dark/gold colours. Change nothing else. Stop there.
```

### 79. Check for updates
```
In Rose source, main/mod_store.py: "Check for updates" reads each installed mod's page (requests.get pageUrl, User-Agent f"Rose/{APP_VERSION}", one request per second, never in parallel) and its schema.org JSON-LD (<script type="application/ld+json">): if dateModified is later than the mod's installedAt, mark it "Update available" with an Update button that opens the page so you press Install again. Change nothing else. Stop there.
```

## Part 7E: Open the store

### 80. Store buttons
```
In Rose source: add "Mod store" to the tray menu (utils/integration/tray_manager.py, below "Account Switcher") and a "Mod store" button in the account window's sidebar (main/account_gui.py, below ADD ACCOUNT, same style). Both start the store with subprocess.Popen([sys.executable, "-m", "main.mod_store"], cwd=<Rose source folder>), unless one is already running (keep the Popen and check poll()). Change nothing else. Stop there.
```

## What happened (Nov 8)

- 78: Continue built the list. Fixes: file name worked out in Python (a JS regex lost its backslash inside the
  Python string); mod names put in with DOM text, never innerHTML.
- 79: split in two self-contained prompts (Python check, then the page). Fixes: RuneForge's JSON-LD keeps
  dateModified inside "@graph"; odd JSON-LD shapes no longer stop the check; "Open page" and "Update" buttons each
  open their own mod (a shared `var` in a loop made them all open the last one; use forEach).
- 80: Continue added both buttons from exact code in the prompt. Fix: two tray lines got extra indentation.
- 81 (your call, Nov 8: Update replaces the old copy): after the new copy passes LTK Manager's check, earlier
  copies of the same RuneForge mod (same slug) in the same champion or category folder are removed with Rose's
  own delete. Fix: delete by Rose's mod name (no extension); the full file name left the old skin-target entry.

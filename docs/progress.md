# ROSE-AccountSwitcher — Development Progress

## Status: In Progress

### What's Done

#### 1. Backend (Python)
- **File**: `Rose/pengu/communication/message_handler.py`
- Added 4 new bridge message handlers:
  - `account-list` → returns all saved accounts with active status
  - `account-add` → adds a new account (email, summoner name, region)
  - `account-switch` → switches to an account, updates session data
  - `account-remove` → removes an account from storage
- Uses existing `AccountManager` class from `main/account_manager.py`
- Accounts stored in `%LOCALAPPDATA%\Rose\accounts\accounts.json`

#### 2. Frontend (JavaScript)
- **File**: `Pengu Loader/plugins/ROSE-AccountSwitcher/index.js`
- Waits for bridge (`window.__roseBridge`) to be available
- Adds a navigation icon in the League client nav bar
- Opens a flyout panel with account switching UI when clicked
- Sends/receives messages via bridge using request/response pattern
- CSS injection from local file with fallback inline styles

#### 3. Styles (CSS)
- **File**: `Pengu Loader/plugins/ROSE-AccountSwitcher/css/styles.css`
- Rose-themed styling matching Settings panel aesthetic
- Account list items with avatars, summoner names, regions
- Login form (email, summoner name, region selector)
- Custom scrollbars and transitions

#### 4. Manifest
- **File**: `Pengu Loader/plugins/ROSE-AccountSwitcher/manifest.json`
- Already existed, no changes needed

### Known Issues

1. **Python version mismatch** — System Python is 3.14 but Rose requires 3.11–3.12. Dependencies installed with compatible versions (unpinned Pillow).

2. **Syntax error in tray_manager.py:251** — Broken `try/except` inside a `finally` block. The `except Exception as e:` on line 251 has no matching `try`. Needs fixing before Rose can launch.

3. **Pillow build failure** — Pillow 10.4.0 has no prebuilt binary for Python 3.14; installed latest compatible version instead.

### File Locations

| Component | Path |
|---|---|
| Plugin source | `_internal/Pengu Loader/plugins/ROSE-AccountSwitcher/` |
| Backend handlers | `_internal/Rose/pengu/communication/message_handler.py` |
| Account storage | `%LOCALAPPDATA%\Rose\accounts\accounts.json` |
| Bridge port (runtime) | `%LOCALAPPDATA%\Rose\state\bridge_port.txt` |

### Next Steps

- [ ] Fix `tray_manager.py:251` syntax error (broken try/except indentation)
- [ ] Test plugin with League client running
- [ ] Add session token persistence in localStorage
- [ ] Auto-login accounts on switch (store/retrieve session tokens)
- [ ] Keyboard shortcuts for quick-switching
- [ ] Import/export account list

### How to Run

```powershell
# Install dependencies first (Python 3.14 compatible versions):
pip install urllib3==2.0.7 requests==2.31.0 websocket-client==1.7.0 websockets==12.0 Pillow pystray xxhash zstandard psutil

# Then run:
python "C:\Program Files\Rose\_internal\Rose\main.py"
```

### Architecture

```
User clicks nav icon
    ↓
Plugin opens flyout panel (CSS-styled)
    ↓
Plugin sends "account-list" via WebSocket bridge → Python backend
    ↓
Backend returns account list → Plugin renders UI
    ↓
User adds/switches/removes accounts
    ↓
Messages routed through message_handler.py → AccountManager → accounts.json
```

---

*Last updated: 2026-11-05*

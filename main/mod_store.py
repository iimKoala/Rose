#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mod store - opens RuneForge mod store in a WebView2 window."""

import ctypes
import json
import os
import re
import threading
import time
import uuid
import winsound
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin

import requests
import webview
import websocket

from utils.core.logging import get_named_logger
from utils.core.paths import get_state_dir, get_user_data_dir


log = get_named_logger("mod_store", "mod_store")

CATEGORIES = [
    ("maps", "Maps"),
    ("fonts", "Fonts"),
    ("announcers", "Announcers"),
    ("ui", "HUD & UI"),
    ("voiceover", "Voice-over"),
    ("loading_screen", "Loading screens"),
    ("vfx", "VFX"),
    ("sfx", "Sound effects"),
    ("others", "Other"),
]


# pywebview exposes every public attribute of a js_api object to the page, recursively: keep non-API attributes "_private"

class _PickerApi:
    def __init__(self, store, init):
        self._store = store
        self._init = init
        self._choice = None
        self._done = threading.Event()

    def get_init(self):
        return self._init

    def get_skins(self, champion_id):
        try:
            return self._store.request_rose(
                "mod-store-skins", {"championId": int(champion_id)}, timeout=15
            )
        except Exception as e:
            return {"success": False, "error": str(e)}

    def choose(self, choice):
        self._choice = choice
        self._done.set()

    def cancel(self):
        self._done.set()


PICKER_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
body {
    background: #010a13;
    color: #f0e6d2;
    font-family: 'Segoe UI', sans-serif;
    margin: 0;
    padding: 20px;
}
.container {
    max-width: 420px;
    margin: 0 auto;
}
h1 {
    color: #c8aa6e;
    font-size: 18px;
    margin: 0 0 4px;
}
.author {
    color: #888;
    font-size: 13px;
    margin: 0 0 16px;
}
label {
    display: block;
    margin: 12px 0 4px;
    font-size: 14px;
}
select {
    background: #0a1520;
    color: #f0e6d2;
    border: 1px solid #333;
    padding: 6px;
    width: 100%;
    box-sizing: border-box;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}
.skins-list {
    margin: 8px 0;
    max-height: 150px;
    overflow-y: auto;
}
.skin-item {
    margin: 4px 0;
}
.skin-item label {
    display: inline;
    margin: 0;
    font-size: 14px;
}
.error {
    color: #e74c3c;
    font-size: 13px;
    margin: 8px 0;
}
.buttons {
    display: flex;
    gap: 10px;
    margin-top: 16px;
}
button {
    flex: 1;
    padding: 8px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}
#installBtn {
    background: #c8aa6e;
    color: #010a13;
}
#cancelBtn {
    background: #333;
    color: #f0e6d2;
}
.hidden {
    display: none;
}
</style>
</head>
<body>
<div class="container">
    <h1 id="modName"></h1>
    <div class="author" id="modAuthor"></div>

    <label>
        <input type="radio" name="kind" value="champion" id="radioChampion"> Champion skin
    </label>
    <label>
        <input type="radio" name="kind" value="category" id="radioOther"> Other mod
    </label>

    <div id="championSection">
        <label for="championSelect">Champion:</label>
        <select id="championSelect"></select>
        <div class="author" id="skinsHint"></div>
        <div id="skinsList" class="skins-list"></div>
    </div>

    <div id="categorySection" class="hidden">
        <label for="categorySelect">Category:</label>
        <select id="categorySelect"></select>
    </div>

    <div class="error" id="errorText"></div>

    <div class="buttons">
        <button id="installBtn">Install</button>
        <button id="cancelBtn">Cancel</button>
    </div>
</div>
<script>
let init = null;

async function setup() {
    init = await pywebview.api.get_init();

    document.getElementById("modName").textContent = init.name;
    document.getElementById("modAuthor").textContent = "by " + init.author;

    const championSelect = document.getElementById("championSelect");
    for (const c of init.champions) {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = c.name;
        if (c.id === init.guessChampion) opt.selected = true;
        championSelect.appendChild(opt);
    }

    const categorySelect = document.getElementById("categorySelect");
    for (const cat of init.categories) {
        const opt = document.createElement("option");
        opt.value = cat.value;
        opt.textContent = cat.label;
        if (cat.value === init.guessCategory) opt.selected = true;
        categorySelect.appendChild(opt);
    }

    if (init.guessKind === "champion") {
        document.getElementById("radioChampion").checked = true;
        showChampionSection();
    } else {
        document.getElementById("radioOther").checked = true;
        showCategorySection();
    }

    if (init.lockChampion) {
        // The mod file names its champion: the user only picks which skin it replaces
        document.getElementById("radioChampion").closest("label").classList.add("hidden");
        document.getElementById("radioOther").closest("label").classList.add("hidden");
        championSelect.disabled = true;
        const champ = init.champions.find(c => c.id === init.guessChampion);
        document.getElementById("skinsHint").textContent =
            "This mod is for " + (champ ? champ.name : "this champion") + ". Which skin should it replace?";
    }

    document.getElementById("radioChampion").addEventListener("change", showChampionSection);
    document.getElementById("radioOther").addEventListener("change", showCategorySection);
    championSelect.addEventListener("change", loadSkins);

    loadSkins();
}

if (window.pywebview && window.pywebview.api && window.pywebview.api.get_init) {
    setup();
} else {
    window.addEventListener("pywebviewready", setup, { once: true });
}

function showChampionSection() {
    document.getElementById("championSection").classList.remove("hidden");
    document.getElementById("categorySection").classList.add("hidden");
}

function showCategorySection() {
    document.getElementById("categorySection").classList.remove("hidden");
    document.getElementById("championSection").classList.add("hidden");
}

async function loadSkins() {
    const championSelect = document.getElementById("championSelect");
    const championId = championSelect.value;
    const skinsList = document.getElementById("skinsList");
    skinsList.innerHTML = "";

    const result = await pywebview.api.get_skins(championId);
    if (!result.success) {
        const err = document.createElement("div");
        err.className = "error";
        err.textContent = result.error;
        skinsList.appendChild(err);
        return;
    }

    for (const skin of result.skins) {
        const div = document.createElement("div");
        div.className = "skin-item";
        var label = document.createElement("label");
        var input = document.createElement("input");
        input.type = "checkbox";
        input.value = String(skin.id);
        label.appendChild(input);
        // A champion's base skin id is championId * 1000
        label.appendChild(document.createTextNode(" " + (skin.id % 1000 === 0 ? "Default (" + skin.name + ")" : skin.name)));
        div.appendChild(label);
        skinsList.appendChild(div);
    }
}

document.getElementById("installBtn").addEventListener("click", async () => {
    const kind = document.getElementById("radioChampion").checked ? "champion" : "category";
    const errorText = document.getElementById("errorText");
    errorText.textContent = "";

    if (kind === "champion") {
        const championId = parseInt(document.getElementById("championSelect").value);
        const checkedSkins = Array.from(document.querySelectorAll("#skinsList input[type=checkbox]:checked")).map(cb => parseInt(cb.value));
        if (checkedSkins.length === 0) {
            errorText.textContent = "Select at least one skin.";
            return;
        }
        await pywebview.api.choose({kind: kind, championId: championId, skinIds: checkedSkins, category: null});
    } else {
        const category = document.getElementById("categorySelect").value;
        await pywebview.api.choose({kind: kind, championId: null, skinIds: [], category: category});
    }
});

document.getElementById("cancelBtn").addEventListener("click", () => {
    pywebview.api.cancel();
});
</script>
</body>
</html>"""


def _redact(uri: str) -> str:
    try:
        parsed = urlparse(uri)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{host}{port}"

        extra = ""
        if parsed.scheme == "ltk" and parsed.query:
            qs = parse_qs(parsed.query)
            url_param = qs.get("url", [""])[0]
            if url_param:
                extra = " (url: " + _redact(url_param) + ")"

        if parsed.query:
            qs = parse_qs(parsed.query)
            query_parts = [f"{key}=…" for key in qs]
            query = "?" + "&".join(query_parts)
        else:
            query = ""

        return f"{parsed.scheme}://{netloc}{parsed.path}{query}{extra}"
    except Exception:
        return "<unparseable>"


# The shops the store window installs from: the name saved with each mod -> (its button's text, the page
# the button opens, its host)
SHOPS = {
    "runeforge": ("RuneForge", "https://runeforge.dev/mods", "runeforge.dev"),
    "divineskins": ("Divine Skins", "https://divineskins.gg/mods/lol", "divineskins.gg"),
}


def _shop_of(url: str) -> str:
    """The shop a page or file address belongs to, "" for any other site (the one place this check lives).

    Strict on purpose: https only, no user@ part, port, backslash, space or control character. urlparse and
    requests read such URLs as different hosts ("https://evil.com\\@runeforge.dev" is runeforge.dev to
    urlparse, evil.com to requests), so the check compares the whole host part exactly.
    """
    url = url or ""
    if "\\" in url or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        return ""
    p = urlparse(url)
    host = p.netloc.lower()
    if p.scheme != "https":
        return ""
    return next((name for name, (_, _, shop_host) in SHOPS.items() if host == shop_host or host.endswith("." + shop_host)), "")


def _is_runeforge(url: str) -> bool:
    """True only for https://runeforge.dev or an https subdomain of it"""
    return _shop_of(url) == "runeforge"


def _page_slug(shop: str, page_url: str) -> str:
    """The mod's own part of its page address: what tells one store mod from another (an update replaces the
    copy with the same shop and slug). RuneForge: /mods/<slug>. Divine Skins: its download page is
    /download/<creator>/<mod> (Rose's store log, Nov 14), so "<creator>/<mod>": two creators can give their
    mods the same name. Any other Divine Skins address gets none, so it can never replace another mod."""
    parts = urlparse(page_url).path.strip("/").split("/")
    if shop == "runeforge":
        return parts[1] if len(parts) > 1 and parts[0] == "mods" else ""
    return f"{parts[1]}/{parts[2]}" if len(parts) == 3 and parts[0] == "download" else ""


def _title_name(title: str, shop: str) -> str:
    """The mod's name from its page's title. RuneForge: the part before the first " - ". Divine Skins: without
    the shop's own name after the last " - " or " | " and without the "Download " its download pages put in
    front; a " - " inside the name stays ("Malenia - Talon")."""
    title = (title or "").strip()
    if shop != "divineskins":
        return title.split(" - ")[0].strip()
    ending = re.search(r"\s[-|]\s[^-|]*$", title)
    if ending and SHOPS[shop][0].lower().replace(" ", "") in ending.group(0).lower().replace(" ", ""):
        title = title[:ending.start()]
    return re.sub(r"^download\s+", "", title.strip(), flags=re.IGNORECASE).strip()


class _FlashInfo(ctypes.Structure):
    """FLASHWINFO, for FlashWindowEx"""
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]


FLASH_TRAY_UNTIL_FRONT = 2 | 12  # FLASHW_TRAY | FLASHW_TIMERNOFG: the taskbar button, until the window is in front


def _alert(hwnd, user32=None, beep=None) -> bool:
    """Call the user back to the store: flash its taskbar button until they come, with Windows' notification
    sound. For a download they waited for in another window (the game's client): it needs an answer or is done.
    Nothing while one of the store's own windows is in front (the status line says it), and the window is
    never brought forward. True when it alerted."""
    if not hwnd:
        return False
    if user32 is None:
        user32 = ctypes.WinDLL("user32")  # Rose's own copy: the types set here change no one else's calls
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    in_front = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(in_front))
    if in_front.value == os.getpid():
        return False
    flash = _FlashInfo(ctypes.sizeof(_FlashInfo), hwnd, FLASH_TRAY_UNTIL_FRONT, 0, 0)
    user32.FlashWindowEx(ctypes.byref(flash))
    (beep or winsound.MessageBeep)()
    return True


# Runs in every page of the store window and acts on Divine Skins only: it presses the close button of the
# shop's "Tired of waiting?" offer, as the user would. The shop's wait itself stays as it is.
# shortcut: written from a picture of the offer, not from the page (Rose does not read the shop's pages); if
# the offer stays open its close button is built another way, so adjust the test in the inner loop.
OFFER_CLOSER_JS = r"""(function () {
    if (!/(^|\.)divineskins\.gg$/.test(location.hostname)) return;
    var queued = false;
    function closeOffer() {
        queued = false;
        var found = document.evaluate("//*[normalize-space(text())='Tired of waiting?']", document, null,
                                      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        for (var i = 0; i < found.snapshotLength; i++) {
            var title = found.snapshotItem(i);
            if (!title.getClientRects().length || Date.now() - (title.roseClosed || 0) < 1500) continue;
            // the offer's own box: the nearest part of the page around the title that holds a close button
            for (var box = title.parentElement; box && box !== document.body; box = box.parentElement) {
                var buttons = box.querySelectorAll("button, [role='button']"), close = null;
                for (var b = 0; b < buttons.length && !close; b++) {
                    var said = buttons[b].getAttribute("aria-label"), text = buttons[b].textContent.trim();
                    // a close button says so, or shows a lone sign (an icon, x); the offer's other button has words
                    if (said ? /close|dismiss/i.test(said) : text.length < 2 || /^close$/i.test(text)) close = buttons[b];
                }
                if (close) {
                    title.roseClosed = Date.now();
                    close.click();
                    break;
                }
            }
        }
    }
    new MutationObserver(function () {
        if (!queued) { queued = true; setTimeout(closeOffer, 200); }
    }).observe(document, {childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "hidden", "open"]});
})();
"""


def _parse_when(text: str) -> datetime:
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _mod_champion(file: Path, champions: list) -> int:
    """The champion a skin mod is for, read from the mod file: its WAD is named after the champion's alias
    (WAD/AurelionSol.wad.client, or a folder of that name). 0 if no WAD names one: a map, UI, sound or
    voice-over mod (AurelionSol.en_US.wad.client is voice-over, not a skin), or not a zip (.modpkg)."""
    aliases = {(c.get("alias") or "").lower(): c.get("id", 0) for c in champions if c.get("alias")}
    try:
        with zipfile.ZipFile(file) as z:
            names = z.namelist()
    except (OSError, zipfile.BadZipFile):
        return 0
    for name in names:
        for part in name.replace("\\", "/").lower().split("/"):
            if part.endswith(".wad.client") and part[: -len(".wad.client")] in aliases:
                return aliases[part[: -len(".wad.client")]]
    return 0


class _InstalledApi:
    def __init__(self, store):
        self._store = store
        self._mods = []

    def load(self):
        try:
            r = self._store.request_rose("mod-store-installed", {}, timeout=30)
            self._mods = r.get("mods", [])
            for mod in self._mods:
                mod["fileName"] = Path(mod.get("storedFile") or "").name
            return r
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_health(self):
        """Whether each installed mod still works with this patch (Rose checks, repairs nothing)."""
        try:
            return self._store.request_rose("mod-store-health", {}, timeout=600)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fix(self, identity):
        """Repair one installed mod in place, as an install from the store does."""
        try:
            return self._store.request_rose("mod-store-fix", {"identity": str(identity)}, timeout=300)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_mod(self, identity):
        """Delete one installed mod and its store note, as Rose's own mod list does."""
        try:
            return self._store.request_rose("mod-store-delete", {"identity": str(identity)}, timeout=60)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def rename_mod(self, identity, new_name):
        """Give one installed mod the name Rose shows (here and in its own mod lists); its file is not renamed."""
        try:
            return self._store.request_rose("mod-store-rename", {"identity": str(identity), "newName": str(new_name)}, timeout=30)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_page(self, url):
        if _shop_of(url):
            self._store.window.load_url(url)
            return True
        return False

    def check_updates(self):
        from config import APP_VERSION

        results = []
        first = True
        for mod in self._mods:
            page_url = mod.get("pageUrl") or ""
            if not page_url.startswith("https://runeforge.dev/"):
                continue
            if not first:
                time.sleep(1)
            first = False

            try:
                resp = requests.get(
                    page_url,
                    headers={"User-Agent": f"Rose/{APP_VERSION}"},
                    timeout=20,
                )
            except Exception as e:
                results.append({
                    "slug": mod.get("slug"),
                    "updateAvailable": False,
                    "error": "Couldn't check (" + type(e).__name__ + ")",
                })
                continue

            if resp.status_code != 200:
                results.append({
                    "slug": mod.get("slug"),
                    "updateAvailable": False,
                    "error": f"Couldn't check (HTTP {resp.status_code})",
                })
                continue

            date_modified = None
            blocks = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                resp.text,
                re.S,
            )
            for block in blocks:
                if date_modified is not None:
                    break
                try:
                    parsed = json.loads(block)
                except (json.JSONDecodeError, TypeError):
                    continue
                graph = parsed.get("@graph") if isinstance(parsed, dict) else None
                items = parsed if isinstance(parsed, list) else [parsed] + (graph if isinstance(graph, list) else [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    dm = item.get("dateModified")
                    if dm:
                        date_modified = dm
                        break

            if not date_modified or not mod.get("installedAt"):
                results.append({
                    "slug": mod.get("slug"),
                    "updateAvailable": False,
                    "error": "Couldn't check (no date on the page)",
                })
                continue

            try:
                updated = _parse_when(date_modified) > _parse_when(mod["installedAt"])
            except Exception as e:
                results.append({
                    "slug": mod.get("slug"),
                    "updateAvailable": False,
                    "error": "Couldn't check (" + type(e).__name__ + ")",
                })
                continue

            results.append({
                "slug": mod.get("slug"),
                "updateAvailable": updated,
                "dateModified": date_modified,
            })

        return results


INSTALLED_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
body {
    background: #010a13;
    color: #f0e6d2;
    font-family: 'Segoe UI', sans-serif;
    margin: 0;
    padding: 20px;
}
.container {
    max-width: 720px;
    margin: 0 auto;
}
h1 {
    color: #c8aa6e;
    font-size: 18px;
    margin: 0 0 12px;
}
.check-btn {
    background: transparent;
    color: #c8aa6e;
    border: 1px solid #c8aa6e;
    padding: 6px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    margin-bottom: 12px;
}
.status {
    font-size: 13px;
    color: #a09b8c;
    margin-bottom: 12px;
}
.mod-row {
    display: flex;
    gap: 14px;
    background: #0a1428;
    border: 1px solid #1e2328;
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 10px;
    transition: border-color 0.15s ease;
}
.mod-row:hover {
    border-color: #785a28;
}
.mod-thumb {
    flex: 0 0 72px;
    width: 72px;
    height: 72px;
    border-radius: 4px;
    object-fit: cover;
    background: #1e2328;
}
.mod-thumb.placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    font-weight: bold;
    color: #785a28;
    background: linear-gradient(135deg, #1e2328, #0a1428);
}
.mod-body {
    flex: 1;
    min-width: 0;
}
.mod-name {
    font-weight: bold;
    font-size: 15px;
    color: #f0e6d2;
}
.mod-kind {
    display: inline-block;
    margin-left: 8px;
    padding: 1px 6px;
    border: 1px solid #463714;
    border-radius: 3px;
    font-size: 11px;
    font-weight: normal;
    color: #c8aa6e;
    vertical-align: middle;
}
.mod-meta {
    font-size: 12px;
    color: #a09b8c;
    margin: 4px 0;
}
.mod-actions {
    display: flex;
    gap: 8px;
}
.rename-box {
    display: block;
    width: 100%;
    max-width: 420px;
    margin-top: 6px;
    padding: 4px 8px;
    background: #010a13;
    color: #f0e6d2;
    border: 1px solid #c8aa6e;
    border-radius: 4px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    font-weight: normal;
}
.open-btn.danger-btn {
    color: #e84057;
    border-color: #e84057;
}
.open-btn.danger-btn.confirm {
    background: #e84057;
    color: #010a13;
}
.open-btn {
    background: transparent;
    color: #c8aa6e;
    border: 1px solid #c8aa6e;
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
    margin-top: 8px;
}
.update-line {
    font-size: 12px;
    color: #a09b8c;
    margin-top: 8px;
}
.update-line.has-update {
    color: #c8aa6e;
    font-weight: bold;
}
.update-line .open-btn {
    margin-left: 8px;
}
.health-line {
    font-size: 12px;
    color: #a09b8c;
    margin-top: 8px;
}
.health-line.ok {
    color: #0acbe6;
}
.health-line.broken {
    color: #e84057;
    font-weight: bold;
}
.health-line .open-btn {
    margin-left: 8px;
    margin-top: 0;
}
</style>
</head>
<body>
<div class="container">
    <h1>Installed mods</h1>
    <button class="check-btn" id="checkBtn">Check for updates</button>
    <div class="status" id="status"></div>
    <div id="modsList"></div>
</div>
<script>
var KIND_LABELS = {skins: "Skin", maps: "Map", fonts: "Font", announcers: "Announcer", ui: "UI", vfx: "VFX",
                   sfx: "Sound", voiceover: "Voice", loading_screen: "Loading screen", others: "Other"};

// Delete asks for a second click within 4 s, then removes the mod and its card
function deleteButton(card, mod) {
    var btn = document.createElement("button");
    btn.className = "open-btn danger-btn";
    btn.textContent = "Delete";
    var armed = null;
    btn.addEventListener("click", function() {
        if (!armed) {
            btn.className = "open-btn danger-btn confirm";
            btn.textContent = "Click again to delete";
            armed = setTimeout(function() {
                armed = null;
                btn.className = "open-btn danger-btn";
                btn.textContent = "Delete";
            }, 4000);
            return;
        }
        clearTimeout(armed);
        armed = null;
        btn.disabled = true;
        btn.textContent = "Deleting...";
        pywebview.api.delete_mod(mod.identity).then(function(result) {
            var status = document.getElementById("status");
            if (result.success) {
                card.parentNode.removeChild(card);
                status.textContent = "Deleted " + (mod.name || result.modName);
            } else {
                btn.disabled = false;
                btn.className = "open-btn danger-btn";
                btn.textContent = "Delete";
                status.textContent = "Couldn't delete " + (mod.name || "it") + ": " + result.error;
            }
        });
    });
    return btn;
}

// Rename: the button opens a text box under the name; Enter or Save keeps it, Esc cancels. Rose changes
// only the name it shows (in its own mod lists too), never the mod's file
function renameButton(name, mod) {
    var btn = document.createElement("button");
    btn.className = "open-btn";
    btn.textContent = "Rename";
    var box = null;
    function close() {
        if (box) name.removeChild(box);
        box = null;
        btn.disabled = false;
        btn.textContent = "Rename";
    }
    function save() {
        if (btn.disabled) return;
        var wanted = box.value.trim();
        if (!wanted || wanted === mod.name) {
            close();
            return;
        }
        btn.disabled = true;
        btn.textContent = "Saving...";
        pywebview.api.rename_mod(mod.identity, wanted).then(function(result) {
            var status = document.getElementById("status");
            if (result.success) {
                status.textContent = "Renamed " + mod.name + " to " + result.displayName;
                mod.name = result.displayName;
                name.firstChild.textContent = mod.name;
            } else {
                status.textContent = "Couldn't rename " + mod.name + ": " + result.error;
            }
            close();
        });
    }
    btn.addEventListener("click", function() {
        if (box) {
            save();
            return;
        }
        box = document.createElement("input");
        box.className = "rename-box";
        box.value = mod.name || "";
        box.maxLength = 100;
        box.addEventListener("keydown", function(event) {
            if (event.key === "Enter") save();
            else if (event.key === "Escape") close();
        });
        name.appendChild(box);
        box.focus();
        box.select();
        btn.textContent = "Save";
    });
    return btn;
}

function setup() {
    pywebview.api.load().then(function(result) {
        var status = document.getElementById("status");
        if (!result.success) {
            status.textContent = result.error;
            return;
        }
        var mods = result.mods || [];
        if (mods.length === 0) {
            status.textContent = "Nothing installed from the store yet";
            return;
        }
        var list = document.getElementById("modsList");
        mods.forEach(function(mod) {
            if (mod.displayName) mod.name = mod.displayName;  // the name the user gave it in Rose
            var card = document.createElement("div");
            card.className = "mod-row";

            var thumb = document.createElement(mod.image ? "img" : "div");
            thumb.className = mod.image ? "mod-thumb" : "mod-thumb placeholder";
            if (mod.image) {
                thumb.src = mod.image;
                thumb.alt = "";
            } else {
                thumb.textContent = (mod.name || "?").charAt(0).toUpperCase();
            }
            card.appendChild(thumb);

            // The body holds the health line (found by the mod's identity) and the update line (by its slug:
            // the same store mod can be installed twice, as a map and as an other mod)
            var row = document.createElement("div");
            row.className = "mod-body";
            row.id = mod.identity || mod.slug || "";
            row.setAttribute("data-slug", mod.slug || "");
            row.setAttribute("data-page-url", mod.pageUrl || "");

            var name = document.createElement("div");
            name.className = "mod-name";
            name.textContent = mod.name || "";
            if (mod.kind) {
                var kind = document.createElement("span");
                kind.className = "mod-kind";
                kind.textContent = KIND_LABELS[mod.kind] || mod.kind;
                name.appendChild(kind);
            }
            row.appendChild(name);

            var meta = document.createElement("div");
            meta.className = "mod-meta";
            var parts = mod.author ? ["by " + mod.author] : [];
            if (mod.version) parts.push("version " + mod.version);
            if (mod.installedAt) parts.push("installed " + mod.installedAt.split("T")[0]);
            meta.textContent = parts.join("  ·  ");
            row.appendChild(meta);

            var actions = document.createElement("div");
            actions.className = "mod-actions";
            if (mod.pageUrl) {
                var btn = document.createElement("button");
                btn.className = "open-btn";
                btn.textContent = "Open page";
                btn.addEventListener("click", function() {
                    pywebview.api.open_page(mod.pageUrl);
                });
                actions.appendChild(btn);
            }
            actions.appendChild(renameButton(name, mod));
            actions.appendChild(deleteButton(card, mod));
            row.appendChild(actions);

            card.appendChild(row);
            list.appendChild(card);
        });
        checkHealth();
    }).catch(function(err) {
        document.getElementById("status").textContent = err;
    });
}

function showHealth(row, mod) {
    var old = row.querySelector(".health-line");
    if (old) old.parentNode.removeChild(old);
    var line = document.createElement("div");
    line.className = "health-line";
    var problems = mod.problems || [];
    if (mod.health === "ltk") {
        line.textContent = "Kept in LTK Manager's library";
    } else if (problems.length) {
        line.className += " broken";
        line.textContent = "Can't be played: " + (problems[0].title || problems[0].description || "LTK Manager can't repair it") + ". Update or delete it";
    } else if ((mod.fixable || 0) > 0) {
        line.className += " broken";
        line.textContent = "Needs a repair: " + mod.fixable + " problem(s) that can crash the game";
        var fixBtn = document.createElement("button");
        fixBtn.className = "open-btn";
        fixBtn.textContent = "Fix";
        fixBtn.addEventListener("click", function() {
            fixBtn.disabled = true;
            fixBtn.textContent = "Fixing...";
            pywebview.api.fix(mod.identity).then(function(result) {
                if (!result.success) {
                    fixBtn.disabled = false;
                    fixBtn.textContent = "Fix";
                    line.firstChild.textContent = "Couldn't fix it: " + result.error;
                    return;
                }
                if (!result.repaired && (result.fixable || 0) > 0) {
                    // the repair ran and changed nothing: say so, not the same line again as if nothing was pressed
                    fixBtn.disabled = false;
                    fixBtn.textContent = "Fix";
                    line.firstChild.textContent = "Couldn't repair it (the reason is in Rose's log): still " + result.fixable + " problem(s)";
                    return;
                }
                showHealth(row, {identity: mod.identity, health: result.health, fixable: result.fixable,
                                 problems: result.problems, repaired: result.repaired});
            });
        });
        line.appendChild(fixBtn);
    } else if (mod.health === "healthy" || mod.health === "repairable") {
        line.className += " ok";
        line.textContent = mod.repaired ? "Fixed " + mod.repaired + " problem(s): works with this patch" : "Works with this patch";
    } else if (mod.health === "unrepairable") {
        // checked: no problem that stops it, but a flaw the checker can't repair (Darkrai: no sound)
        var flaws = mod.warnings || [];
        line.textContent = "Works, with a flaw that can't be repaired" + (flaws.length ? ": " + (flaws[0].description || flaws[0].title) : "");
    } else {
        line.textContent = "Not checked" + (mod.health ? " (" + mod.health + ")" : "");
    }
    row.appendChild(line);
}

function checkHealth() {
    pywebview.api.check_health().then(function(result) {
        if (!result.success) {
            document.getElementById("status").textContent = "Couldn't check the mods: " + result.error;
            return;
        }
        (result.mods || []).forEach(function(mod) {
            var row = document.getElementById(mod.identity || mod.slug || "");
            if (row) showHealth(row, mod);
        });
    });
}

document.getElementById("checkBtn").addEventListener("click", function() {
    var btn = document.getElementById("checkBtn");
    var status = document.getElementById("status");
    btn.disabled = true;
    status.textContent = "Checking for updates...";
    var oldLines = document.querySelectorAll(".update-line");
    for (var i = 0; i < oldLines.length; i++) {
        oldLines[i].parentNode.removeChild(oldLines[i]);
    }
    pywebview.api.check_updates().then(function(results) {
        var n = 0;
        results.forEach(function(result) {
            // Every card of that store mod (it can be installed twice, as a map and as an other mod)
            var rows = document.querySelectorAll('.mod-body[data-slug="' + CSS.escape(result.slug || "") + '"]');
            Array.prototype.forEach.call(rows, function(row) {
                var line = document.createElement("div");
                line.className = "update-line";
                if (result.updateAvailable) {
                    line.className += " has-update";
                    line.textContent = "Update available";
                    var updateBtn = document.createElement("button");
                    updateBtn.className = "open-btn";
                    updateBtn.textContent = "Update";
                    updateBtn.addEventListener("click", function() {
                        pywebview.api.open_page(row.getAttribute("data-page-url"));
                    });
                    line.appendChild(updateBtn);
                    n++;
                } else if (result.error) {
                    line.textContent = result.error;
                } else {
                    line.textContent = "Up to date";
                }
                row.appendChild(line);
            });
        });
        if (n > 0) {
            status.textContent = n + " update(s) available";
        } else {
            status.textContent = "All up to date";
        }
        btn.disabled = false;
    }).catch(function(err) {
        status.textContent = "Couldn't check: " + err;
        btn.disabled = false;
    });
});

if (window.pywebview && window.pywebview.api && window.pywebview.api.load) {
    setup();
} else {
    window.addEventListener("pywebviewready", setup, { once: true });
}
</script>
</body>
</html>"""


class ModStore:
    """Lifelong manager for the mod-store WebView2 window."""

    def __init__(self):
        self.core = None
        self._status = ""
        self._form = None
        self._status_label = None
        self._Action = None
        self.window = webview.create_window(
            "Rose - Mod store",
            SHOPS["runeforge"][1],
            width=1200,
            height=820,
        )
        self.window.events.before_show += self._before_show

    def ask_where(self, init):
        api = _PickerApi(self, init)
        window = webview.create_window("Rose - Install mod", html=PICKER_HTML, js_api=api, width=460, height=600, resizable=False)
        window.events.closed += lambda: api._done.set()
        api._done.wait()
        try:
            window.destroy()
        except Exception:
            pass
        return api._choice

    def _before_show(self, window):
        window.native.webview.CoreWebView2InitializationCompleted += self._on_initialization_completed
        self._build_bar(window.native)

    def _on_initialization_completed(self, sender, args):
        self.core = sender.CoreWebView2
        log.info("[ModStore] WebView2 ready")
        self.core.LaunchingExternalUriScheme += self._on_launching_external_uri_scheme
        self.core.NavigationStarting += self._on_navigation_starting
        self.core.DownloadStarting += self._on_download_starting
        self.core.SourceChanged += self._on_source_changed
        self.core.NewWindowRequested += self._on_new_window_requested
        try:
            self.core.AddScriptToExecuteOnDocumentCreatedAsync(OFFER_CLOSER_JS)
        except Exception as e:  # noqa: BLE001 - the shops work without it
            log.info(f"[ModStore] Could not add the offer closer: {e}")

    def _on_launching_external_uri_scheme(self, sender, args):
        args.Cancel = True
        uri = args.Uri
        origin = args.InitiatingOrigin
        if uri.startswith("ltk://install"):
            if _is_runeforge(origin):
                self._handle_install_link(uri, origin)
            else:
                log.info(f"[ModStore] Blocked an external app link: {_redact(uri)} from {_redact(origin)}")
        else:
            log.info(f"[ModStore] LaunchingExternalUriScheme on {_redact(origin)}: Uri={_redact(uri)}")

    def _on_navigation_starting(self, sender, args):
        uri = args.Uri
        if uri.startswith("ltk:"):
            args.Cancel = True
            p = urlparse(self.core.Source)
            origin = f"{p.scheme}://{p.hostname}"
            self._handle_install_link(uri, origin)
        elif uri.startswith("rose://"):
            args.Cancel = True
            if uri == "rose://installed":
                threading.Thread(target=self.show_installed, daemon=True).start()
        else:
            log.info(f"[ModStore] NavigationStarting on {_redact(self.core.Source)}: Uri={_redact(args.Uri)}")

    def _on_source_changed(self, sender, args):
        """Remember the last shop page that is not a download page: Divine Skins downloads start on a page of
        their own (/download/<creator>/<mod>), and "Open page" should open the mod's page, not download it again"""
        source = self.core.Source
        if _shop_of(source) and not urlparse(source).path.startswith("/download/"):
            self._last_page = source

    def _handle_install_link(self, uri, origin):
        if not (uri.startswith("ltk://install") and _is_runeforge(origin)):
            log.info(f"[ModStore] Blocked install link: {_redact(uri)} from {_redact(origin)}")
            threading.Thread(target=self.show_status, args=("That install link isn't from RuneForge, so Rose didn't use it",), daemon=True).start()
            return
        parsed = urlparse(uri)
        qs = parse_qs(parsed.query)
        url = qs.get("url", [""])[0]
        name = qs.get("name", [""])[0]
        author = qs.get("author", [""])[0]
        if _is_runeforge(url):
            page_url = self.core.Source
            info = {"url": url, "name": name, "author": author, "pageUrl": page_url, "slug": _page_slug("runeforge", page_url)}
            threading.Thread(target=self.start_install, args=(info,), daemon=True).start()
        else:
            log.info(f"[ModStore] Install link refused: {_redact(uri)}")
            threading.Thread(target=self.show_status, args=("That install link isn't from RuneForge, so Rose didn't use it",), daemon=True).start()

    def show_installed(self):
        if getattr(self, "_installed_open", False):
            return
        self._installed_open = True
        api = _InstalledApi(self)
        window = webview.create_window("Rose - Installed mods", html=INSTALLED_HTML, js_api=api, width=760, height=620)
        window.events.closed += lambda: setattr(self, "_installed_open", False)

    def show_status(self, text):
        self._status = text
        log.info("[ModStore] " + text)
        if self._form is not None and self._status_label is not None:
            self._form.BeginInvoke(self._Action(lambda: setattr(self._status_label, "Text", text)))
        self.window.set_title("Rose - Mod store" + (" - " + text if text else ""))

    def alert(self):
        """Call the user back to the store window (_alert), from its own thread as the status line is set"""
        form = getattr(self, "_form", None)

        def flash():
            try:
                _alert(int(form.Handle.ToInt64()))
            except Exception as e:  # noqa: BLE001 - an alert must never end the store window
                log.info(f"[ModStore] Could not flash the store's taskbar button: {e}")
        if form is not None:
            form.BeginInvoke(self._Action(flash))

    def start_install(self, info):
        """Install a downloaded mod (_install), then call back a user who went to another window meanwhile"""
        try:
            self._install(info)
        finally:
            self.alert()

    def _install(self, info):
        # 2) Guess mod info from page
        try:
            title = self.window.evaluate_js("document.title") or ""
            if not title:
                log.info("[ModStore] The page gave no title; naming the mod from its page address")
        except Exception as e:
            log.info(f"[ModStore] Could not read the page's title ({type(e).__name__}); naming the mod from its page address")
            title = ""

        # shortcut: a name made from the page address loses the store's capitals and punctuation; read the name from the page another way once the log shows why the title fails
        shop = info.get("source") or "runeforge"
        name = info.get("name") or _title_name(title, shop) or info.get("slug", "").rsplit("/", 1)[-1].replace("-", " ").title()

        try:
            page_text = self.window.evaluate_js("document.body.innerText.slice(0, 4000)") or ""
        except Exception:
            page_text = ""

        page_text_lower = page_text.lower()

        guess_kind = "champion" if "champion skin" in page_text_lower else "category"

        guess_category = "others"
        for value, label in CATEGORIES:
            if value in page_text_lower or label.lower() in page_text_lower:
                guess_category = value
                break

        # File first: LTK Manager checks it before the user is asked anything, and it names its champion
        if info.get("url"):
            self.show_status("Downloading " + name + "...")
            try:
                file = self.download_signed(info["url"])
            except Exception as e:
                msg = str(e) if isinstance(e, RuntimeError) else type(e).__name__
                self.show_status("Download failed: " + msg)
                return
        else:
            file = Path(info["file"])
        self.show_status("Checking " + name + " with LTK Manager...")
        try:
            checked = self.request_rose("mod-store-check", {"file": str(file)}, timeout=300)
        except Exception as e:
            msg = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            self.show_status("Check failed: " + msg)
            Path(file).unlink(missing_ok=True)
            return
        if not checked.get("success"):
            self.show_status("Not installed: " + str(checked.get("error")))
            Path(file).unlink(missing_ok=True)
            return

        # 3) Champions
        champions = []
        error = None
        try:
            champs = self.request_rose("mod-store-champions", {}, timeout=15)
            if champs.get("success"):
                champions = champs.get("champions", [])
            else:
                error = champs.get("error")
        except Exception as e:
            champions = []
            error = str(e)

        guess_champion = _mod_champion(file, champions)
        lock_champion = bool(guess_champion)
        if lock_champion:
            guess_kind = "champion"
        elif champions:
            # Whole words, longest name first: "Vi" must not match inside "Victorious Morgana"
            mod_name = name.lower()
            for champ in sorted(champions, key=lambda c: -len(c.get("name", ""))):
                champ_name = champ.get("name", "").lower()
                if champ_name and re.search("(?<![a-z])" + re.escape(champ_name) + "(?![a-z])", mod_name):
                    guess_champion = champ.get("id", 0)
                    break
            if guess_champion == 0:
                guess_champion = champions[0].get("id", 0)

        # 4) Ask user, called back first if they went to another window during the download or the check
        self.alert()
        choice = self.ask_where({
            "name": name,
            "author": info.get("author", ""),
            "guessKind": guess_kind,
            "guessChampion": guess_champion,
            "lockChampion": lock_champion,
            "guessCategory": guess_category,
            "champions": champions,
            "categories": [{"value": v, "label": l} for v, l in CATEGORIES],
            "error": error,
        })

        # 5) Cancellation
        if choice is None:
            Path(file).unlink(missing_ok=True)
            self.show_status("Install cancelled")
            return

        # 7) releaseId
        release_id = ""
        download_url = info.get("url", "")
        if download_url:
            try:
                parts = urlparse(download_url).path.rstrip("/").split("/")
                for i, part in enumerate(parts):
                    if part == "releases" and i + 1 < len(parts):
                        release_id = parts[i + 1]
                        break
            except Exception:
                release_id = ""

        # 8) Install
        self.show_status("Installing " + name + "...")
        try:
            result = self.request_rose(
                "mod-store-install",
                {
                    "file": str(file),
                    "kind": choice.get("kind"),
                    "championId": choice.get("championId"),
                    "skinIds": choice.get("skinIds") or [],
                    "category": choice.get("category"),
                    "origin": {
                        "source": shop,
                        "slug": info.get("slug", ""),
                        "pageUrl": info.get("pageUrl", ""),
                        "releaseId": release_id,
                        "version": "",
                        "name": name,
                        "author": info.get("author", ""),
                    },
                },
                timeout=300,
            )
        except Exception as e:
            msg = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            self.show_status("Install failed: " + msg)
            Path(file).unlink(missing_ok=True)
            return

        # 9) Result
        if result.get("success"):
            health = (result.get("health") or {}).get("health") or "checked"
            self.show_status("Installed " + name + (" (old copy replaced)" if result.get("replaced") else "") + " - LTK Manager: " + {"unrepairable": "works, with a flaw it can't repair"}.get(health, health))
        else:
            self.show_status("Not installed: " + str(result.get("error")))

    def _on_download_starting(self, sender, args):
        shop = _shop_of(self.core.Source)
        if not shop:
            log.info(f"[ModStore] DownloadStarting on {_redact(self.core.Source)}: Uri={_redact(args.DownloadOperation.Uri)}, ResultFilePath={Path(args.ResultFilePath).name}")
            return

        suffix = Path(args.ResultFilePath).suffix.lower()
        if suffix in (".fantome", ".modpkg", ".zip"):
            from pengu.communication.mod_store_handlers import store_downloads_dir
            args.ResultFilePath = str(store_downloads_dir() / f"{uuid.uuid4().hex}{suffix}")
            # pywebview's own handler ran first and cancelled every download (its ALLOW_DOWNLOADS is off;
            # turning it on would show a Save As box). Rose takes this one, so undo that cancel.
            args.Cancel = False
            try:
                # and keep the browser's own Downloads box closed: its "Open file" starts LTK Manager on the
                # file while Rose installs it (Nov 14: four LTK Manager windows, one hung, a game left unmodded)
                args.Handled = True
            except Exception as e:  # noqa: BLE001 - the download still installs
                log.info(f"[ModStore] Could not hide the browser's Downloads box: {e}")
            log.info(f"[ModStore] DownloadStarting on {_redact(self.core.Source)}: {Path(args.ResultFilePath).name}")
        else:
            log.info(f"[ModStore] DownloadStarting on {_redact(self.core.Source)}: {Path(args.ResultFilePath).name} (suffix {suffix})")
            return

        page_url = self.core.Source
        slug = _page_slug(shop, page_url)
        came_from = getattr(self, "_last_page", "")
        if urlparse(page_url).path.startswith("/download/") and _shop_of(came_from) == shop and slug.rsplit("/", 1)[-1] in came_from:
            page_url = came_from  # the mod's own page, which the user pressed Download on

        def _on_state_changed(sender_state, args_state):
            op = sender_state
            state = str(op.State)
            if state == "Completed":
                info = {"file": str(op.ResultFilePath), "pageUrl": page_url, "slug": slug, "source": shop}
                threading.Thread(target=self.start_install, args=(info,), daemon=True).start()
            elif state == "Interrupted":
                log.info("[ModStore] Download interrupted: " + Path(str(op.ResultFilePath)).name + " (" + str(op.InterruptReason) + ")")
                Path(str(op.ResultFilePath)).unlink(missing_ok=True)

        args.DownloadOperation.StateChanged += _on_state_changed

    def _on_new_window_requested(self, sender, args):
        log.info(f"[ModStore] NewWindowRequested on {_redact(self.core.Source)}: Uri={_redact(args.Uri)}")

    def download_signed(self, url: str) -> Path:
        """Download a signed URL to store_downloads_dir(). Returns the saved Path."""
        from config import APP_VERSION
        from pengu.communication.mod_store_handlers import store_downloads_dir

        # Follow redirects here, not in requests, so every hop passes the RuneForge check before Rose contacts it
        for _ in range(5):
            if not _is_runeforge(url):
                raise RuntimeError("Rose only downloads mods from RuneForge")
            resp = requests.get(
                url,
                stream=True,
                timeout=60,
                allow_redirects=False,
                headers={"User-Agent": f"Rose/{APP_VERSION}"},
            )
            if not resp.is_redirect:
                break
            url = urljoin(url, resp.headers.get("Location", ""))
            resp.close()
        else:
            raise RuntimeError("Too many redirects")
        try:  # close the response on every path, errors included
            if resp.status_code == 403:
                raise RuntimeError("The link has expired. Press Install again.")
            if resp.status_code in (404, 410):
                raise RuntimeError("The mod's file is gone.")
            if resp.status_code == 429:
                raise RuntimeError("RuneForge is busy.")
            resp.raise_for_status()

            # Determine file name and suffix
            content_disp = resp.headers.get("Content-Disposition", "")
            filename = ""
            if "filename=" in content_disp:
                filename = content_disp.split("filename=")[1].split(";")[0].strip().strip('"').strip("'")
            if not filename:
                filename = urlparse(url).path.split("/")[-1] or ""

            suffix = Path(filename).suffix.lower()
            first_chunk = b""
            if suffix not in (".fantome", ".modpkg", ".zip"):
                first_chunk = next(resp.iter_content(4), b"")
                if first_chunk[:4] != b"PK\x03\x04":
                    raise RuntimeError("That download is not a mod file")
                suffix = ".zip"  # PK header or no name: a zip

            dest = store_downloads_dir() / f"{uuid.uuid4().hex}{suffix}"
            written = 0
            try:
                with dest.open("wb") as f:
                    if first_chunk:
                        f.write(first_chunk)
                        written += len(first_chunk)
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        written += len(chunk)
                        if written > 1_000_000_000:
                            raise RuntimeError("File too large (over 1 GB)")
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
            # Host name only: the query string holds the download signature
            log.info("[ModStore] Downloaded " + dest.name + " from " + (urlparse(resp.url).hostname or "?"))
            return dest
        finally:
            resp.close()

    def request_rose(self, type: str, data: dict, timeout: float = 120) -> dict:
        """Send a request to Rose's bridge and return the response dict."""
        port_file = get_state_dir() / "bridge_port.txt"
        try:
            port = int(port_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            raise RuntimeError("Start Rose first")

        request_id = uuid.uuid4().hex
        message = {**data, "type": type, "requestId": request_id}
        expected_type = type + "-response"

        try:
            ws = websocket.create_connection(f"ws://127.0.0.1:{port}", timeout=timeout)
        except (ConnectionRefusedError, OSError) as e:
            raise RuntimeError("Start Rose first") from e
        try:
            ws.send(json.dumps(message))
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Request {type} timed out after {timeout}s")
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    raise TimeoutError(f"Request {type} timed out after {timeout}s")
                except websocket.WebSocketConnectionClosedException:
                    raise RuntimeError("Rose closed the connection. Is Rose still running?")
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("requestId") == request_id and msg.get("type") == expected_type:
                    return msg
        finally:
            ws.close()

    def _build_bar(self, form):
        """Native bar at the bottom of the window: Back, a button for each shop, Installed & updates, status."""
        try:
            import clr
            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Drawing")
            from System import Action
            from System.Windows.Forms import Panel, Button, Label, DockStyle, FlatStyle, AnchorStyles
            from System.Drawing import Color, Font, ContentAlignment
            dark, gold, edge, light = (Color.FromArgb(1, 10, 19), Color.FromArgb(200, 170, 110),
                                       Color.FromArgb(120, 90, 40), Color.FromArgb(240, 230, 210))
            bar = Panel()
            bar.Dock = DockStyle.Bottom
            bar.Height = 36
            bar.BackColor = dark
            x = 8
            buttons = [("◀ Back", 80, lambda: self.window.evaluate_js("history.back()"))]
            buttons += [(label, 100, lambda home=home: self.window.load_url(home)) for label, home, _host in SHOPS.values()]
            buttons += [("Installed && updates", 150, self.show_installed)]
            for text, width, action in buttons:
                b = Button()
                b.Text = text
                b.FlatStyle = FlatStyle.Flat
                b.FlatAppearance.BorderColor = edge
                b.ForeColor = gold
                b.BackColor = dark
                b.Font = Font("Segoe UI", 9)
                b.SetBounds(x, 5, width, 26)
                # Clicks run on the UI thread; pywebview calls must not block it
                b.Click += lambda s, e, a=action: threading.Thread(target=a, daemon=True).start()
                bar.Controls.Add(b)
                x += width + 8
            label = Label()
            label.ForeColor = light
            label.BackColor = dark
            label.Font = Font("Segoe UI", 9)
            label.TextAlign = ContentAlignment.MiddleRight
            label.SetBounds(x, 8, max(form.ClientSize.Width - x - 12, 100), 20)
            label.Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top
            bar.Controls.Add(label)
            form.Controls.Add(bar)
            self._form, self._status_label, self._Action = form, label, Action
        except Exception as e:
            log.error(f"[ModStore] Could not build the bar: {e}")

    def run(self):
        webview.start(
            private_mode=False,
            storage_path=str(get_user_data_dir() / "store-webview"),
        )


def main():
    ModStore().run()


if __name__ == "__main__":
    main()

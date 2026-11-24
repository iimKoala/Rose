#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mod Store message handlers
Mixed into MessageHandler; kept separate so the mod store code stays in a small file.
"""

import base64
import hashlib
import io
import json
import logging
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from utils.core.paths import get_user_data_dir
from utils.core.utilities import get_champion_id_from_skin_id

log = logging.getLogger(__name__)

# What the Installed page asks for again every time it opens, kept while the file it was made from is unchanged
_THUMBNAILS: dict = {}  # file stamp -> the picture's data URI (24 pictures took 1.2 s to make again, Nov 13)
_VERDICTS: dict = {}  # (the mod's file stamp, the game's stamp) -> check_mod's answer (24 mods took about 20 s)
_KEPT_ANSWERS = 256  # of each; a changed file leaves its old answer behind, so start over past this


def _file_stamp(path: Path) -> tuple:
    """(path, size, time of the last change): an answer about a file holds while this stays the same"""
    stat = Path(path).stat()
    return str(path), stat.st_size, stat.st_mtime_ns


def _keep(answers: dict, stamp, answer):
    if len(answers) >= _KEPT_ANSWERS:
        answers.clear()
    answers[stamp] = answer
    return answer


def store_downloads_dir() -> Path:
    """Return the store-downloads directory under Rose's user data, creating it if missing."""
    d = get_user_data_dir() / "store-downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def mod_file_name(name) -> str:
    """The store's mod name as a safe Windows file name, without extension; "" if nothing usable is left"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(name or ""))  # characters Windows refuses, folder separators included
    name = " ".join(name.split()).strip(" .")
    if not name or name.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        return ""
    return name[:100].strip(" .")


class ModStoreHandlersMixin:
    """Mod Store handlers. Needs self._send_response(message: str) from MessageHandler."""

    def _route_mod_store_message(self, payload_type: str, payload: dict) -> bool:
        """Handle a mod-store-* message. Returns False if the type isn't a mod store message."""
        routes = {
            "mod-store-install": self._handle_mod_store_install,
            "mod-store-skins": self._handle_mod_store_skins,
            "mod-store-champions": self._handle_mod_store_champions,
            "mod-store-installed": self._handle_mod_store_installed,
            "mod-store-check": self._handle_mod_store_check,
            "mod-store-health": self._handle_mod_store_health,
            "mod-store-fix": self._handle_mod_store_fix,
            "mod-store-open": self._handle_mod_store_open,
            "mod-store-delete": self._handle_mod_store_delete,
            "mod-store-rename": self._handle_mod_store_rename,
        }
        handler = routes.get(payload_type)
        if handler is None:
            return False
        handler(payload)
        return True

    def _send_mod_store_response(self, request: dict, payload: dict) -> None:
        """Send a response back to the plugin via WebSocket."""
        payload['requestId'] = request.get('requestId')
        self._send_response(json.dumps(payload))

    def _store_download_path(self, raw) -> Path | None:
        """Return a Path only if raw names an existing .fantome/.modpkg/.zip file inside store_downloads_dir()."""
        p = Path(raw)
        if not p.is_file():
            log.warning("Store download path refused: %s (not a file)", raw)
            return None
        try:
            if not p.resolve().is_relative_to(store_downloads_dir().resolve()):
                log.warning("Store download path refused: %s (outside store-downloads)", raw)
                return None
        except (OSError, ValueError):
            log.warning("Store download path refused: %s", raw)
            return None
        if p.suffix not in (".fantome", ".modpkg", ".zip"):
            log.warning("Store download path refused: %s (bad suffix)", raw)
            return None
        return p

    def _handle_mod_store_check(self, payload: dict) -> None:
        """LTK Manager's check on a fresh store download, before the user is asked where it goes.

        A mod LTK Manager would turn off is deleted and answered with the reason, so nobody picks a skin
        for a mod that can't be played. "health" None: the check didn't run (champion select, a game,
        LTK Manager missing); the install checks again anyway.

        The skinhack rule alone does not delete it here: the download is still as its author made it, and
        the install matches a champion skin to the base skin (_fix_base_skin) before LTK Manager's rules
        judge it, as adding the same file by hand does. A mod the rule still stands on after that is
        removed by the install (_check_imported_mods). The answer then has "baseSkinPending": True.
        """
        try:
            file = self._store_download_path(payload.get("file"))
            if file is None:
                self._send_mod_store_response(payload, {"type": "mod-store-check-response", "success": False, "error": "Only files the mod store downloaded can be checked"})
                return
            injection_manager = getattr(self, "injection_manager", None)
            overlay = getattr(getattr(injection_manager, "injector", None), "overlay_manager", None)
            phase = getattr(getattr(self, "shared_state", None), "phase", None)
            busy = phase in getattr(self, "_MOD_CHECK_BUSY_PHASES", ()) or bool(getattr(injection_manager, "_injection_in_progress", False))
            result = overlay.check_mod(file, file.stem) if overlay is not None and not busy else None
            problems = (result or {}).get("problems") or []
            pending = False
            if problems:
                from pengu.communication.message_handler import SKINHACK_RULE, _rejected_import
                # What the install's base-skin fix does not change: these decide here
                final = [problem for problem in problems if problem.get("rule") != SKINHACK_RULE]
                if final:
                    error = _rejected_import({"fileName": file.name}, {**result, "problems": final})["error"]
                    file.unlink(missing_ok=True)
                    log.warning("Store download %s not kept: %s", file.name, error)
                    self._send_mod_store_response(payload, {"type": "mod-store-check-response", "success": False, "error": error})
                    return
                pending = True
                log.info("Store download %s kept for the install: LTK Manager's skinhack rule is judged again "
                         "once the skin is matched to the base skin", file.name)
            answer = {"type": "mod-store-check-response", "success": True, "health": result}
            if pending:
                answer["baseSkinPending"] = True
            self._send_mod_store_response(payload, answer)
        except Exception as e:
            log.exception("mod-store-check failed")
            self._send_mod_store_response(payload, {"type": "mod-store-check-response", "success": False, "error": str(e)})

    def _handle_mod_store_install(self, payload: dict) -> None:
        """Install a mod from the store into the saved-mods system."""
        path = None
        try:
            path = self._store_download_path(payload.get("file") or "")
            if path is None:
                self._send_mod_store_response(payload, {"type": "mod-store-install-response", "success": False, "error": "Only files the mod store downloaded can be installed"})
                return

            kind = payload.get("kind")
            origin = dict(payload.get("origin") or {})
            # RuneForge names the download by a file id: store the mod under its own name (Nov 9 request)
            clean = mod_file_name(origin.get("name"))
            named = path.with_name(clean + path.suffix)
            if clean and not named.exists():
                path = path.rename(named)
            errors = []

            if kind == "champion":
                try:
                    champion_id = int(payload.get("championId"))
                except (TypeError, ValueError):
                    self._send_mod_store_response(payload, {"type": "mod-store-install-response", "success": False, "error": "Pick a champion first"})
                    return
                skin_ids = [int(s) for s in payload.get("skinIds") or []]
                added = self.mod_storage.import_mod_file(champion_id, path, skin_ids)
                item = {
                    "fileName": path.name,
                    "path": str(added.identity_path),
                    "relativePath": added.identity_path.relative_to(self.mod_storage.mods_root).as_posix(),
                    "modName": added.name,
                    "savedAlready": added.nothing_added,
                    "targetManifest": str(self.mod_storage.get_champion_dir(champion_id) / self.mod_storage.TARGET_METADATA),
                }
                remove = lambda it: self.mod_storage.delete_champion_mod(champion_id, mod_name=it["modName"])
                skins = True
                saved_kind = "skins"
            elif kind == "category":
                category = payload.get("category")
                if category not in self.mod_storage.MOD_CATEGORIES:
                    self._send_mod_store_response(payload, {"type": "mod-store-install-response", "success": False, "error": f"Unknown category: {category}"})
                    return
                added = self.mod_storage.import_category_mod_file(category, path)
                item = {
                    "fileName": path.name,
                    "path": str(added.identity_path),
                    "relativePath": added.identity_path.relative_to(self.mod_storage.mods_root).as_posix(),
                    "modName": added.name,
                    "savedAlready": added.nothing_added,
                }
                remove = lambda it: self.mod_storage.delete_category_mod(category, it["modName"])
                skins = False
                saved_kind = category
            else:
                self._send_mod_store_response(payload, {"type": "mod-store-install-response", "success": False, "error": "Unknown kind"})
                return

            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            kept = self._check_imported_mods([item], errors, remove, skins=skins)

            replaced = 0
            if kept:
                new_path = Path(kept[0]["path"])
                self.mod_storage.write_origin(new_path, {**origin, "installedAt": datetime.now(timezone.utc).isoformat(), "sha256": sha256})
                replaced = self._remove_older_store_copies(new_path, origin, remove, saved_kind)
                if clean and added.name != clean:
                    # Its name was taken (an older copy, removed just now): show the mod's own name, not "... (2)"
                    try:
                        if kind == "champion":
                            self.mod_storage.set_champion_mod_display_name(champion_id, origin["name"], relative_path=item["relativePath"])
                        else:
                            self.mod_storage.set_category_mod_display_name(category, added.name, origin["name"])
                    except ValueError as e:
                        log.warning("Couldn't name %s after the mod: %s", added.name, e)

            self._send_mod_store_response(payload, {"type": "mod-store-install-response", "success": bool(kept), "modName": item["modName"], "health": kept[0].get("health") if kept else None, "replaced": replaced, "error": errors[0]["error"] if errors else None})
        except Exception as e:
            log.exception("mod-store-install failed")
            self._send_mod_store_response(payload, {"type": "mod-store-install-response", "success": False, "error": str(e)})
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    def _remove_older_store_copies(self, new_path: Path, origin: dict, remove, kind: str) -> int:
        """Update = Install again: once the new copy passed LTK Manager's check, remove earlier copies of the same store mod."""
        slug = origin.get("slug")
        if not slug:
            return 0
        removed = 0
        for mod in self.mod_storage.saved_mods(kind):
            old = mod.path(self.mod_storage.mods_root)
            if old == new_path:
                continue
            try:
                note = self.mod_storage.read_origin(old)
                if not note or note.get("source") != origin.get("source") or note.get("slug") != slug:
                    continue
                if remove({"modName": mod.name}):
                    removed += 1
                    log.info("Replaced older copy %s", mod.name)
                    old.with_suffix(self.mod_storage.ORIGIN_SIDECAR_SUFFIX).unlink(missing_ok=True)
            except Exception as e:
                log.warning("Couldn't remove older copy %s: %s", mod.name, e)
        return removed

    def _store_mods(self) -> list:
        """(saved mod, store note) for each mod installed from the store."""
        root = self.mod_storage.mods_root
        found = []
        for mod in self.mod_storage.saved_mods():
            note = self.mod_storage.read_origin(mod.path(root))
            if note:
                found.append((mod, note))
        return found

    def _store_overlay(self):
        """The overlay manager that runs Rose's checker; raises why it can't run now."""
        overlay = getattr(getattr(getattr(self, "injection_manager", None), "injector", None), "overlay_manager", None)
        if overlay is None or getattr(overlay, "game_dir", None) is None:
            raise RuntimeError("Rose doesn't know League's folder yet: open League once")
        if self._ltk_wanted_by_game():
            raise RuntimeError("Not during champion select or a game")
        return overlay

    def _handle_mod_store_health(self, payload: dict) -> None:
        """Whether each mod installed from the store still works with this patch: LTK Manager's rules
        (rose-mod-check), repairing nothing. A mod LTK Manager holds has no copy in Rose to check ("ltk")."""
        try:
            overlay = self._store_overlay()

            def verdict(found) -> dict:
                mod, note = found
                entry = {"slug": note.get("slug"), "identity": mod.identity, "modName": mod.name}
                if mod.rose_copy is None:
                    entry["health"] = "ltk"
                else:
                    entry.update(self._store_verdict(overlay, mod))
                return entry

            # 3 checks at once: the user's 6 mods took 9.4 s one after another, 2.6 s this way (Nov 10)
            with ThreadPoolExecutor(max_workers=3) as pool:
                mods = list(pool.map(verdict, self._store_mods()))
            self._send_mod_store_response(payload, {"type": "mod-store-health-response", "success": True, "mods": mods})
        except Exception as e:
            log.warning("mod-store-health failed: %s", e)
            self._send_mod_store_response(payload, {"type": "mod-store-health-response", "success": False, "error": str(e)})

    @staticmethod
    def _store_verdict(overlay, mod) -> dict:
        """check_mod's answer for a mod as it is (no repair). An archive's answer is kept until the archive
        or the game's program changes (a repair, an update, a patch); a mod stored as a folder, and a check
        that did not run, are asked again every time."""
        stamp = None
        try:
            if mod.rose_copy.is_file():
                game = Path(overlay.game_dir) / "League of Legends.exe"
                stamp = (_file_stamp(mod.rose_copy), _file_stamp(game) if game.is_file() else None)
        except OSError:
            stamp = None
        if stamp is not None and stamp in _VERDICTS:
            return dict(_VERDICTS[stamp])
        result = overlay.check_mod(mod.rose_copy, mod.name, repair=False)
        if result is None:
            return {"health": "unknown"}
        return dict(result if stamp is None else _keep(_VERDICTS, stamp, result))

    def _handle_mod_store_fix(self, payload: dict) -> None:
        """Repair one mod installed from the store in place, as an install does (rose-mod-check)."""
        try:
            overlay = self._store_overlay()
            identity = str(payload.get("identity") or "")
            mod = next((m for m, _ in self._store_mods() if m.identity == identity), None)
            if mod is None:
                raise RuntimeError("This mod is no longer installed")
            if mod.rose_copy is None:
                raise RuntimeError("LTK Manager holds this mod: update it from the store to replace it")
            from injection.baseskin.library import stored_skin_rewrite
            with stored_skin_rewrite():
                result = overlay.check_mod(mod.rose_copy, mod.name)
                if result and result.get("repaired"):
                    self.mod_storage.refresh_mod_hashes(mod.rose_copy)
            if result is None:
                raise RuntimeError("The checker didn't run (see Rose's log)")
            self._send_mod_store_response(payload, {"type": "mod-store-fix-response", "success": True, **result})
        except Exception as e:
            log.warning("mod-store-fix failed: %s", e)
            self._send_mod_store_response(payload, {"type": "mod-store-fix-response", "success": False, "error": str(e)})

    def _handle_mod_store_open(self, payload: dict) -> None:
        """Open the Mod store window from the client's nav bar button, as the tray menu does."""
        try:
            from main.account_gui import open_mod_store
            open_mod_store()
            self._send_mod_store_response(payload, {"type": "mod-store-open-response", "success": True})
        except Exception as e:
            log.warning("mod-store-open failed: %s", e)
            self._send_mod_store_response(payload, {"type": "mod-store-open-response", "success": False, "error": str(e)})

    def _store_thumbnail(self, mod) -> str:
        """The mod's picture, small, as a PNG data URI ("" when it has none): its image beside the
        manifest, else META/image.png in Rose's copy. Re-encoded, so the page never gets the mod's own file.
        Kept until the file it was made from changes."""
        try:
            source = next((path for path in mod.image_paths() if path.exists()), None)
            origin = source or mod.rose_copy  # the file the picture is read from
            if origin is None:
                return ""
            stamp = _file_stamp(origin)
            if stamp not in _THUMBNAILS:
                _keep(_THUMBNAILS, stamp, self._make_thumbnail(source, mod.rose_copy))
            return _THUMBNAILS[stamp]
        except Exception as e:  # a picture must never break the list
            log.debug("No picture for %s: %s", mod.name, e)
            return ""

    @staticmethod
    def _make_thumbnail(source, rose_copy) -> str:
        if source is not None:
            data = source.read_bytes()
        elif zipfile.is_zipfile(rose_copy):
            with zipfile.ZipFile(rose_copy) as archive:
                name = next((n for n in archive.namelist() if n.lower() in ("meta/image.png", "meta/image.jpg")), None)
                if name is None or archive.getinfo(name).file_size > 20 * 1024 * 1024:
                    return ""
                data = archive.read(name)
        else:
            return ""
        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail((144, 144))
            out = io.BytesIO()
            image.convert("RGBA").save(out, "PNG")
        return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")

    def _handle_mod_store_delete(self, payload: dict) -> None:
        """Delete one mod installed from the store (the Installed list's Delete button), and its store note."""
        try:
            if self._ltk_wanted_by_game():
                raise RuntimeError("Not during champion select or a game")
            identity = str(payload.get("identity") or "")
            mod = next((m for m, _ in self._store_mods() if m.identity == identity), None)
            if mod is None:
                raise RuntimeError("This mod is no longer installed")
            if mod.kind == self.mod_storage.CATEGORY_SKINS:
                deleted = self.mod_storage.delete_champion_mod(get_champion_id_from_skin_id(mod.storage_id),
                                                               relative_path=mod.identity)
            else:
                deleted = self.mod_storage.delete_category_mod(mod.kind, mod.name)
            if not deleted:
                raise RuntimeError("Rose could not delete it (see Rose's log)")
            mod.path(self.mod_storage.mods_root).with_suffix(self.mod_storage.ORIGIN_SIDECAR_SUFFIX).unlink(missing_ok=True)
            log.info("Deleted store mod %s", mod.name)
            self._send_mod_store_response(payload, {"type": "mod-store-delete-response", "success": True, "modName": mod.name})
        except Exception as e:
            log.warning("mod-store-delete failed: %s", e)
            self._send_mod_store_response(payload, {"type": "mod-store-delete-response", "success": False, "error": str(e)})

    def _handle_mod_store_rename(self, payload: dict) -> None:
        """Rename one mod installed from the store (the Installed list's Rename button): the name Rose shows,
        there and in its own mod lists. Only its manifest entry changes, as with Rose's own rename."""
        try:
            identity = str(payload.get("identity") or "")
            mod = next((m for m, _ in self._store_mods() if m.identity == identity), None)
            if mod is None:
                raise RuntimeError("This mod is no longer installed")
            new_name = str(payload.get("newName") or "")
            if mod.kind == self.mod_storage.CATEGORY_SKINS:
                champion_id = get_champion_id_from_skin_id(mod.storage_id)
                display_name = self.mod_storage.set_champion_mod_display_name(champion_id, new_name, relative_path=mod.identity)
                # a skin mod that is selected right now shows its new name too
                self._sync_selected_custom_mod_display_name(champion_id, mod.identity, mod.name, display_name)
            else:
                display_name = self.mod_storage.set_category_mod_display_name(mod.kind, mod.name, new_name)
            log.info("Renamed store mod %s to %s", mod.name, display_name)
            self._send_mod_store_response(payload, {"type": "mod-store-rename-response", "success": True, "displayName": display_name})
        except Exception as e:
            log.warning("mod-store-rename failed: %s", e)
            self._send_mod_store_response(payload, {"type": "mod-store-rename-response", "success": False, "error": str(e)})

    def _handle_mod_store_skins(self, payload: dict) -> None:
        """List available skins from the mod store."""
        from lcu.core.client import LCU
        try:
            try:
                champion_id = int(payload.get("championId"))
            except (TypeError, ValueError):
                self._send_mod_store_response(payload, {"type": "mod-store-skins-response", "success": False, "error": "Pick a champion first"})
                return
            client = LCU()
            if not client.ok:
                self._send_mod_store_response(payload, {"type": "mod-store-skins-response", "success": False, "error": "Open League to choose skins"})
                return
            data = client.get(f"/lol-game-data/assets/v1/champions/{champion_id}.json")
            if not data or "skins" not in data:
                self._send_mod_store_response(payload, {"type": "mod-store-skins-response", "success": False, "error": "Failed to load skins"})
                return
            skins = [{"id": s["id"], "name": s["name"]} for s in data["skins"] if s.get("id")]
            self._send_mod_store_response(payload, {"type": "mod-store-skins-response", "success": True, "skins": skins})
        except Exception as e:
            log.exception("mod-store-skins failed")
            self._send_mod_store_response(payload, {"type": "mod-store-skins-response", "success": False, "error": str(e)})

    def _handle_mod_store_champions(self, payload: dict) -> None:
        """List available champions from the mod store."""
        from lcu.core.client import LCU
        try:
            client = LCU()
            if not client.ok:
                self._send_mod_store_response(payload, {"type": "mod-store-champions-response", "success": False, "error": "Open League to choose a champion"})
                return
            data = client.get("/lol-game-data/assets/v1/champion-summary.json")
            if not data:
                self._send_mod_store_response(payload, {"type": "mod-store-champions-response", "success": False, "error": "Failed to load champions"})
                return
            champions = [{"id": c["id"], "name": c["name"], "alias": c.get("alias", "")} for c in data if c.get("id", 0) > 0]
            self._send_mod_store_response(payload, {"type": "mod-store-champions-response", "success": True, "champions": champions})
        except Exception as e:
            log.exception("mod-store-champions failed")
            self._send_mod_store_response(payload, {"type": "mod-store-champions-response", "success": False, "error": str(e)})

    def _handle_mod_store_installed(self, payload: dict) -> None:
        """List installed store mods from the saved-mods system."""
        try:
            mods = []
            for mod in self.mod_storage.saved_mods():
                note_path = mod.path(self.mod_storage.mods_root)
                try:
                    note = self.mod_storage.read_origin(note_path)
                except Exception:
                    continue
                if not note:
                    continue
                mods.append({
                    **note,
                    "modName": mod.name,
                    "storedFile": str(mod.rose_copy) if mod.rose_copy else "",
                    "inLtkManager": bool(mod.ltk_id),
                    "identity": mod.identity,
                    "kind": mod.kind,
                    "displayName": mod.display_name or "",  # the name the user gave it in Rose; "" when none
                    "image": self._store_thumbnail(mod),
                })
            self._send_mod_store_response(payload, {"type": "mod-store-installed-response", "success": True, "mods": mods})
        except Exception as e:
            log.exception("mod-store-installed failed")
            self._send_mod_store_response(payload, {"type": "mod-store-installed-response", "success": False, "error": str(e)})

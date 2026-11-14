"""Rose's account window: main/account_web/ in a pywebview window, run as its own program (python -m main.account_window), because pywebview needs the main thread."""

import json
import logging

from pathlib import Path

from main.account_login import switch_in_background
from main.account_manager import get_account_manager
from main import account_import
from main.account_import import password_problem, username_problem
from main.account_secrets import get_password, set_password
import webview


class Api:
    def __init__(self):
        self._window = None
        self._maximized = False

    def list_accounts(self):
        """Every saved account for the page. Never a password: only whether one is saved."""
        return [{
            "id": a.id, "riotId": a.riot_id, "username": a.username, "region": a.region,
            "tier": a.tier, "division": a.division, "lp": a.lp, "level": a.level, "note": a.note,
            "lastSeason": a.last_season, "isActive": a.is_active, "hasPassword": bool(get_password(a.id)),
            "loginError": a.login_error,
        } for a in get_account_manager().get_all_accounts()]

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def save_account(self, account_id, username, password, region, note):
        """Add (empty account_id) or edit an account, like the old account form. The password goes only to
        Windows Credential Manager: never logged, never returned, never in accounts.json."""
        manager = get_account_manager()
        username = (username or "").strip()
        region = (region or "").strip() or "NA"
        note = (note or "").strip()
        if username_problem(username):
            return {"ok": False, "error": username_problem(username)}
        if password and password_problem(password):
            return {"ok": False, "error": password_problem(password)}
        account = manager.get_account(account_id) if account_id else None
        if account_id and account is None:
            return {"ok": False, "error": "That account no longer exists"}
        if account is None and not password:
            return {"ok": False, "error": "Password is required"}
        other = manager.find_by_username(username)
        if other and (account is None or other.id != account.id):
            return {"ok": False, "error": "An account with that login username is already saved"}
        renamed = account is not None and account.username.lower() != username.lower()
        if account is not None:
            if not manager.update_account(account.id, username, region, note):
                return {"ok": False, "error": "That account was changed or removed in the meantime. Close the form and try again."}
            saved = account
        else:
            saved = manager.add_account(username, region=region, note=note)
        if password:
            set_password(saved.id, password)
        if password or renamed:
            manager.set_login_error(saved.id, "")
        return {"ok": True}

    def remove_account(self, account_id):
        """Remove an account; AccountManager.remove_account deletes its saved password too"""
        return {"ok": bool(get_account_manager().remove_account(account_id))}

    def _pick_file(self, dialog_type, **options):
        """The file the user picked in pywebview's dialog, or None if cancelled (private: not visible to the page)"""
        result = self._window.create_file_dialog(dialog_type, **options)
        if not result:
            return None
        return Path(result[0] if isinstance(result, (list, tuple)) else result)

    def export_accounts(self):
        """Export every account WITH its password (the user's choice) to a text file Import can read back.
        The passwords go only into the file the user picks, never to the page."""
        accounts = get_account_manager().get_all_accounts()
        if not accounts:
            return {"ok": False, "error": "No accounts to export"}
        path = self._pick_file(webview.FileDialog.SAVE, save_filename="rose_accounts.txt", file_types=("Text files (*.txt)",))
        if path is None:
            return {"ok": False, "cancelled": True}
        try:
            count = account_import.export_accounts(path, accounts, get_password, True)
        except OSError as e:
            return {"ok": False, "error": f"Could not export: {e}"}
        return {"ok": True, "count": count, "path": str(path)}

    def import_accounts(self, region):
        """Import username:password lines from a text file; lines without a region get this one"""
        region = (region or "NA").strip().upper()
        if region not in account_import.REGIONS:
            return {"ok": False, "error": f"Unknown region: {region}"}
        path = self._pick_file(webview.FileDialog.OPEN, file_types=("Text files (*.txt)", "All files (*.*)"))
        if path is None:
            return {"ok": False, "cancelled": True}
        try:
            result = account_import.import_accounts(path, get_account_manager(), set_password, region)
        except (OSError, UnicodeError) as e:
            return {"ok": False, "error": f"Could not import the file: {e}"}
        return {"ok": True, "added": result.added, "skipped": len(result.skipped),
                "skippedFile": str(result.skipped_file) if result.skipped_file else ""}

    def open_mod_store(self):
        """Open the mod store window (one store at a time)"""
        from main.account_gui import open_mod_store
        open_mod_store()
        return {"ok": True}

    def log_in(self, account_id):
        def progress(message):
            self._window.evaluate_js("setStep(" + json.dumps(message) + ")")

        def done(ok, message):
            self._window.evaluate_js("finishLogin(" + json.dumps(ok) + ", " + json.dumps(message) + ")")

        switch_in_background(account_id, progress, done)
        return {"ok": True}

    def close(self):
        self._window.destroy()


def main():
    api = Api()
    window = webview.create_window(
        "Rose - Accounts",
        url=str(Path(__file__).parent / "account_web" / "index.html"),
        js_api=api,
        width=1200,
        height=760,
        min_size=(960, 600),
        frameless=True,
        easy_drag=False,
        background_color="#010a13",
    )
    api._window = window
    # The sign-in code logs to Rose's "tracer" logger; in this program it goes to logs/account_window_*.log
    from utils.core.logging import get_named_logger
    window_log = get_named_logger("account_window", "account_window", "verbose")
    tracer = logging.getLogger("tracer")
    tracer.setLevel(logging.DEBUG)
    for handler in window_log.handlers:
        tracer.addHandler(handler)
    webview.start(http_server=True)


if __name__ == "__main__":
    main()

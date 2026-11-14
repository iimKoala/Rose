# -*- coding: utf-8 -*-
"""
Account Login - switch the Riot Client to a saved account.

Riot has no official way for an app to sign in for you, so this signs the Riot
Client out through its local API and types the saved login into its sign-in
window (pywinauto). It breaks if Riot changes that window, and it can't answer
two-factor prompts: the user finishes those in the Riot Client.
"""

import ctypes
import json
import os
import subprocess
import threading
import time
import warnings
from pathlib import Path
from typing import Callable, Optional

import psutil
import requests
import urllib3

from utils.core.logging import get_logger
from main.account_manager import get_account_manager
from main.account_secrets import get_password

log = get_logger()

GAME_PROCESS = "League of Legends.exe"
LEAGUE_CLIENT_PROCESSES = {"LeagueClient.exe", "LeagueClientUx.exe", "LeagueClientUxRender.exe"}
RIOT_CLIENT_PROCESSES = {"RiotClientServices.exe", "Riot Client.exe", "RiotClientCrashHandler.exe"}
RIOT_CLIENT_LOCKFILE = Path(os.environ.get("LOCALAPPDATA", "")) / "Riot Games" / "Riot Client" / "Config" / "lockfile"
RIOT_CLIENT_INSTALLS = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Riot Games" / "RiotClientInstalls.json"
RIOT_CLIENT_FALLBACK = Path(r"C:\Riot Games\Riot Client\RiotClientServices.exe")
LAUNCH_LEAGUE_ARGS = ["--launch-product=league_of_legends", "--launch-patchline=live"]
LAUNCH_LEAGUE_PATH = "/product-launcher/v1/products/league_of_legends/patchlines/live"  # the Play button
ELIGIBILITY_PATH = LAUNCH_LEAGUE_PATH + "/eligibility"  # 2xx once League can launch for the signed-in player
LEAGUE_SIGN_IN_PATH = "/rso-auth/v2/authorizations/lol"  # League's own sign-in in the Riot Client (clientId lol)
LEAGUE_SIGN_IN_REQUEST_PATH = "/rso-auth/v2/authorizations"  # asks the Riot Client to make a sign-in for a client
LEAGUE_SIGN_IN_REQUEST = {  # what League's own sign-in has (Riot Client, Nov 10)
    "clientId": "lol",
    "scope": ["openid", "offline_access", "lol", "ban", "account", "lol_region", "summoner"],
}

_switch_lock = threading.Lock()  # one switch at a time


# ------------------------------------------------------------------ Riot Client local API
def _riot_client_exe() -> Path:
    """RiotClientServices.exe path from RiotClientInstalls.json, else the default install path"""
    try:
        data = json.loads(RIOT_CLIENT_INSTALLS.read_text(encoding="utf-8"))
        path = Path(data.get("rc_default") or "")
        if path.is_file():
            return path
    except Exception as e:
        log.debug(f"[AccountLogin] Could not read RiotClientInstalls.json: {e}")
    return RIOT_CLIENT_FALLBACK


def _rc_request(method: str, path: str, timeout: float = 5.0, body: Optional[dict] = None) -> Optional[requests.Response]:
    """Call the Riot Client's local API (localhost only), with an optional JSON body. None if the client isn't running."""
    try:
        name, pid, port, password, protocol = RIOT_CLIENT_LOCKFILE.read_text(encoding="utf-8").strip().split(":")
    except (OSError, ValueError):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            # Self-signed cert on 127.0.0.1 only, same as Rose's LCU connection (lcu_connection.py)
            return requests.request(method, f"{protocol}://127.0.0.1:{port}{path}", json=body,
                                    auth=("riot", password), verify=False, timeout=timeout)
    except requests.RequestException:
        return None


def _riot_client_running() -> bool:
    return _rc_request("GET", "/rso-auth/v1/authorization") is not None


def _signed_in() -> bool:
    response = _rc_request("GET", "/rso-auth/v1/authorization")
    return response is not None and response.status_code == 200


def _signed_in_account() -> Optional[tuple[str, str]]:
    """(login username, Riot ID) the Riot Client is signed in as, or None if signed out or not ready"""
    if not _signed_in():
        return None
    response = _rc_request("GET", "/riot-client-auth/v1/userinfo")
    if response is None or not response.ok:
        return None
    try:
        info = response.json()
    except ValueError:
        return None
    acct = info.get("acct") or {}
    riot_id = f"{acct['game_name']}#{acct.get('tag_line', '')}" if acct.get("game_name") else ""
    return info.get("preferred_username") or "", riot_id


def _is_signed_in_as(account) -> bool:
    """True if the Riot Client is signed in to this saved account (login username or Riot ID matches)"""
    signed = _signed_in_account()
    if not signed:
        return False
    username, riot_id = signed
    return bool((username and username.lower() == (account.username or "").lower())
                or (riot_id and account.riot_id and riot_id.lower() == account.riot_id.lower()))


def _signed_in_puuid() -> str:
    """The player (puuid) the Riot Client is signed in as, or "" if unknown"""
    session = _rc_request("GET", "/player-session-lifecycle/v1/session")
    try:
        return (session.json().get("puuid") or "") if session is not None and session.ok else ""
    except ValueError:
        return ""


def _forget_league_sign_in() -> None:
    """Delete League's own sign-in so the next League signs in as the Riot Client's player.

    Only while League is closed: a running League would be signed out.
    """
    if _league_client_running():
        return
    response = _rc_request("DELETE", LEAGUE_SIGN_IN_PATH)
    log.info(f"[AccountLogin] Cleared League's old sign-in: {response.status_code if response is not None else 'no response'}")


def _make_league_sign_in() -> None:
    """Have the Riot Client make League's sign-in for its player now, before Play.

    On a good start the Riot Client makes it as League opens ("Using direct token exchange", then "UserInfo for
    clientId: lol" in its log). After a switch it sometimes doesn't, and League waits forever for its login
    ("unknown player", Nov 10: 2 of 4). Only the answer's type is read: the rest holds League's tokens.
    """
    response = _rc_request("POST", LEAGUE_SIGN_IN_REQUEST_PATH, body=LEAGUE_SIGN_IN_REQUEST)
    try:
        kind = response.json().get("type") if response is not None and response.ok else None
    except (ValueError, AttributeError):
        kind = None
    status = response.status_code if response is not None else "no response"
    log.info(f"[AccountLogin] Made League's sign-in: {status} ({kind or 'no type'})")


def _auth_state() -> dict:
    """The Riot Client's sign-in screen: type, error, retryAfter, timestamp only (never tokens); {} if unknown"""
    response = _rc_request("GET", "/rso-authenticator/v1/authentication")
    try:
        body = response.json() if response is not None and response.ok else {}
    except ValueError:
        return {}
    if not isinstance(body, dict):
        return {}
    return {key: body.get(key) for key in ("type", "error", "retryAfter", "timestamp")}


def _sign_in_problem(before: dict) -> Optional[str]:
    """A message if the Riot Client refused this sign-in, else None (keep waiting).

    Riot has answered once the timestamp changes. Seen live on Nov 9 (Riot Client v142): a wrong username or
    password gives type "auth" (back on the sign-in form) with an EMPTY error and a new timestamp; the reason
    is only on screen. Two-factor is type "multifactor": keep waiting.
    shortcut: rate_limited and auth_failure come from RiotGamesApi.dll, not seen live; a captcha puzzle might also look like this, check if a user reports it.
    """
    state = _auth_state()
    if not state or state.get("timestamp") == before.get("timestamp"):
        return None  # Riot hasn't answered this sign-in yet
    error = state.get("error") or ""
    if error == "rate_limited":
        wait = state.get("retryAfter")
        return "Riot says there were too many sign-in attempts. " + (f"Try again in {wait} seconds." if isinstance(wait, int) else "Wait a few minutes.")
    if error == "auth_failure" or (not error and state.get("type") == "auth"):
        return "Wrong username or password for this account. Edit it in Rose's account window."
    return None


def _sign_out() -> None:
    """Sign the Riot Client out, as its own Sign Out does"""
    for path, timeout in (
        # Ends the session, "stay signed in" included; it can take several seconds to answer.
        # If it doesn't finish, "stay signed in" signs the old account straight back in.
        ("/player-session-lifecycle/v1/session", 20.0),
        ("/rso-auth/v1/authorization", 5.0),  # forget the sign-in tokens
        ("/rso-auth/v1/session", 5.0),  # drop the login session (404 when there is none)
        # League's own sign-in survives the three above, and a new League reuses it (Nov 9: Riot Client on one account, League on another)
        (LEAGUE_SIGN_IN_PATH, 5.0),
    ):
        response = _rc_request("DELETE", path, timeout=timeout)
        if response is None:  # the client sometimes drops the connection mid-sign-out: ask once more
            time.sleep(1.0)
            response = _rc_request("DELETE", path, timeout=timeout)
        log.info(f"[AccountLogin] Sign-out {path}: {response.status_code if response is not None else 'no response'}")


def _sign_out_and_stay_out() -> bool:
    """Sign out, and once more if "stay signed in" signs the old account straight back in"""
    for _ in range(2):
        _sign_out()
        if _wait(lambda: not _signed_in(), 20) and not _wait(_signed_in, 3):
            return True
        log.info("[AccountLogin] The Riot Client signed itself back in; signing out again")
    return False


def _wait(condition: Callable[[], bool], timeout: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


# ------------------------------------------------------------------ processes
def game_in_progress() -> bool:
    """True while a game runs or waits for a reconnect: switching then would leave the game"""
    if any(p.info["name"] == GAME_PROCESS for p in psutil.process_iter(["name"])):
        return True
    try:
        from lcu.core.client import LCU
        lcu = LCU()
        return bool(lcu.ok and lcu.phase in ("InProgress", "Reconnect"))
    except Exception:
        return False


def _close_league_client(timeout: float = 20.0) -> None:
    procs = [p for p in psutil.process_iter(["name"]) if p.info["name"] in LEAGUE_CLIENT_PROCESSES]
    if procs:
        # Close League the way the Riot Client does, so its launch session ends too. A League that is only
        # killed leaves the Riot Client thinking it's still "already launched".
        response = _rc_request("DELETE", LAUNCH_LEAGUE_PATH, timeout=10.0)
        log.info(f"[AccountLogin] Close League request: {response.status_code if response is not None else 'no response'}")
        _, procs = psutil.wait_procs(procs, timeout=15)
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass
    _remove_stale_league_lockfile()


def _remove_stale_league_lockfile() -> None:
    """A closed League client leaves its lockfile; Rose would keep retrying that dead port until League restarts"""
    try:
        from lcu.core.lockfile import find_lockfile
        path = find_lockfile()
        if not path:
            return
        pid = int(Path(path).read_text(encoding="utf-8").split(":")[1])
        if not psutil.pid_exists(pid):
            Path(path).unlink()
            log.info("[AccountLogin] Removed the closed League client's lockfile")
    except Exception as e:
        log.debug(f"[AccountLogin] Could not check the League lockfile: {e}")


def _start_riot_client(*args: str) -> None:
    exe = _riot_client_exe()
    if not args:
        # Through Explorer, so it starts with the shell's normal rights, not Rose's administrator rights: a Riot
        # Client started as administrator starts League as administrator, and no mod can be applied to it (Nov 10)
        subprocess.Popen(["explorer.exe", str(exe)], close_fds=True)
        return
    subprocess.Popen([str(exe), *args], cwd=str(exe.parent), close_fds=True)


def _riot_client_elevated() -> Optional[bool]:
    """Whether the Riot Client runs as administrator (League then does too); None if it can't be told"""
    from utils.system.windows_account import process_elevated
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] == "RiotClientServices.exe":
            return process_elevated(proc.pid)
    return None


def _close_riot_client(timeout: float = 15.0) -> None:
    """Close every Riot Client process, so the next one starts fresh. Only called signed out, with League closed."""
    procs = [p for p in psutil.process_iter(["name"]) if p.info["name"] in RIOT_CLIENT_PROCESSES]
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=timeout)
    log.info(f"[AccountLogin] Closed the Riot Client ({len(procs)} processes, {len(alive)} still running)")


def _league_client_running() -> bool:
    return any(p.info["name"] in LEAGUE_CLIENT_PROCESSES for p in psutil.process_iter(["name"]))


def _press_play() -> bool:
    """Ask the Riot Client to start League through its local API, as its Play button does.

    True if the request was taken: 2xx, or 423 "already_launched" (a launch is under way).
    """
    response = _rc_request("POST", LAUNCH_LEAGUE_PATH, timeout=15.0)  # can be slow right after a sign-in
    if response is None:
        return False
    log.info(f"[AccountLogin] Play request: {response.status_code}")
    return response.ok or response.status_code == 423


def _launch_league(timeout: float = 90.0) -> bool:
    """Press Play and wait for League, retrying until it starts.

    Right after a sign-in the Riot Client may not take the request yet, so retry every few seconds.
    The command-line launch (like the desktop shortcut) is the fallback; it is often ignored after a sign-in.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        if _press_play():
            if _wait(_league_client_running, 20):
                return True
        elif attempt % 5 == 0:
            _start_riot_client(*LAUNCH_LEAGUE_ARGS)
        if _wait(_league_client_running, 3):
            return True
        log.info("[AccountLogin] League didn't start yet; asking the Riot Client again")
    return False


def _ready_to_play(account) -> bool:
    """The Riot Client has finished the sign-in: right account, nothing pending, League eligible to launch"""
    if not _is_signed_in_as(account):
        return False
    session = _rc_request("GET", "/player-session-lifecycle/v1/session")
    try:
        if session is None or not session.ok or session.json().get("actionRequired"):
            return False
    except ValueError:
        return False
    eligibility = _rc_request("GET", ELIGIBILITY_PATH)
    return eligibility is not None and eligibility.ok


def _wait_ready_to_play(account, timeout: float = 60.0) -> bool:
    """Wait until the sign-in has settled: _ready_to_play for 3 checks in a row (about 3 s).

    Pressing Play while it's still settling starts League without the player's credentials
    ("unknown player" / "unexpected error").
    """
    streak = [0]

    def settled() -> bool:
        streak[0] = streak[0] + 1 if _ready_to_play(account) else 0
        return streak[0] >= 3

    return _wait(settled, timeout)


def _not_ready_reason() -> str:
    """Why the Riot Client won't launch League yet, for the log (e.g. eula_not_accepted)"""
    eligibility = _rc_request("GET", ELIGIBILITY_PATH)
    if eligibility is None:
        return "no answer"
    if eligibility.ok:
        return "still signing in"
    try:
        return eligibility.json().get("errorCode") or f"error {eligibility.status_code}"
    except ValueError:
        return f"error {eligibility.status_code}"


def _league_loaded(timeout: float = 45.0) -> bool:
    """True once League shows the Riot Client's player, or if League was closed meanwhile (nothing to fix).

    False if League keeps running without one ("unknown player" / "unexpected error"), or shows a different
    player: an old League sign-in the Riot Client kept (Nov 9: Riot Client on one account, League on another).
    45 s: League shows the player within about 10 s; on Nov 9 a user gave up on "unknown player" after about 50 s.
    A League with no login session for 15 s is "unknown player" (Nov 9 League logs: a good one has it within 2 s): stop early.
    """
    from lcu.core.client import LCU
    wrong_player = []
    no_login = []  # when League answered "no login session", while it still has none

    def loaded() -> bool:
        if not _league_client_running():
            no_login.clear()  # a League started again gets its own 15 s
            # The user may close an "unknown player" League and press Play again (Nov 9): watch the new one too
            return not _wait(_league_client_running, 15)
        try:
            lcu = LCU()
            summoner = lcu.get("/lol-summoner/v1/current-summoner", timeout=3.0) if lcu.ok else None
            login = lcu.get("/lol-login/v1/session", timeout=3.0, use_cache=False) if lcu.ok and not summoner else {}
        except Exception:
            return False
        if not (summoner and (summoner.get("gameName") or summoner.get("displayName"))):
            if login is None:  # League's API is up and says it has no login session
                no_login.append(time.monotonic())
                if no_login[-1] - no_login[0] >= 15:
                    log.warning("[AccountLogin] League has had no login session for 15 s (\"unknown player\")")
                    wrong_player.append(True)  # stop waiting: this League won't sign in by itself, restart it
                    return True
            else:
                no_login.clear()
            return False
        expected = _signed_in_puuid()
        if expected and summoner.get("puuid") and summoner["puuid"] != expected:
            log.warning("[AccountLogin] League opened as a different player than the Riot Client (an old League sign-in)")
            wrong_player.append(True)  # stop waiting: this League won't change player by itself
        return True

    return _wait(loaded, timeout, interval=3.0) and not wrong_player


def _start_league_for(account) -> tuple[bool, str]:
    """Make League's sign-in and press Play once the sign-in has settled; check League loaded the player, restart once if not"""
    for attempt in (1, 2):
        if not _wait_ready_to_play(account):
            # Unknown states shouldn't block Play: the loaded check below catches a League that fails
            log.warning(f"[AccountLogin] Riot Client not ready to start League ({_not_ready_reason()}); trying anyway")
        _forget_league_sign_in()
        _make_league_sign_in()
        if not _launch_league():
            return True, "Signed in, but League didn't start. Press Play in the Riot Client."
        if _league_loaded():
            return True, "Signed in. League is starting."
        if attempt == 1:
            log.warning("[AccountLogin] League didn't load the signed-in player; restarting League")
            _close_league_client()
    return True, "Signed in, but League couldn't load the account. Close League and press Play in the Riot Client."


# ------------------------------------------------------------------ sign-in window
def _escape_keys(text: str) -> str:
    """Escape pywinauto send_keys modifiers so every character is typed literally"""
    return "".join("{%s}" % c if c in "+^%~(){}[]" else c for c in text)


def _is_password_field(ctrl) -> bool:
    try:
        return bool(ctrl.element_info.element.CurrentIsPassword)
    except Exception:
        return False


def _riot_client_window() -> int:
    """Handle of the Riot Client's own window, shown or hidden; 0 if there is none.

    Matched by process too, so a browser tab titled "Riot Client" never gets the login.
    """
    from pywinauto import Desktop
    pids = {p.pid for p in psutil.process_iter(["name"]) if p.info["name"] == "Riot Client.exe"}
    for window in Desktop(backend="win32").windows(title="Riot Client", class_name="Chrome_WidgetWin_1", visible_only=False):
        if window.process_id() in pids:
            return window.handle
    return 0


def _in_front(handle: int) -> bool:
    return ctypes.windll.user32.GetForegroundWindow() == handle


def _bring_to_front(handle: int) -> None:
    """Show the Riot Client and put it in front: hidden or covered, it builds no sign-in fields (Nov 9)"""
    user32 = ctypes.windll.user32
    state = "hidden" if not user32.IsWindowVisible(handle) else "minimized" if user32.IsIconic(handle) else "behind other windows"
    log.info(f"[AccountLogin] Bringing the Riot Client to the front (it was {state})")
    user32.ShowWindow(handle, 9 if user32.IsIconic(handle) else 5)  # SW_RESTORE, else SW_SHOW
    user32.SetForegroundWindow(handle)


def fill_riot_login(username: str, password: str, timeout: float = 60.0) -> bool:
    """Type the login into the Riot Client sign-in window and press Enter.

    Returns False if the window or its username/password fields don't show up in time,
    so the user can sign in by hand. Never logs the password.
    """
    import comtypes
    comtypes.CoInitialize()  # UI Automation needs COM on this thread
    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys

        log.info("[AccountLogin] Looking for the Riot Client sign-in window")
        deadline = time.monotonic() + timeout
        next_status = time.monotonic() + 10
        next_raise = 0.0
        while time.monotonic() < deadline:
            edits = []
            try:
                handle = _riot_client_window()
                if handle:
                    # Hidden, minimized or covered, the Riot Client builds no sign-in fields: bring it up
                    if not _in_front(handle) and time.monotonic() >= next_raise:
                        _bring_to_front(handle)
                        next_raise = time.monotonic() + 5  # at most every 5 s, so the user can still use other windows
                        time.sleep(1.0)
                    edits = [e for e in Desktop(backend="uia").window(handle=handle).descendants(control_type="Edit") if e.is_visible() and e.is_enabled()]
                password_fields = [e for e in edits if _is_password_field(e)]
                username_fields = [e for e in edits if not _is_password_field(e)]
                # Only type when both fields are there, so the password can't land anywhere else
                if password_fields and username_fields:
                    for field, text in ((username_fields[0], username), (password_fields[0], password)):
                        field.set_focus()
                        field.click_input()
                        # Keys go to the window in front: never type the login anywhere but the Riot Client
                        if not _in_front(handle):
                            raise RuntimeError("the Riot Client is not in front")
                        send_keys("^a{BACKSPACE}")
                        send_keys(_escape_keys(text), with_spaces=True, pause=0.01)
                    if not _in_front(handle):
                        raise RuntimeError("the Riot Client is not in front")
                    send_keys("{ENTER}")
                    log.info("[AccountLogin] Filled in the Riot Client sign-in")
                    return True
            except Exception as e:
                # Type name only: a typing error's message could quote the keys, i.e. the password
                log.info(f"[AccountLogin] Sign-in window not ready: {type(e).__name__}")
            if time.monotonic() >= next_status:
                try:
                    titles = [w.window_text() for w in Desktop(backend="uia").windows() if "riot" in w.window_text().lower()]
                except Exception:
                    titles = "?"
                log.info(f"[AccountLogin] Still waiting for the sign-in fields ({len(edits)} found; Riot windows: {titles})")
                next_status = time.monotonic() + 10
            time.sleep(1.0)
        log.warning("[AccountLogin] Riot Client sign-in fields not found")
        return False
    finally:
        comtypes.CoUninitialize()


# ------------------------------------------------------------------ switch
def switch_to_account(account_id: str, progress: Callable[[str], None] = lambda msg: None) -> tuple[bool, str]:
    """Sign the Riot Client in to a saved account and start League.

    Returns (success, message for the user). Runs for up to a few minutes: call it off the UI thread.
    """
    if not _switch_lock.acquire(blocking=False):
        return False, "A switch is already in progress"
    show = progress

    def progress(message: str) -> None:  # every stage also goes to the log
        log.info(f"[AccountLogin] {message}")
        show(message)

    try:
        account = get_account_manager().get_account(account_id)
        if not account:
            return False, "Account not found"
        password = get_password(account.id)
        if not password:
            return False, "No saved password for this account. Edit it to add one."
        if game_in_progress():
            return False, "Can't switch accounts during a game"

        # Already on this account: no need to sign out and in again. A League stuck on
        # "unknown player" gets restarted, so switching to the same account also fixes that.
        if _is_signed_in_as(account):
            if _league_client_running():
                if _league_loaded(timeout=10):
                    return True, "Already signed in to this account."
                progress("Closing League...")
                _close_league_client()
            progress("Starting League...")
            return _start_league_for(account)

        progress("Closing League...")
        _close_league_client()

        if not _riot_client_running():
            progress("Starting the Riot Client...")
            _start_riot_client()
            if not _wait(_riot_client_running, 45):
                return False, "The Riot Client didn't start"

        if _signed_in():
            progress("Signing out of the Riot Client...")
            if not _sign_out_and_stay_out():
                return False, "Couldn't sign out of the Riot Client"
            # A Riot Client that has held another account starts League wrong for the next one (its logs, Nov 10):
            # "unknown player" in 12 switches of 16, and the ready check can stay on the old account's region.
            # A freshly started Riot Client loaded the player 3 times in 3.
            progress("Restarting the Riot Client...")
            _close_riot_client()

        # Start it again, or bring its window up: once League has started it can be hidden, with no sign-in fields to find
        _start_riot_client()

        progress("Filling in the sign-in...")
        if not fill_riot_login(account.username, password):
            return False, "Couldn't fill in the sign-in. Please type it in the Riot Client."
        before = _auth_state()  # right after Enter, before Riot answers: anything older isn't this sign-in's

        progress("Waiting for the sign-in (finish any two-factor prompt in the Riot Client)...")
        problem = []

        def signed_in_or_refused() -> bool:
            if _signed_in():
                return True
            message = _sign_in_problem(before)
            if message and not _wait(_signed_in, 3):  # a sign-in that just went through can look like this for a moment
                problem.append(message)
            return bool(message)

        if not _wait(signed_in_or_refused, 120):
            return False, "Sign-in not finished. Check the Riot Client."
        if problem:
            log.warning(f"[AccountLogin] The Riot Client refused the sign-in ({_auth_state().get('error') or 'no reason given'})")
            if "Wrong username or password" in problem[0]:
                get_account_manager().set_login_error(account.id, "wrong_login")
            return False, problem[0]
        # Never press Play for the wrong account: "stay signed in" can bring the previous one back
        if not _wait(lambda: _is_signed_in_as(account), 15):
            other = (_signed_in_account() or ("", ""))[1] or "a different account"
            log.warning(f"[AccountLogin] Signed in to {other}, not account {account.id}")
            return False, f"The Riot Client signed in to {other} instead. Sign out in the Riot Client, then try again."

        get_account_manager().set_login_error(account.id, "")  # this login works
        progress("Starting League...")
        log.info(f"[AccountLogin] Switched to account {account.id}")
        if _riot_client_elevated():
            log.warning("[AccountLogin] The Riot Client runs as administrator, so League will too: mods can't be applied to it")
        return _start_league_for(account)
    except Exception as e:
        log.error(f"[AccountLogin] Switch failed: {e}")
        return False, f"Switch failed: {e}"
    finally:
        _switch_lock.release()


def switch_in_background(account_id: str, progress: Callable[[str], None] = lambda msg: None,
                         done: Callable[[bool, str], None] = lambda ok, msg: None) -> None:
    """Run switch_to_account on its own thread; done(success, message) is called at the end"""
    def run():
        ok, message = switch_to_account(account_id, progress)
        (log.info if ok else log.warning)(f"[AccountLogin] {message}")
        done(ok, message)

    threading.Thread(target=run, name="AccountSwitch", daemon=True).start()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Account Manager - Manages multiple League of Legends accounts
Accounts are added by login username; Riot ID and rank are filled in
automatically when Rose sees that login signed in to the League client.
"""

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.core.logging import get_logger
from utils.core.paths import get_user_data_dir
from utils.core.atomic_file import atomic_write
from .account_secrets import delete_password

log = get_logger()


@dataclass
class Account:
    """A saved League of Legends account"""
    id: str  # Internal id; also the password key in Windows Credential Manager
    username: str  # Riot login name (never sent to the League client)
    region: str = "NA"
    note: str = ""
    riot_id: str = ""  # Name#Tag, filled in automatically after the first sign-in
    last_login: Optional[str] = None
    is_active: bool = False
    # Rank data (filled in automatically)
    tier: str = ""
    division: str = ""
    lp: int = 0
    level: int = 0
    last_season: str = ""
    rank_updated: Optional[str] = None
    login_error: str = ""  # "wrong_login" after the Riot Client refused this login; cleared by a sign-in that works or a new password
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    login_count: int = 0

    def to_dict(self) -> dict:
        """Convert account to dictionary for serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Account':
        """Create account from dictionary, ignoring unknown keys"""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class AccountManager:
    """Manages multiple accounts with storage and switching"""

    def __init__(self):
        self.accounts: dict[str, Account] = {}
        self.active_account_id: Optional[str] = None
        self._lock = threading.RLock()
        self._storage_path = self._get_storage_path()
        self._stamp = None  # (mtime_ns, size) of accounts.json as last read or written by this program
        self._load_accounts()

    def _get_storage_path(self) -> Path:
        """Get the path for storing account data"""
        accounts_dir = get_user_data_dir() / "accounts"
        accounts_dir.mkdir(parents=True, exist_ok=True)
        return accounts_dir / "accounts.json"

    def _file_stamp(self):
        """accounts.json's (modification time, size), or None if it can't be read"""
        try:
            st = self._storage_path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _reload_if_changed(self) -> None:
        """Re-read accounts.json if another program (Rose or the account window) saved it since we did.

        Call inside self._lock. A re-read that fails keeps the accounts in memory: never lose accounts over
        a file that is busy for a moment. shortcut: no lock between programs, so two saves in the same
        instant can still lose one change; upgrade to a lock file if that ever happens.
        """
        stamp = self._file_stamp()
        if stamp is None or stamp == self._stamp:
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            log.warning(f"[AccountManager] Could not re-read accounts.json ({type(e).__name__}); keeping the accounts in memory")
            return
        loaded, active = {}, None
        for acc_data in data.values():
            if not acc_data.get("id") or not acc_data.get("username"):
                continue
            account = Account.from_dict(acc_data)
            loaded[account.id] = account
            if account.is_active:
                active = account.id
        self.accounts, self.active_account_id, self._stamp = loaded, active, stamp

    def _load_accounts(self) -> None:
        """Load accounts from storage"""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                loaded = {}
                for acc_id, acc_data in data.items():
                    if not acc_data.get('id') or not acc_data.get('username'):
                        log.warning(f"[AccountManager] Skipping old account entry (re-add it with its login username): {acc_id}")
                        continue
                    account = Account.from_dict(acc_data)
                    loaded[account.id] = account
                    if account.is_active:
                        self.active_account_id = account.id
                self.accounts = loaded
                self._stamp = self._file_stamp()
                log.info(f"[AccountManager] Loaded {len(self.accounts)} accounts")
            else:
                log.info("[AccountManager] No existing accounts found")
        except Exception as e:
            log.error(f"[AccountManager] Failed to load accounts: {e}")
            try:
                if self._storage_path.exists():
                    backup = self._storage_path.parent / f"accounts.broken-{datetime.now():%Y%m%d-%H%M%S}.json"
                    shutil.copy2(self._storage_path, backup)
                    log.warning(f"[AccountManager] Backed up corrupted file to {backup}")
            except Exception as copy_e:
                log.error(f"[AccountManager] Failed to backup corrupted file: {copy_e}")
            self.accounts = {}

    def _save_accounts(self) -> None:
        """Save accounts to storage"""
        try:
            data = {acc_id: acc.to_dict() for acc_id, acc in self.accounts.items()}
            with atomic_write(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._stamp = self._file_stamp()
            log.debug(f"[AccountManager] Saved {len(self.accounts)} accounts")
        except Exception as e:
            log.error(f"[AccountManager] Failed to save accounts: {e}")

    def add_account(self, username: str, region: str = "NA", note: str = "") -> Account:
        """Add a new account by login username. Returns the existing one if already saved."""
        username = username.strip()
        with self._lock:
            self._reload_if_changed()
            existing = self.find_by_username(username)
            if existing:
                log.warning("[AccountManager] An account with that login username already exists")
                return existing

            account = Account(id=uuid.uuid4().hex, username=username, region=region, note=note)
            self.accounts[account.id] = account
            self._save_accounts()
            log.info(f"[AccountManager] Added account {account.id}")
            return account

    def update_account(self, account_id: str, username: str, region: str, note: str) -> bool:
        """Update the editable fields of an account"""
        with self._lock:
            self._reload_if_changed()
            account = self.accounts.get(account_id)
            if not account:
                return False
            other = self.find_by_username(username)
            if other and other.id != account_id:
                log.warning("[AccountManager] Another account already uses that login username")
                return False
            account.username = username.strip()
            account.region = region
            account.note = note
            self._save_accounts()
            return True

    def remove_account(self, account_id: str) -> bool:
        """Remove an account and its saved password"""
        with self._lock:
            self._reload_if_changed()
            if account_id not in self.accounts:
                log.warning(f"[AccountManager] Account {account_id} not found")
                return False
            del self.accounts[account_id]
            if account_id == self.active_account_id:
                self.active_account_id = None
            self._save_accounts()
        delete_password(account_id)
        log.info(f"[AccountManager] Removed account {account_id}")
        return True

    def get_account(self, account_id: str) -> Optional[Account]:
        """Get an account by its internal id"""
        with self._lock:
            self._reload_if_changed()
            return self.accounts.get(account_id)

    def find_by_username(self, username: str) -> Optional[Account]:
        """Find an account by login username (case-insensitive)"""
        wanted = username.strip().lower()
        with self._lock:
            self._reload_if_changed()
            return next((a for a in self.accounts.values() if a.username.lower() == wanted), None)

    def get_all_accounts(self) -> list[Account]:
        """Get all accounts"""
        with self._lock:
            self._reload_if_changed()
            return list(self.accounts.values())

    def get_active_account(self) -> Optional[Account]:
        """Get the currently active account"""
        with self._lock:
            self._reload_if_changed()
            if self.active_account_id:
                return self.accounts.get(self.active_account_id)
            return None

    def set_active_account(self, account_id: str) -> bool:
        """Mark an account as the one signed in to the client"""
        with self._lock:
            self._reload_if_changed()
            if account_id not in self.accounts:
                log.warning(f"[AccountManager] Account {account_id} not found")
                return False
            if account_id == self.active_account_id:
                return True  # already active; don't count it as a new login

            for acc in self.accounts.values():
                acc.is_active = False
            account = self.accounts[account_id]
            account.is_active = True
            account.last_login = datetime.now().isoformat()
            account.login_count += 1
            self.active_account_id = account_id
            self._save_accounts()
            log.info(f"[AccountManager] Set active account {account_id}")
            return True

    def update_from_client(self, account_id: str, riot_id: str, tier: str = "", division: str = "",
                           lp: int = 0, level: int = 0, last_season: str = "") -> bool:
        """Save the Riot ID and rank the League client reports for a signed-in account"""
        with self._lock:
            self._reload_if_changed()
            account = self.accounts.get(account_id)
            if not account:
                return False
            seen = (riot_id or account.riot_id, tier, division, lp, level, last_season)
            if seen == (account.riot_id, account.tier, account.division, account.lp, account.level, account.last_season):
                return True  # nothing new: don't rewrite accounts.json on every 60 s check
            if riot_id:
                account.riot_id = riot_id
            account.tier = tier
            account.division = division
            account.lp = lp
            account.level = level
            account.last_season = last_season
            account.rank_updated = datetime.now().isoformat()
            self._save_accounts()
            return True

    def set_login_error(self, account_id: str, error: str) -> None:
        """Remember ("wrong_login") or clear ("") that the Riot Client refused this account's login"""
        with self._lock:
            self._reload_if_changed()
            account = self.accounts.get(account_id)
            if account is None or account.login_error == error:
                return
            account.login_error = error
            self._save_accounts()


# Global instance
_account_manager = None
_account_manager_lock = threading.Lock()


def get_account_manager() -> AccountManager:
    """Get or create the global AccountManager instance"""
    global _account_manager
    if _account_manager is None:
        with _account_manager_lock:
            if _account_manager is None:
                _account_manager = AccountManager()
    return _account_manager

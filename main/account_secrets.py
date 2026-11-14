# -*- coding: utf-8 -*-
"""
Account Secrets - Store and retrieve account passwords using the system keyring
(Windows Credential Manager). Passwords are keyed by the account's internal id.
"""

import keyring
from keyring.errors import PasswordDeleteError

_SERVICE = "Rose-AccountSwitcher"


def set_password(account_id: str, password: str) -> None:
    """Store a password for the given account id in the system keyring."""
    keyring.set_password(_SERVICE, account_id, password)


def get_password(account_id: str) -> str:
    """Retrieve the password for the given account id. Returns "" if none is saved."""
    return keyring.get_password(_SERVICE, account_id) or ""


def delete_password(account_id: str) -> bool:
    """Delete the stored password. Returns False if there was none."""
    try:
        keyring.delete_password(_SERVICE, account_id)
        return True
    except PasswordDeleteError:
        return False

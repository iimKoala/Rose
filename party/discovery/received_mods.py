#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where the custom skin mods that party members sent us are kept (party/network/mod_transfer.py).

A folder of its own under Rose's mods folder, each file named by its content hash. They are not the user's
own mods: Rose's mod lists never show them, and they are only used for the friend who plays with them.
"""

from pathlib import Path
from typing import Optional

from utils.core.paths import get_user_data_dir

FOLDER = "party-received"
SUFFIXES = (".fantome", ".zip", ".modpkg")


def received_dir() -> Path:
    return get_user_data_dir() / "mods" / FOLDER


def received_mod(content_hash) -> Optional[str]:
    """The file a friend sent us with this content hash, as a path relative to the mods folder; None when
    there is none"""
    if not isinstance(content_hash, str) or not content_hash or not all(c in "0123456789abcdef" for c in content_hash):
        return None
    for suffix in SUFFIXES:
        if (received_dir() / f"{content_hash}{suffix}").is_file():
            return f"{FOLDER}/{content_hash}{suffix}"
    return None

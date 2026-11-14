# -*- coding: utf-8 -*-
"""
Account Import/Export - plain text account lists.

One account per line:  username:password  or  username:password:REGION
The separator can also be | ; tab or comma. Blank lines and lines starting with # are ignored.
Invalid lines are skipped and listed in "<file>_skipped.txt" next to the imported file
(line number, username and reason; never the password).

"Valid" here means well-formed: Rose can't check a password with Riot without signing in.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

SEPARATORS = (":", "|", ";", "\t", ",")
REGIONS = {"NA", "EUW", "EUNE", "KR", "JP", "BR", "LAN", "LAS", "OCE", "TR", "RU", "PH", "SG", "TH", "TW", "VN", "ME"}
USERNAME_LENGTH = (3, 24)
PASSWORD_LENGTH = (6, 128)


def username_problem(username: str) -> Optional[str]:
    """Why this can't be a Riot login username, or None. Never contacts Riot: format only."""
    if not username:
        return "Login username is required"
    if "#" in username:
        return "That looks like a Riot ID (Name#TAG). Use the login username you type into the Riot Client"
    if any(c.isspace() for c in username):
        return "The login username can't contain spaces"
    if any(sep in username for sep in SEPARATORS):
        return "The login username can't contain : | ; , or tabs"
    if not USERNAME_LENGTH[0] <= len(username) <= USERNAME_LENGTH[1]:
        return f"The login username must be {USERNAME_LENGTH[0]}-{USERNAME_LENGTH[1]} characters"
    return None


def password_problem(password: str) -> Optional[str]:
    """Why this can't be a Riot password, or None (format only; length like Import)"""
    if not PASSWORD_LENGTH[0] <= len(password) <= PASSWORD_LENGTH[1]:
        return f"The password must be {PASSWORD_LENGTH[0]}-{PASSWORD_LENGTH[1]} characters"
    return None


@dataclass
class ParsedAccount:
    username: str
    password: str
    region: str


@dataclass
class ImportResult:
    added: int
    skipped: list  # (line number, username, reason)
    skipped_file: Optional[Path]


def parse_line(line: str, default_region: str = "NA") -> tuple[Optional[ParsedAccount], Optional[str], str]:
    """Parse one line. Returns (account or None, error or None, username for messages).

    (None, None, "") means the line is blank or a comment.
    """
    text = line.strip()
    if not text or text.startswith("#"):
        return None, None, ""

    positions = [(text.find(sep), sep) for sep in SEPARATORS if sep in text]
    if not positions:
        return None, "no separator between username and password (use username:password)", ""
    _, sep = min(positions)
    username, rest = text.split(sep, 1)
    username, password, region = username.strip(), rest.strip(), default_region

    # Optional trailing region, e.g. user:pass:EUW
    if sep in password:
        head, tail = password.rsplit(sep, 1)
        if tail.strip().upper() in REGIONS:
            password, region = head.strip(), tail.strip().upper()

    if not username:
        return None, "username is empty", ""
    if username_problem(username):
        return None, username_problem(username), username
    if not password:
        return None, "password is empty", username
    if not PASSWORD_LENGTH[0] <= len(password) <= PASSWORD_LENGTH[1]:
        return None, f"password must be {PASSWORD_LENGTH[0]}-{PASSWORD_LENGTH[1]} characters", username
    return ParsedAccount(username, password, region), None, username


def import_accounts(path: Path, manager, set_password: Callable[[str, str], None],
                    default_region: str = "NA") -> ImportResult:
    """Add every valid, new account from a text file; list skipped lines in <file>_skipped.txt"""
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    added, skipped, seen = 0, [], set()

    for number, line in enumerate(lines, start=1):
        account, error, username = parse_line(line, default_region)
        if account is None:
            if error:
                skipped.append((number, username, error))
            continue
        key = account.username.lower()
        if key in seen:
            skipped.append((number, account.username, "duplicate of an earlier line"))
            continue
        seen.add(key)
        if manager.find_by_username(account.username):
            skipped.append((number, account.username, "already saved in Rose"))
            continue
        saved = manager.add_account(account.username, region=account.region)
        set_password(saved.id, account.password)  # Windows Credential Manager only
        added += 1

    skipped_file = None
    if skipped:
        skipped_file = Path(path).with_name(f"{Path(path).stem}_skipped.txt")
        report = [f"Skipped while importing {Path(path).name} ({len(skipped)} lines). Passwords are not listed.", ""]
        report += [f"Line {n}: {user or '(no username)'} - {reason}" for n, user, reason in skipped]
        skipped_file.write_text("\n".join(report) + "\n", encoding="utf-8")
    return ImportResult(added, skipped, skipped_file)


def export_accounts(path: Path, accounts, get_password: Callable[[str], str], include_passwords: bool) -> int:
    """Write accounts to a text file. With passwords it can be imported again; without, it's a list.

    Returns the number of accounts written.
    """
    if include_passwords:
        header = ["# Rose accounts: username:password:REGION", "# Contains passwords in plain text. Keep this file private.", ""]
        rows = [f"{a.username}:{get_password(a.id)}:{a.region}" for a in accounts]
    else:
        header = ["# Rose accounts (no passwords; this list can't be imported back)", "# username | region | Riot ID | note", ""]
        rows = [" | ".join([a.username, a.region, a.riot_id or "-", a.note or "-"]) for a in accounts]
    Path(path).write_text("\n".join(header + rows) + "\n", encoding="utf-8")
    return len(rows)

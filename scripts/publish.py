#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publish this copy of Rose to its public GitHub repository, after checking that it holds nothing private.

What goes out is ONE new commit holding the files of the local HEAD, on top of what was published before
(the first time: on top of the original project's history). The local history, with its old file versions
and its commit messages, never leaves this PC. After a merge of the original, that one commit also names
the original's newest commit as a parent: the original's commits are public already.

Before anything is sent, every file of that commit and its message are searched for this PC's private
values (the Windows user name, the computer's name, email addresses of the local commits, and the names,
logins and notes of the accounts saved in Rose's account switcher) and for things shaped like keys and
tokens. One hit and nothing is published. A hit is told by its kind and its place, never by its value.

    python scripts/publish.py --check              only the check
    python scripts/publish.py                      check, then publish
    python scripts/publish.py --message "..."      with this text as the public commit's message

More values never to publish, one a line: .git/rose-private.txt (that file never leaves the PC either).
Design: docs/install-from-github.md.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = re.search(r'^REPO = "([^"]+)"', (ROOT / "scripts" / "rose_update.py").read_text(encoding="utf-8"), re.M).group(1)
BRANCH = re.search(r'^BRANCH = "([^"]+)"', (ROOT / "scripts" / "rose_update.py").read_text(encoding="utf-8"), re.M).group(1)
PUBLISHED = "refs/heads/published"          # the public commits, as they were sent
PUBLISHED_FROM = "refs/published-from"      # the local commit the last public commit was made from
SHORT = 5  # a private value shorter than this is searched as a whole word: a three-letter name is inside many words
ACCOUNT_FIELDS = ("username", "riotid", "riot_id", "gamename", "game_name", "tagline", "name", "summonername", "email", "puuid", "note", "login")
# What a server or a default uses as a tag or name: not private, and found all over the code
ORDINARY = {"na1", "euw", "euw1", "eune", "eun1", "kr1", "br1", "lan", "las", "la1", "la2", "oce", "oc1", "jp1", "tr1", "rose", "league", "riot",
            "account", "player", "client", "login", "name", "main", "smurf", "none", "null", "true", "false", "test"}
SECRETS = {
    "a GitHub token": rb"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}",
    "a private key": rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "a sign-in token (JWT)": rb"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}",
    "a Riot client password": rb"riot:[A-Za-z0-9_\-]{16,}|Basic [A-Za-z0-9+/]{24,}={0,2}",
    "a link with a signature": rb"https?://[^\s'\"]*[?&](token|sig|signature|X-Amz-Signature)=[A-Za-z0-9%_\-]{16,}",
    "a chat webhook": rb"discord(app)?\.com/api/webhooks/\d+/|hooks\.slack\.com/services/T",
}
# Known and looked at: (the kind's start, the file). Each with its reason.
ALLOWED = (
    # a three-letter account word is also a Czech word in the original project's translation
    ("an account's", "Pengu Loader/plugins/ROSE-I18n/locales/cs.json"),
)


def git(*args, data=None, cwd=ROOT) -> bytes:
    return subprocess.run(["git", *args], input=data, capture_output=True, check=True, cwd=cwd).stdout


def private_values(owner: str = REPO.split("/")[0]) -> dict:
    """{value in lower case: its kind} of what must never be published. Values that are part of the
    repository owner's GitHub name are left out: that name is public by publishing at all."""
    found = {}

    def add(kind: str, value) -> None:
        value = str(value or "").strip().lower()
        if len(value) >= 3 and value not in ORDINARY and value not in owner.lower():
            found.setdefault(value, kind)

    add("the Windows user name", os.environ.get("USERNAME"))
    add("the computer's name", os.environ.get("COMPUTERNAME"))
    public = set(git("log", "origin/main", "--format=%ae%n%ce").decode("utf-8", "replace").split())
    for email in set(git("log", "--all", "--format=%ae%n%ce").decode("utf-8", "replace").split()) - public:
        if not email.endswith("@users.noreply.github.com") and "@" in email:
            add("an email address of the local commits", email)
            add("an email address of the local commits (its name)", email.split("@")[0])
    extra = ROOT / ".git" / "rose-private.txt"
    for line in extra.read_text(encoding="utf-8").splitlines() if extra.exists() else []:
        add("a value of .git/rose-private.txt", line)
        if "@" in line:
            add("a value of .git/rose-private.txt (its name)", line.split("@")[0])
    accounts = Path(os.environ.get("LOCALAPPDATA", "")) / "Rose" / "accounts" / "accounts.json"

    def walk(node, key="") -> None:
        if isinstance(node, dict):
            for inner, value in node.items():
                walk(value, inner)
        elif isinstance(node, list):
            for value in node:
                walk(value, key)
        elif isinstance(node, str) and key.lower() in ACCOUNT_FIELDS:
            add(f"an account's {key}", node)
            for part in re.split(r"[#\s,;:/]+", node):
                add(f"an account's {key} (a word of it)", part)

    if accounts.exists():
        try:
            walk(json.loads(accounts.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            raise SystemExit("The saved accounts could not be read, so their names cannot be checked: nothing is published.")
    return found


def searcher(values: dict):
    """A function (data: bytes) -> the kinds of private values in it"""
    whole = {value: kind for value, kind in values.items() if len(value) < SHORT}
    inside = {value.encode("utf-8"): kind for value, kind in values.items() if len(value) >= SHORT}
    words = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(v) for v in sorted(whole, key=len, reverse=True)) + r")(?![a-z0-9])") if whole else None

    def search(data: bytes) -> set:
        lowered = data.lower()
        kinds = {kind for value, kind in inside.items() if value in lowered}
        if words is not None and b"\0" not in data[:4096]:  # short words only in text: a program's bytes hold every short word
            kinds |= {whole[match] for match in set(words.findall(lowered.decode("utf-8", "replace")))}
        return kinds

    return search


def secret_kinds(data: bytes) -> set:
    return {kind for kind, pattern in SECRETS.items() if re.search(pattern, data)}


def audit(files, message: str, values: dict) -> list:
    """[(kind, place)] of everything private or key-like in *files* ({path: bytes} or pairs) and *message*"""
    search, hits = searcher(values), []
    for path, data in (files.items() if isinstance(files, dict) else files):
        for kind in sorted(search(data) | secret_kinds(data) | search(path.encode("utf-8"))):
            if not any(kind.startswith(start) and path == allowed for start, allowed in ALLOWED):
                hits.append((kind, path))
    for kind in sorted(search(message.encode("utf-8")) | secret_kinds(message.encode("utf-8"))):
        hits.append((kind, "the commit message"))
    return hits


def head_files():
    """(path, bytes) of every file of the local HEAD, as git holds it (not as the folder has it now)"""
    for line in git("ls-tree", "-r", "-z", "HEAD").decode("utf-8", "replace").split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            yield path, git("cat-file", "blob", meta.split()[2])


def ref(name: str, cwd=ROOT) -> str:
    done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", name], capture_output=True, cwd=cwd)
    return done.stdout.decode().strip() if done.returncode == 0 else ""


def public_parents(parent: str, cwd=ROOT) -> list:
    """The parents of the public commit: what was published before and, when HEAD holds a merge of the
    original that is not published yet, the original's newest commit too. Those commits are public already
    (they are the original's), and without them GitHub keeps counting this branch as behind the original."""
    def within(older: str, newer: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], capture_output=True, cwd=cwd).returncode == 0

    original = ref("refs/remotes/origin/main", cwd)
    return [parent, original] if original and within(original, "HEAD") and not within(original, parent) else [parent]


def public_message(given: str) -> str:
    if given:
        return given
    since = ref(PUBLISHED_FROM)
    if not since:
        return "Rose with an account switcher, a mod store, a builds panel and in-game panels\n\nThis version's changes, on top of the original project."
    subjects = git("log", "--reverse", "--format=- %s", f"{since}..HEAD").decode("utf-8", "replace").strip()
    return "Update\n\n" + subjects if subjects else "Update"


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    given = args[args.index("--message") + 1] if "--message" in args and args.index("--message") + 1 < len(args) else ""
    waiting = git("status", "--porcelain", "--untracked-files=no").decode().strip()
    if waiting:
        print("Not committed yet, so NOT part of what is published:\n" + waiting + "\n")
    values = private_values()
    message = public_message(given)
    files = list(head_files())
    hits = audit(files, message, values)
    print(f"Checked {len(files)} files and the commit message for {len(values)} private values of this PC and for keys and tokens.")
    if hits:
        print(f"\nNOTHING IS PUBLISHED: {len(hits)} thing(s) must go first.")
        for kind, place in hits:
            print(f"  {kind}: in {place}")
        return 1
    print("Nothing private found.")
    if "--check" in args:
        return 0
    parent = ref(PUBLISHED) or git("merge-base", "HEAD", "origin/main").decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    if ref(PUBLISHED) and git("rev-parse", parent + "^{tree}").decode().strip() == tree:
        commit = parent  # these files were made into a public commit already: only send it (again)
    else:
        parents = [arg for one in public_parents(parent) for arg in ("-p", one)]
        commit = git("commit-tree", tree, *parents, "-m", message).decode().strip()
        git("update-ref", PUBLISHED, commit)
        git("update-ref", PUBLISHED_FROM, "HEAD")
    pushed = subprocess.run(["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential", "push",
                             f"https://github.com/{REPO}.git", f"{PUBLISHED}:refs/heads/{BRANCH}"], cwd=ROOT)
    if pushed.returncode:
        print("GitHub did not take it. The commit is kept here; run this again to send it.")
        return 1
    print(f"Published to github.com/{REPO} (branch {BRANCH}) as {commit[:8]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

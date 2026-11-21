#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install Rose from its source on GitHub, and keep that copy up to date.

For a PC that runs this version of Rose without the developer's tools (no git, no build): the source is
downloaded as GitHub's zip of the newest commit, put in place file by file, and Rose is started from it with
its own Python environment. `Start Rose.bat` runs this before every start, so each push to the repository
reaches that PC at its next start. Only Python's standard library is used: it runs before Rose's packages
are installed.

    python rose_update.py --install [folder]    first time: source, packages, tools, a Desktop shortcut
                                                (--no-shortcut: without it, for a trial install)
    python rose_update.py                       before each start: the newest source, packages if they changed

A developer's copy (a folder with .git) is never touched. An update that fails never keeps Rose from
starting: it starts as it is. Design: docs/install-from-github.md.
"""

import io
import os
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPO = "iimKoala/Rose"
BRANCH = "release"
TOOLS_URL = f"https://github.com/{REPO}/releases/download/tools/rose-tools.zip"
VERSION_FILE, FILES_FILE, PACKAGES_FILE = ".rose-version", ".rose-files", ".rose-packages"
# An update downloaded while Rose ran (main/self_update.py), waiting for the next start to be installed
STAGED_FILE, STAGED_VERSION_FILE = ".rose-update.zip", ".rose-update-version"
PACKAGE_LISTS = ("requirements.txt", "requirements-run.txt")
# The plugins' own settings on this PC: put there once, never replaced by an update
KEPT = ("Pengu Loader/datastore", "Pengu Loader/config")
# Programs Rose needs that are not in the source (built from native/ and vendor/); they come as one zip
TOOLS = ("Pengu Loader/Pengu Loader.exe", "injection/tools/LeagueToolFlop.dll", "injection/tools/ltk_launcher.exe",
         "injection/tools/rose-mod-check.exe")
TIMEOUT_S = 60


def fetch(url: str, accept: str = "") -> bytes:
    """What GitHub answers at *url*"""
    request = urllib.request.Request(url, headers={"User-Agent": "Rose-updater", **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as answer:
        return answer.read()


def latest_version(fetch=fetch) -> str:
    """The id of the newest commit on the branch"""
    version = fetch(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}", "application/vnd.github.sha").decode("ascii", "replace").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", version):
        raise ValueError("GitHub's answer is not a version")
    return version


def safe_path(root: Path, relative: str) -> Path:
    """Where a zip's file goes inside *root*; a name that would leave the folder is refused"""
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
        raise ValueError(f"a file outside Rose's folder: {relative!r}")
    return root.joinpath(*parts)


def unpack(archive: bytes, root: Path, strip_top: bool, kept=()) -> list:
    """Put a zip's files into *root* (only those that differ are written); the names it holds. *strip_top*:
    GitHub's source zips keep everything in one top folder. A *kept* file that exists already is left."""
    names = []
    with zipfile.ZipFile(io.BytesIO(archive)) as packed:
        for name in packed.namelist():
            relative = name.split("/", 1)[1] if strip_top and "/" in name else ("" if strip_top else name)
            if not relative or relative.endswith("/"):
                continue
            target = safe_path(root, relative)
            names.append(relative)
            if relative in kept and target.exists():
                continue
            content = packed.read(name)
            if relative.lower().endswith((".bat", ".cmd")):
                # git keeps these with Unix line ends; cmd.exe can lose its place in such a file (goto, labels)
                content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            if target.exists() and target.read_bytes() == content:
                continue  # also keeps the running Start Rose.bat untouched when it did not change
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    return names


def apply_source(archive: bytes, root: Path) -> int:
    """Make *root* hold the source in GitHub's zip: its files written, and the files of the last update that
    are gone from it removed. Returns how many old files were removed."""
    old = set((root / FILES_FILE).read_text(encoding="utf-8").splitlines()) if (root / FILES_FILE).exists() else set()
    names = unpack(archive, root, strip_top=True, kept=KEPT)
    removed = 0
    for gone in sorted(old - set(names) - set(KEPT)):
        try:
            safe_path(root, gone).unlink()
            removed += 1
        except (OSError, ValueError):
            pass
    (root / FILES_FILE).write_text("\n".join(names) + "\n", encoding="utf-8")
    return removed


def package_list(root: Path) -> str:
    """The packages Rose needs to run from source: both of its lists (requirements.txt has the app's own,
    requirements-run.txt the windows'), each without its "Build requirements" part (PyInstaller is for
    building Rose.exe and does not install on every Python)."""
    lines = []
    for name in PACKAGE_LISTS:
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            if line.strip().lower().startswith("# build requirements"):
                break
            if line.strip() and not line.lstrip().startswith("#") and line.strip() not in lines:
                lines.append(line.strip())
    return "".join(line + chr(10) for line in lines)


def ensure_packages(root: Path, run=subprocess.run) -> bool:
    """Rose's own Python environment with the packages it lists; installed again only when the list
    changed. Returns whether anything was installed."""
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)
    wanted = package_list(root)
    marker = root / PACKAGES_FILE
    if marker.exists() and marker.read_text(encoding="utf-8") == wanted:
        return False
    print("Installing Rose's Python packages (a few minutes the first time)...")
    todo = root / (PACKAGES_FILE + ".todo")
    todo.write_text(wanted, encoding="utf-8")
    run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(todo)], check=True)
    todo.replace(marker)
    return True


def ensure_tools(root: Path, fetch=fetch) -> bool:
    """The programs that are not in the source, downloaded once. Returns whether they were downloaded."""
    if all((root / tool).exists() for tool in TOOLS):
        return False
    print("Downloading the programs Rose starts (Pengu Loader, the mod bridge)...")
    unpack(fetch(TOOLS_URL), root, strip_top=False)
    missing = [tool for tool in TOOLS if not (root / tool).exists()]
    if missing:
        raise ValueError(f"the tools download lacks {', '.join(missing)}")
    return True


def make_shortcut(root: Path, run=subprocess.run) -> None:
    """A "Rose" shortcut on the Desktop that starts this copy"""
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Rose.lnk')); "
              "$s.TargetPath = $env:ROSE_START; $s.WorkingDirectory = $env:ROSE_DIR; $s.IconLocation = $env:ROSE_ICON; $s.Save()")
    env = dict(os.environ, ROSE_START=str(root / "Start Rose.bat"), ROSE_DIR=str(root), ROSE_ICON=str(root / "assets" / "icon.ico"))
    run(["powershell", "-NoProfile", "-Command", script], check=True, env=env)


def staged_version(root: Path) -> str:
    """The version downloaded while Rose ran and not installed yet; "" for none"""
    try:
        version = (root / STAGED_VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return version if re.fullmatch(r"[0-9a-f]{40}", version) and (root / STAGED_FILE).exists() else ""


def drop_staged(root: Path) -> None:
    for name in (STAGED_FILE, STAGED_VERSION_FILE, STAGED_FILE + ".part"):
        try:
            (root / name).unlink()
        except OSError:
            pass


def stage(root: Path, fetch=fetch) -> str:
    """Download the newest version without installing it: Rose is running from the files it would replace.
    Returns the version that waits for the next start; "" when this copy is up to date, or a developer's.
    A download that is not a whole zip is not kept. Raises what GitHub's answer raises."""
    if (root / ".git").exists():
        return ""
    version_file = root / VERSION_FILE
    current = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else ""
    newest = latest_version(fetch)
    if newest == current:
        drop_staged(root)
        return ""
    if staged_version(root) == newest:
        return newest
    archive = fetch(f"https://github.com/{REPO}/archive/{newest}.zip")
    with zipfile.ZipFile(io.BytesIO(archive)) as packed:
        if not packed.namelist() or packed.testzip() is not None:
            raise ValueError("the download is damaged")
    part = root / (STAGED_FILE + ".part")
    part.write_bytes(archive)
    part.replace(root / STAGED_FILE)
    (root / STAGED_VERSION_FILE).write_text(newest, encoding="utf-8")
    return newest


def update(root: Path, installing: bool, fetch=fetch, run=subprocess.run) -> str:
    """Bring *root* to the newest version; returns what was done, in words"""
    root.mkdir(parents=True, exist_ok=True)
    version_file = root / VERSION_FILE
    current = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else ""
    staged = staged_version(root)
    try:
        newest = latest_version(fetch)
    except Exception:
        if not staged:
            raise
        newest = staged  # GitHub cannot be asked now: what was downloaded while Rose ran is installed
    done = "Rose is up to date"
    if newest != current:
        try:
            if staged == newest:
                archive = (root / STAGED_FILE).read_bytes()
            else:
                print("Downloading the newest Rose...")
                archive = fetch(f"https://github.com/{REPO}/archive/{newest}.zip")
            removed = apply_source(archive, root)
        finally:
            drop_staged(root)  # installed, outdated, or unusable: the next start downloads anew
        version_file.write_text(newest, encoding="utf-8")
        done = f"Rose is now at version {newest[:8]}" + (f" ({removed} old file(s) removed)" if removed else "")
    else:
        drop_staged(root)
    ensure_packages(root, run)
    ensure_tools(root, fetch)
    if installing:
        make_shortcut(root, run)
    return done


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    installing = "--install" in args
    shortcut = installing and "--no-shortcut" not in args  # --no-shortcut: a trial install beside a real one
    folders = [arg for arg in args if not arg.startswith("--")]
    if installing:
        root = Path(folders[0]) if folders else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "Rose"
    else:
        root = Path(__file__).resolve().parent.parent
    root = root.resolve()
    if (root / ".git").exists():
        print("This is a developer's copy of Rose (it has a .git folder): it is not updated from here.")
        return 0
    try:
        print(update(root, shortcut, fetch, subprocess.run))  # named here, so they are the ones in place when this runs
    except Exception as e:  # noqa: BLE001 - whatever went wrong, say it; an update must not stop Rose from starting
        print(f"Rose could not be {'installed' if installing else 'updated'}: {type(e).__name__}: {e}")
        return 1 if installing else 0
    if installing:
        print(f"\nRose is installed in {root}." + ("\nStart it with the Rose shortcut on your Desktop." if shortcut else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

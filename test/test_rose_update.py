"""scripts/rose_update.py: installing and updating a copy of Rose from GitHub's source zip.

No network and no programs: GitHub and the commands are faked, the folder is a temporary one.
"""

import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rose_update.py"
spec = importlib.util.spec_from_file_location("rose_update", SCRIPT)
rose_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rose_update)

V1, V2, V3 = "1" * 40, "2" * 40, "3" * 40
TOOL_FILES = {tool: b"program" for tool in rose_update.TOOLS}


def zipped(files: dict, top: str = "") -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as packed:
        for name, content in files.items():
            packed.writestr(top + name, content)
    return data.getvalue()


def source(**changes) -> dict:
    lists = {"requirements.txt": ["# App requirements", "keyring==25.7.0", "requests==2.31.0", "# Build requirements", "pyinstaller==6.3.0"],
             "requirements-run.txt": ["requests==2.31.0", "pywebview==6.2.1", "", "# Build requirements"]}
    files = {"main.py": b"print('rose')", "Start Rose.bat": b"@echo off" + bytes([10]),
             **{name: bytes([10]).join(line.encode() for line in lines) for name, lines in lists.items()},
             "Pengu Loader/datastore": b"{}", "main/old_feature.py": b"old"}
    files.update(changes)
    return {name: content for name, content in files.items() if content is not None}


class Github:
    """What GitHub answers, and what was asked"""

    def __init__(self, version=V1, files=None, tools=TOOL_FILES):
        self.version, self.files, self.tools, self.asked = version, files or source(), tools, []

    def __call__(self, url, accept=""):
        self.asked.append(url)
        if "api.github.com" in url:
            return self.version.encode()
        if "/archive/" in url:
            return zipped(self.files, top=f"Rose-{self.version}/")
        if url == rose_update.TOOLS_URL:
            return zipped(self.tools)
        raise AssertionError(f"unexpected address: {url}")

    def downloads(self) -> list:
        return [url for url in self.asked if "api.github.com" not in url]


class UpdateCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "Rose"
        self.commands = []
        quiet = patch("builtins.print")  # the updater says what it does; not in the test run's output
        quiet.start()
        self.addCleanup(quiet.stop)

    def run_command(self, command, check=False, env=None):
        self.commands.append([str(part) for part in command])
        if "venv" in command:  # as the real command leaves it: an environment with its own Python
            python = Path(command[-1]) / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_bytes(b"")

    def update(self, github, installing=False):
        return rose_update.update(self.root, installing, fetch=github, run=self.run_command)


class InstallTests(UpdateCase):
    def test_a_first_install_gets_the_source_the_packages_the_tools_and_a_shortcut(self):
        github = Github()

        self.update(github, installing=True)

        self.assertEqual((self.root / "main.py").read_bytes(), b"print('rose')")
        self.assertEqual((self.root / rose_update.VERSION_FILE).read_text(), V1)
        self.assertTrue(all((self.root / tool).exists() for tool in rose_update.TOOLS))
        kinds = [" ".join(command[1:4]) for command in self.commands]
        self.assertEqual(kinds[0], f"-m venv {self.root / '.venv'}")
        self.assertIn("-m pip install", kinds[1])
        self.assertEqual(self.commands[2][0], "powershell", "the Desktop shortcut")

    def test_a_trial_install_goes_into_the_folder_given_and_makes_no_shortcut(self):
        with patch.object(rose_update, "fetch", Github()), patch.object(rose_update.subprocess, "run", self.run_command):
            code = rose_update.main(["--install", "--no-shortcut", str(self.root)])

        self.assertEqual(code, 0)
        self.assertTrue((self.root / "main.py").exists())
        self.assertFalse(any(command[0] == "powershell" for command in self.commands))

    def test_an_install_that_cannot_reach_github_fails_and_says_so(self):
        def offline(url, accept=""):
            raise OSError("no internet")

        with patch.object(rose_update, "fetch", offline), patch("builtins.print") as said:
            code = rose_update.main(["--install", str(self.root)])

        self.assertEqual(code, 1)
        self.assertIn("could not be installed", said.call_args.args[0])


class UpdateTests(UpdateCase):
    def setUp(self):
        super().setUp()
        self.update(Github(), installing=True)
        self.commands.clear()

    def test_nothing_new_downloads_nothing_and_installs_nothing(self):
        github = Github()

        self.assertEqual(self.update(github), "Rose is up to date")
        self.assertEqual(github.downloads(), [])
        self.assertEqual(self.commands, [])

    def test_a_new_version_replaces_changed_files_adds_new_ones_and_removes_those_that_are_gone(self):
        github = Github(V2, source(**{"main.py": b"print('newer')", "main/new_feature.py": b"new", "main/old_feature.py": None}))

        said = self.update(github)

        self.assertEqual((self.root / "main.py").read_bytes(), b"print('newer')")
        self.assertTrue((self.root / "main" / "new_feature.py").exists())
        self.assertFalse((self.root / "main" / "old_feature.py").exists())
        self.assertEqual((self.root / rose_update.VERSION_FILE).read_text(), V2)
        self.assertIn("1 old file(s) removed", said)
        self.assertEqual(self.commands, [], "the package list did not change")

    def test_what_this_pc_wrote_itself_is_left_alone(self):
        (self.root / "Pengu Loader" / "datastore").write_bytes(b'{"mine": 1}')
        (self.root / "state.json").write_bytes(b"not from the source")

        self.update(Github(V2, source(**{"Pengu Loader/datastore": b"{}"})))

        self.assertEqual((self.root / "Pengu Loader" / "datastore").read_bytes(), b'{"mine": 1}')
        self.assertTrue((self.root / "state.json").exists())
        self.assertTrue(all((self.root / tool).exists() for tool in rose_update.TOOLS))

    def test_a_file_that_did_not_change_is_not_written_again(self):
        bat = self.root / "Start Rose.bat"
        before = bat.stat().st_mtime_ns
        with patch.object(Path, "write_bytes", autospec=True, side_effect=Path.write_bytes) as written:
            self.update(Github(V2, source(**{"main.py": b"print('newer')"})))

        self.assertEqual([call.args[0].name for call in written.call_args_list], ["main.py"])
        self.assertEqual(bat.stat().st_mtime_ns, before)

    def test_a_batch_file_gets_windows_line_ends_whatever_git_stored(self):
        unix, windows = bytes([10]), bytes([13, 10])
        self.update(Github(V2, source(**{"Start Rose.bat": b"@echo off" + unix + b"goto end" + unix + b":end" + unix})))

        self.assertEqual((self.root / "Start Rose.bat").read_bytes(), b"@echo off" + windows + b"goto end" + windows + b":end" + windows)
        with patch.object(Path, "write_bytes", autospec=True, side_effect=Path.write_bytes) as written:
            self.update(Github("3" * 40, source(**{"Start Rose.bat": b"@echo off" + windows + b"goto end" + unix + b":end" + unix})))
        self.assertEqual(written.call_args_list, [], "the same lines again: the running file is left alone")

    def test_packages_are_installed_again_only_when_the_list_changed(self):
        self.update(Github(V2, source(**{"requirements-run.txt": b"requests==2.32.0\n"})))

        self.assertEqual(len(self.commands), 1)
        self.assertIn("pip", self.commands[0])

    def test_the_packages_are_both_lists_without_what_only_a_build_needs(self):
        self.assertEqual(rose_update.package_list(self.root).split(), ["keyring==25.7.0", "requests==2.31.0", "pywebview==6.2.1"])
        newer_build = b"keyring==25.7.0" + bytes([10]) + b"requests==2.31.0" + bytes([10]) + b"# Build requirements" + bytes([10]) + b"pyinstaller==7.0"

        self.update(Github(V2, source(**{"requirements.txt": newer_build})))

        self.assertEqual(self.commands, [], "a change to the build's packages installs nothing")

    def test_packages_that_failed_to_install_are_tried_again_at_the_next_start(self):
        def failing(command, check=False, env=None):
            raise OSError("pip failed")

        with self.assertRaises(OSError):
            rose_update.update(self.root, False, fetch=Github(V2, source(**{"requirements-run.txt": b"x==1\n"})), run=failing)
        self.update(Github(V2, source(**{"requirements-run.txt": b"x==1\n"})))

        self.assertEqual(len(self.commands), 1)

    def test_missing_tools_are_downloaded_again_and_an_incomplete_download_is_an_error(self):
        (self.root / rose_update.TOOLS[0]).unlink()
        github = Github()

        self.update(github)

        self.assertEqual(github.downloads(), [rose_update.TOOLS_URL])
        (self.root / rose_update.TOOLS[0]).unlink()
        with self.assertRaises(ValueError):
            self.update(Github(tools={rose_update.TOOLS[1]: b"x"}))

    def test_an_update_that_fails_never_keeps_rose_from_starting(self):
        def offline(url, accept=""):
            raise OSError("no internet")

        script_in_copy = self.root / "scripts" / "rose_update.py"
        with patch.object(rose_update, "__file__", str(script_in_copy)), patch.object(rose_update, "fetch", offline), \
                patch("builtins.print") as said:
            code = rose_update.main([])

        self.assertEqual(code, 0)
        self.assertIn("could not be updated", said.call_args.args[0])
        self.assertEqual((self.root / "main.py").read_bytes(), b"print('rose')")


class WhileRoseRunsTests(UpdateCase):
    """stage(): a new version is downloaded while Rose runs (main/self_update.py) and installed at the next start"""

    def setUp(self):
        super().setUp()
        self.update(Github(), installing=True)
        self.commands.clear()
        self.newer = Github(V2, source(**{"main.py": b"print('newer')"}))

    def waiting(self) -> list:
        return sorted(path.name for path in self.root.iterdir() if path.name.startswith(".rose-update"))

    def test_a_new_version_is_downloaded_and_not_installed(self):
        self.assertEqual(rose_update.stage(self.root, self.newer), V2)

        self.assertEqual(self.waiting(), [".rose-update-version", ".rose-update.zip"])
        self.assertEqual((self.root / "main.py").read_bytes(), b"print('rose')", "Rose is running from these files")
        self.assertEqual((self.root / rose_update.VERSION_FILE).read_text(), V1)

    def test_nothing_new_downloads_nothing(self):
        github = Github()

        self.assertEqual(rose_update.stage(self.root, github), "")
        self.assertEqual((github.downloads(), self.waiting()), ([], []))

    def test_a_version_already_downloaded_is_not_downloaded_again(self):
        rose_update.stage(self.root, self.newer)
        again = Github(V2, self.newer.files)

        self.assertEqual(rose_update.stage(self.root, again), V2)
        self.assertEqual(again.downloads(), [])

    def test_the_next_start_installs_it_without_downloading_it_again(self):
        rose_update.stage(self.root, self.newer)
        at_start = Github(V2, self.newer.files)

        said = self.update(at_start)

        self.assertIn("now at version 22222222", said)
        self.assertEqual((self.root / "main.py").read_bytes(), b"print('newer')")
        self.assertEqual((at_start.downloads(), self.waiting()), ([], []))

    def test_without_internet_the_next_start_still_installs_it(self):
        rose_update.stage(self.root, self.newer)

        def offline(url, accept=""):
            raise OSError("no internet")

        self.update(offline)

        self.assertEqual((self.root / "main.py").read_bytes(), b"print('newer')")
        self.assertEqual((self.root / rose_update.VERSION_FILE).read_text(), V2)

    def test_a_version_newer_than_the_downloaded_one_wins(self):
        rose_update.stage(self.root, self.newer)
        newest = Github(V3, source(**{"main.py": b"print('newest')"}))

        self.update(newest)

        self.assertEqual((self.root / "main.py").read_bytes(), b"print('newest')")
        self.assertEqual((len(newest.downloads()), self.waiting()), (1, []))

    def test_a_damaged_download_is_not_kept(self):
        def damaged(url, accept=""):
            return V2.encode() if "api.github.com" in url else b"<html>try again later</html>"

        with self.assertRaises(zipfile.BadZipFile):
            rose_update.stage(self.root, damaged)
        self.assertEqual(self.waiting(), [])

    def test_a_download_the_start_cannot_use_is_dropped_and_rose_starts(self):
        rose_update.stage(self.root, self.newer)
        (self.root / rose_update.STAGED_FILE).write_bytes(b"cut short")
        script_in_copy = self.root / "scripts" / "rose_update.py"

        with patch.object(rose_update, "__file__", str(script_in_copy)), patch.object(rose_update, "fetch", Github(V2, self.newer.files)),                 patch("builtins.print"):
            code = rose_update.main([])

        self.assertEqual((code, self.waiting()), (0, []), "the next start downloads anew")
        self.assertEqual((self.root / "main.py").read_bytes(), b"print('rose')")

    def test_a_developers_copy_downloads_nothing(self):
        (self.root / ".git").mkdir()

        def never(url, accept=""):
            raise AssertionError("GitHub must not be asked")

        self.assertEqual(rose_update.stage(self.root, never), "")


class SafetyTests(UpdateCase):
    def test_start_rose_bat_keeps_the_lines_a_running_copy_has_read(self):
        """An update replaces Start Rose.bat while cmd runs it, and cmd reads on from where it was: everything
        up to the line that starts Rose must stay byte for byte, new lines go below it."""
        lines = (SCRIPT.parents[1] / "Start Rose.bat").read_text(encoding="utf-8").splitlines()
        first_start = lines.index(r'".venv\Scripts\python.exe" main.py')

        self.assertEqual(first_start, 17)
        self.assertEqual(lines[15:17], [r'".venv\Scripts\python.exe" scripts\rose_update.py',
                                        "echo Starting Rose. Keep this window open; close it to stop Rose."])
        self.assertEqual((lines[0], lines[9], lines[18]), ("@echo off", 'cd /d "%~dp0"', ":ended"))
        self.assertIn('if exist ".rose-restart" goto again', lines[18:])

    def test_a_developers_copy_is_never_touched(self):
        (self.root / ".git").mkdir(parents=True)
        (self.root / "main.py").write_bytes(b"my work")

        def never(url, accept=""):
            raise AssertionError("GitHub must not be asked")

        with patch.object(rose_update, "fetch", never), patch("builtins.print"):
            code = rose_update.main(["--install", str(self.root)])

        self.assertEqual(code, 0)
        self.assertEqual((self.root / "main.py").read_bytes(), b"my work")

    def test_a_zip_cannot_write_outside_roses_folder(self):
        for name in ("../evil.py", "a/../../evil.py", "/evil.py", "C:/evil.py", "\\evil.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                rose_update.unpack(zipped({name: b"x"}), self.root, strip_top=False)
        self.assertFalse((self.root.parent / "evil.py").exists())

    def test_only_a_commit_id_is_taken_for_a_version(self):
        self.assertEqual(rose_update.latest_version(lambda url, accept="": V1.encode() + b"\n"), V1)
        for answer in (b"", b"<html>rate limit</html>", b"../../x", V1.encode()[:39]):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                rose_update.latest_version(lambda url, accept="": answer)


if __name__ == "__main__":
    unittest.main()

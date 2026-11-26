"""scripts/publish.py: the check that keeps private values and keys out of what is published.

The private values here are made up; the real ones of this PC are never read by these tests. The samples of
keys and tokens are put together from pieces, so this file itself holds nothing shaped like one.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish.py"
spec = importlib.util.spec_from_file_location("publish", SCRIPT)
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)

WORD = "an account's riot_id (a word of it)"
VALUES = {"jdoe42": "the Windows user name", "starfall": WORD, "bob": WORD, "jane.doe@example.org": "an email address of the local commits"}


def kinds(files=None, message="Update") -> list:
    return publish.audit(files or {}, message, VALUES)


class AuditTests(unittest.TestCase):
    def test_clean_files_and_message_pass(self):
        self.assertEqual(kinds({"main/app.py": b"print('hello')", "docs/notes.md": b"The account joined a game."}), [])

    def test_a_private_value_is_found_whatever_its_capitals_and_told_by_kind_and_place_only(self):
        hits = kinds({"tools/check.exe": b"\x00\x01C:\\Users\\JDoe42\\.cargo\\registry\x00", "docs/a.md": b"signed in as StarFall today"})

        self.assertEqual(sorted(hits), [(WORD, "docs/a.md"), ("the Windows user name", "tools/check.exe")])
        self.assertFalse(any("jdoe42" in str(hit).lower() or "starfall" in str(hit).lower() for hit in hits), "the value itself is never told")

    def test_a_short_value_counts_as_a_whole_word_only(self):
        self.assertEqual(kinds({"a.py": b"# League on Bob, then restart"}), [(WORD, "a.py")])
        self.assertEqual(kinds({"a.py": b"bobsled = bobbin and kabob"}), [])
        self.assertEqual(kinds({"a.dll": b"\x00\x00 bob \x00"}), [], "a program's bytes hold every short word")

    def test_the_commit_message_and_file_names_are_checked_too(self):
        self.assertEqual(kinds(message="restart League once (the starfall bug)"), [(WORD, "the commit message")])
        self.assertEqual(kinds({"notes/jdoe42.txt": b"x"}), [("the Windows user name", "notes/jdoe42.txt")])

    def test_keys_and_tokens_are_found_by_their_shape(self):
        samples = {"a GitHub token": b"token = gh" + b"p_" + b"a1B2" * 9,
                   "a private key": b"-----BEGIN RSA " + b"PRIVATE KEY-----",
                   "a sign-in token (JWT)": b"ey" + b"JhbGciOiJIUzI1NiJ9abc." + b"ey" + b"JzdWIiOiIxMjM0NTY3ODkwIn0.sig",
                   "a Riot client password": b"Authorization: Ba" + b"sic " + b"cmlvdDphYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3g=",
                   "a link with a signature": b"https://cdn.example.com/file.zip?to" + b"ken=" + b"abcdefghijklmnop1234",
                   "a chat webhook": b"https://discord.com/api/web" + b"hooks/123456789/abc"}
        for kind, data in samples.items():
            with self.subTest(kind=kind):
                self.assertEqual(kinds({"x.txt": data}), [(kind, "x.txt")])

    def test_a_looked_at_coincidence_is_let_through_only_in_its_own_file(self):
        czech = "Pengu Loader/plugins/ROSE-I18n/locales/cs.json"
        self.assertEqual(kinds({czech: b'"day": "bob"'}), [])
        self.assertEqual(kinds({"other.json": b'"day": "bob"'}), [(WORD, "other.json")])
        self.assertEqual(kinds({czech: b"jdoe42"}), [("the Windows user name", czech)], "only the kind that was looked at")

    def test_what_is_part_of_the_owners_github_name_is_not_private(self):
        search = publish.searcher({value: kind for value, kind in VALUES.items() if value not in "starfallgames"})

        self.assertEqual(search(b"github.com/StarfallGames/Rose"), set())
        self.assertEqual(search(b"C:\\Users\\jdoe42"), {"the Windows user name"})


class OrdinaryHereTests(unittest.TestCase):
    """.git/rose-ordinary.txt: everyday words this PC's owner said are not private. Made-up account here."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rose_publish_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / ".git").mkdir()
        accounts = self.root / "appdata" / "Rose" / "accounts"
        accounts.mkdir(parents=True)
        (accounts / "accounts.json").write_text(json.dumps({"accounts": [{"riot_id": "Starfall Bob#EUW9", "login": "starfall"}]}),
                                                encoding="utf-8")
        for started in (patch.object(publish, "ROOT", self.root), patch.object(publish, "git", return_value=b""),
                        patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "appdata"), "USERNAME": "jdoe42", "COMPUTERNAME": "PC-TEST"})):
            started.start()
            self.addCleanup(started.stop)

    def test_without_the_file_every_word_of_an_account_is_private(self):
        self.assertEqual(publish.ordinary_here(self.root), set())
        values = publish.private_values("someowner")
        self.assertLessEqual({"starfall", "bob", "euw9", "starfall bob#euw9"}, set(values))

    def test_a_word_on_the_list_is_no_longer_searched_for_and_the_whole_name_still_is(self):
        (self.root / ".git" / "rose-ordinary.txt").write_text("Starfall\r\n\r\n", encoding="utf-8-sig")  # as an editor saves it

        self.assertEqual(publish.ordinary_here(self.root), {"starfall"})
        values = publish.private_values("someowner")
        self.assertNotIn("starfall", values, "also where it is a whole value: the login is that word")
        self.assertLessEqual({"bob", "euw9", "starfall bob#euw9", "jdoe42"}, set(values), "nothing else is let go")
        hits = publish.audit({"old/public.md": b"a starfall of sparks", "new/leak.md": b"signed in as Starfall Bob#EUW9"}, "Update", values)
        self.assertEqual({place for _kind, place in hits}, {"new/leak.md"}, "the old file with the everyday word passes")


class PublicParentsTests(unittest.TestCase):
    def test_a_merge_of_the_original_is_published_as_a_merge_and_only_once(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args) -> str:
                made_up = ["-c", "user.name=Tester", "-c", "user.email=tester@example.org", "-c", "commit.gpgsign=false"]
                return subprocess.run(["git", *made_up, *args], cwd=folder, capture_output=True, check=True).stdout.decode().strip()

            git("init", "-q", "-b", "main")
            git("commit", "-q", "--allow-empty", "-m", "the original, at the fork point")
            fork_point = git("rev-parse", "HEAD")
            git("commit", "-q", "--allow-empty", "-m", "the original, newer")
            newer = git("rev-parse", "HEAD")
            git("update-ref", "refs/remotes/origin/main", newer)
            git("reset", "-q", "--hard", fork_point)
            git("commit", "-q", "--allow-empty", "-m", "the fork's own work")
            published = git("commit-tree", "HEAD^{tree}", "-p", fork_point, "-m", "public")

            self.assertEqual(publish.public_parents(published, cwd=folder), [published], "HEAD does not hold the original's newer commit")

            git("merge", "-q", "--no-edit", newer)
            self.assertEqual(publish.public_parents(published, cwd=folder), [published, newer])

            merged = git("commit-tree", "HEAD^{tree}", "-p", published, "-p", newer, "-m", "public merge")
            self.assertEqual(publish.public_parents(merged, cwd=folder), [merged], "what is published already holds it")


if __name__ == "__main__":
    unittest.main()

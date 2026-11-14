"""scripts/publish.py: the check that keeps private values and keys out of what is published.

The private values here are made up; the real ones of this PC are never read by these tests. The samples of
keys and tokens are put together from pieces, so this file itself holds nothing shaped like one.
"""

import importlib.util
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

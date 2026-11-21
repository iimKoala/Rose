"""main/cs_rate.py: the build strip's CS-a-minute readout, from the game's own live data. No game, no window."""

import unittest

from main import cs_rate

ME = {"riotId": "Player One#NA1", "summonerName": "Player One", "scores": {"creepScore": 47, "kills": 1}}
OTHER = {"riotId": "Someone Else#NA1", "summonerName": "Someone Else", "scores": {"creepScore": 12}}


def game(me=ME, seconds=372.5, active=None) -> dict:
    return {"activePlayer": active or {"riotId": "Player One#NA1", "summonerName": "Player One"},
            "allPlayers": [OTHER, me], "gameData": {"gameTime": seconds}}


class ReadTests(unittest.TestCase):
    def test_the_count_and_the_time_of_the_player_at_this_computer(self):
        self.assertEqual(cs_rate.read_cs(game()), (47, 372.5))

    def test_an_older_game_that_names_the_player_without_a_tag(self):
        self.assertEqual(cs_rate.read_cs(game(active={"summonerName": "Player One"})), (47, 372.5))

    def test_a_missing_name_never_matches_a_missing_name(self):
        """None equals None: players listed without a summonerName must not all pass for the user, whose
        own summonerName is missing too. The first one's count would be shown as the user's."""
        others = [{"riotId": "Someone Else#NA1", "scores": {"creepScore": 12}},
                  {"riotId": "Player One#NA1", "scores": {"creepScore": 47}}]
        data = {"activePlayer": {"riotId": "Player One#NA1"}, "allPlayers": others, "gameData": {"gameTime": 372.5}}
        self.assertEqual(cs_rate.read_cs(data), (47, 372.5))
        nameless = {"activePlayer": {}, "allPlayers": [{"scores": {"creepScore": 5}}], "gameData": {"gameTime": 100.0}}
        self.assertIsNone(cs_rate.read_cs(nameless), "nobody is known to be the user")

    def test_data_without_the_player_the_count_or_the_time_reads_as_nothing(self):
        self.assertIsNone(cs_rate.read_cs({}))
        self.assertIsNone(cs_rate.read_cs({"activePlayer": None, "allPlayers": None, "gameData": None}))
        self.assertIsNone(cs_rate.read_cs(game(active={"riotId": "Nobody#NA1"})))
        self.assertIsNone(cs_rate.read_cs(game(me={**ME, "scores": {"kills": 1}})))
        self.assertIsNone(cs_rate.read_cs({**game(), "gameData": {"gameMode": "CLASSIC"}}))


class RateTests(unittest.TestCase):
    def test_a_count_that_moves_by_one_is_the_count_over_the_minutes(self):
        rate = cs_rate.CsRate()
        self.assertAlmostEqual(rate.update(47, 372.0), 47 / 6.2)
        self.assertAlmostEqual(rate.update(50, 400.0), 7.5, msg="exact for good, also on a multiple of ten")
        self.assertAlmostEqual(rate.update(50, 600.0), 5.0, msg="no minion for 200 seconds: the rate falls")

    def test_a_count_that_moves_in_tens_is_exact_when_it_moves_and_bounded_after(self):
        rate = cs_rate.CsRate()
        self.assertEqual(rate.update(0, 120.0), 0.0)
        self.assertAlmostEqual(rate.update(10, 150.0), 4.0)
        self.assertAlmostEqual(rate.update(10, 200.0), 4.0, msg="up to 9 more may have died: no reason to fall yet")
        self.assertAlmostEqual(rate.update(10, 300.0), 3.8, msg="even 19 minions in 5 minutes are 3.8")
        self.assertAlmostEqual(rate.update(20, 300.0), 4.0)

    def test_nothing_is_said_before_the_first_minions_can_have_died(self):
        rate = cs_rate.CsRate()
        self.assertIsNone(rate.update(0, 30.0))
        self.assertIsNone(rate.update(3, cs_rate.MIN_GAME_S - 0.1))
        self.assertAlmostEqual(rate.update(3, cs_rate.MIN_GAME_S), 2.0)

    def test_a_strip_started_in_the_middle_of_a_game(self):
        """Rose was restarted: the first count seen is already large, and nobody knows when it last moved"""
        rate = cs_rate.CsRate()
        self.assertAlmostEqual(rate.update(120, 900.0), 8.0)
        self.assertAlmostEqual(rate.update(120, 930.0), 8.0, msg="between 120 and 129 in 15.5 minutes")


class LabelTests(unittest.TestCase):
    def test_one_decimal_and_a_dash_for_nothing(self):
        self.assertEqual(cs_rate.label(7.5806), "CS/min 7.6")
        self.assertEqual(cs_rate.label(0.0), "CS/min 0.0")
        self.assertEqual(cs_rate.label(None), "CS/min –")


if __name__ == "__main__":
    unittest.main()

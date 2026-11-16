"""main/onetricks.py and main/build_service.py: whose builds the champ select panel shows for a lane.

No network: the players and the lane shares are made up.
"""

import unittest
from unittest.mock import patch

from main import build_service, onetricks


def player(name: str, lane: str) -> dict:
    return {"name": name, "lane": lane, "puuid": name}


# In the ranking's order: A is the champion's best player
RANKED = [player("A", "top"), player("B", "jungle"), player("C", "top"), player("D", "mid"), player("E", "jungle"), player("F", "top")]
MOSTLY_TOP = {"top": 0.6, "jungle": 0.3, "mid": 0.1, "bot": 0.0, "supp": 0.0}


def names(players: list) -> str:
    return "".join(one["name"] for one in players)


class ByLaneTests(unittest.TestCase):
    def test_the_lanes_own_players_come_first_then_the_champions_main_lane_then_the_rest(self):
        self.assertEqual(names(onetricks.by_lane(RANKED, MOSTLY_TOP, "jungle")), "BE" + "ACF" + "D")

    def test_a_lane_nobody_plays_falls_back_to_the_champions_main_lane(self):
        self.assertEqual(names(onetricks.by_lane(RANKED, MOSTLY_TOP, "supp")), "ACF" + "BDE")

    def test_no_lane_given_starts_with_the_champions_main_lane(self):
        self.assertEqual(names(onetricks.by_lane(RANKED, MOSTLY_TOP)), "ACF" + "BDE")
        self.assertEqual(names(onetricks.by_lane(RANKED, MOSTLY_TOP, "top")), "ACF" + "BDE", "the main lane itself gives the same")

    def test_a_page_without_lane_games_keeps_the_rankings_order(self):
        self.assertEqual(names(onetricks.by_lane(RANKED, dict.fromkeys(onetricks.LANES, 0.0))), "ABCDEF")
        self.assertEqual(names(onetricks.by_lane(RANKED, {}, "mid")), "D" + "ABCEF")

    def test_the_panel_tries_the_players_in_that_order(self):
        with patch.object(build_service, "_ranking", return_value=(RANKED, MOSTLY_TOP)):
            self.assertEqual(names(build_service._candidates("Champion", "jungle")), "BEACFD")
            self.assertEqual(names(build_service._candidates("Champion", "")), "ACFBDE")


if __name__ == "__main__":
    unittest.main()

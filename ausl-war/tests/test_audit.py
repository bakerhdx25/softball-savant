import unittest

from ausl_war.audit import count_boxscore_players, count_plays, payload_quality, semantic_presence


class PayloadAuditTests(unittest.TestCase):
    def test_counts_raw_plays(self):
        self.assertEqual(count_plays({"plays": [{}, {}, {}]}), 3)

    def test_counts_distinct_boxscore_players(self):
        payload = {
            "team": {
                "players": [
                    {"id": "p1", "first_name": "A"},
                    {"id": "p2", "last_name": "B"},
                ],
                "groups": [{"stats": [{"player_id": "p1", "stats": {"AB": 3}}]}],
            }
        }
        self.assertEqual(count_boxscore_players(payload), 2)

    def test_semantic_scan_checks_paths_and_templates(self):
        payload = {
            "plays": [
                {
                    "pitcher_id": "p1",
                    "outs": 1,
                    "final_details": [{"template": "Runner stole second"}],
                }
            ]
        }
        presence = semantic_presence(payload)
        self.assertTrue(presence["pitcher_identity"])
        self.assertTrue(presence["outs"])
        self.assertTrue(presence["stolen_bases"])

    def test_quality_prefers_more_plays_then_players(self):
        boxscore = {"players": [{"id": "p1", "first_name": "A"}]}
        self.assertEqual(payload_quality(boxscore, {"plays": [{}, {}]})[:2], (2, 1))


if __name__ == "__main__":
    unittest.main()


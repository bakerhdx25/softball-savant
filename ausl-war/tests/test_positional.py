import unittest

from ausl_war.positional import (
    build_position_exposure,
    center_position_scale,
    split_positions,
    weighted_player_adjustment,
)


class PositionalResearchTests(unittest.TestCase):
    def test_split_positions_preserves_sequence(self):
        self.assertEqual(split_positions("DH, 1B, P"), ["DH", "1B", "P"])
        self.assertEqual(split_positions(None), [])

    def test_candidate_scale_is_opportunity_centered(self):
        centered = center_position_scale(
            {"SS": 5.0, "1B": -3.0}, {"SS": 100.0, "1B": 200.0}
        )
        self.assertAlmostEqual(centered["SS"] * 100 + centered["1B"] * 200, 0.0)

    def test_multi_position_adjustment_is_innings_weighted(self):
        result = weighted_player_adjustment(
            {"SS": 300.0, "1B": 225.0}, {"SS": 6.0, "1B": -4.0}
        )
        self.assertAlmostEqual(result, 6.0 * 300 / 525 - 4.0 * 225 / 525)

    def test_innings_are_allocated_only_for_clean_team_games(self):
        positions = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
        box = [
            {
                "role": "hitting", "canonical_id": "game", "team": "Club",
                "season": 2026, "player": f"Player {position}",
                "player_key": f"player{position.lower()}", "position": position,
            }
            for position in positions
        ]
        event = {
            "canonical_id": "game", "season": 2026, "fielding_team": "Club",
            "outs_before": 0, "outs_after": 3, "pitch_text": "",
            "play_text": "",
        }
        rows, audit, _ = build_position_exposure(box, [event])
        self.assertEqual(audit["team_games_with_confirmed_position_innings"], 1)
        self.assertTrue(all(row["confirmed_defensive_outs"] == 3 for row in rows))

        substituted = {**event, "pitch_text": "Lineup changed: Runner in for batter"}
        rows, audit, _ = build_position_exposure(box, [substituted])
        self.assertEqual(audit["team_games_with_confirmed_position_innings"], 0)
        self.assertTrue(all(row["confirmed_defensive_outs"] == 0 for row in rows))


if __name__ == "__main__":
    unittest.main()

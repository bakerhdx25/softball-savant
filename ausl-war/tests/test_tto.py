import unittest

from ausl_war.tto import (
    _official_event_type,
    _reconstruct_team_pitchers,
    aggregate_rows,
    assign_series_ids,
    canonical_person_key,
    derive_exposures,
)


def event(order, batter, pitcher, outs_before, outs_after, play_text):
    return {
        "canonical_id": "game-1",
        "source_game_id": "source-1",
        "season": 2026,
        "inning": order,
        "half": "top",
        "event_order": order,
        "display_row_index": order,
        "event_type": "out",
        "is_plate_appearance": True,
        "batting_team": "Batters",
        "fielding_team": "Fielders",
        "batter": batter,
        "pitcher": pitcher,
        "outs_before": outs_before,
        "outs_after": outs_after,
        "bases_before": 0,
        "bases_after": 0,
        "runners_before": {},
        "runners_after": {},
        "runs_scored": 0,
        "runner_actions": [],
        "pitch_text": "In play.",
        "play_text": play_text,
    }


class TTOTests(unittest.TestCase):
    def test_identity_aliases_cover_known_cross_season_changes(self):
        self.assertEqual(canonical_person_key("Odicci Alexander"), "odiccialexanderbennett")
        self.assertEqual(canonical_person_key("Payton Gotshall"), "paytongottshall")

    def test_official_action_codes_classify_plate_appearances(self):
        self.assertEqual(_official_event_type("HR RC RBI2", ""), "home_run")
        self.assertEqual(_official_event_type("KS", ""), "strikeout")
        self.assertEqual(_official_event_type("FC 6", ""), "fielders_choice")
        self.assertEqual(_official_event_type("E6F", ""), "reached_on_error")
        self.assertEqual(_official_event_type("SF 8 RBI", ""), "sacrifice_fly")

    def test_boxscore_constrained_reconstruction_preserves_reentry(self):
        rows = [
            event(1, "Hitter A", "Pitcher A", 0, 1, "Hitter A grounds out, Pitcher A pitching."),
            event(2, "Hitter B", "Pitcher A", 0, 1, "Hitter B grounds out, Pitcher B pitching."),
            event(3, "Hitter A", "Pitcher B", 0, 1, "Hitter A grounds out, Pitcher A pitching."),
        ]
        pitchers = [
            {"player": "Pitcher A", "innings_decimal": 2 / 3},
            {"player": "Pitcher B", "innings_decimal": 1 / 3},
        ]
        rebuilt, audit = _reconstruct_team_pitchers(rows, pitchers)
        self.assertEqual([row["pitcher"] for row in rebuilt], ["Pitcher A", "Pitcher B", "Pitcher A"])
        self.assertEqual(audit["optimal_paths"], 1)

    def test_same_pitcher_encounter_continues_after_reentry(self):
        rows = [
            event(1, "Hitter A", "Pitcher A", 0, 1, "Hitter A grounds out, Pitcher A pitching."),
            event(2, "Hitter B", "Pitcher B", 0, 1, "Hitter B grounds out, Pitcher B pitching."),
            event(3, "Hitter A", "Pitcher A", 0, 1, "Hitter A grounds out, Pitcher A pitching."),
        ]
        for row in rows:
            row["pitcher_key"] = canonical_person_key(row["pitcher"])
            row["pitcher_attribution_ambiguous"] = False
            row["pitcher_attribution_method"] = "explicit_play_text"
        valued = [{**row, "run_value": 0.0} for row in rows]
        official = {
            "game-1": {
                "gameId": 1,
                "gameDateIso": "2026-06-01T12:00:00-04:00",
            }
        }
        series = {"game-1": {"series_id": "series-1", "series_game_number": 1, "series_source": "test"}}
        weights = {"scaled_weights": {}}
        enriched = derive_exposures(
            rows,
            valued,
            {"out": 0.0},
            [{"canonical_id": "game-1", "start_ts": "2026-06-01T16:00:00Z"}],
            official,
            series,
            weights,
        )
        self.assertEqual(enriched[0]["same_game_matchup_number"], 1)
        self.assertEqual(enriched[2]["same_game_matchup_number"], 2)

    def test_regular_series_resets_when_same_venue_games_are_separated(self):
        def official(game_id, date):
            return {
                "gameId": game_id,
                "seasonId": 369,
                "gameDateIso": date,
                "gameTypeLk": "RS",
                "seriesId": None,
                "competitors": [{"name": "Bandits"}, {"name": "Blaze"}],
                "venue": {"name": "Test Park"},
            }
        assigned = assign_series_ids(
            {
                "a": official(1, "2026-06-01T12:00:00-04:00"),
                "b": official(2, "2026-06-03T12:00:00-04:00"),
                "c": official(3, "2026-06-12T12:00:00-04:00"),
            }
        )
        self.assertEqual(assigned["a"]["series_id"], assigned["b"]["series_id"])
        self.assertNotEqual(assigned["b"]["series_id"], assigned["c"]["series_id"])

    def test_basic_metrics(self):
        rows = [
            {"canonical_id": "a", "PA_value": 1, "AB_value": 1, "H_value": 1, "TB_value": 4, "BB_value": 0, "HBP_value": 0, "SF_value": 0, "SO_value": 0, "HR_value": 1, "OBP_num_value": 1, "OBP_den_value": 1, "wOBA_num_value": 2.0, "wOBA_den_value": 1, "run_value": 1.0},
            {"canonical_id": "b", "PA_value": 1, "AB_value": 1, "H_value": 0, "TB_value": 0, "BB_value": 0, "HBP_value": 0, "SF_value": 0, "SO_value": 1, "HR_value": 0, "OBP_num_value": 0, "OBP_den_value": 1, "wOBA_num_value": 0.0, "wOBA_den_value": 1, "run_value": -0.5},
        ]
        result = aggregate_rows(rows, {})
        self.assertEqual(result["AVG"], 0.5)
        self.assertEqual(result["SLG"], 2.0)
        self.assertEqual(result["OPS"], 2.5)
        self.assertEqual(result["RV_per_PA"], 0.25)


if __name__ == "__main__":
    unittest.main()

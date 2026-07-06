import unittest

from ausl_war.normalize import (
    RunnerState,
    apply_pinch_runner_substitution,
    apply_runner_clauses,
    classify_plate_appearance,
    parse_innings,
    normalize_game,
)


class NormalizeTests(unittest.TestCase):
    def test_event_classification_covers_special_outcomes(self):
        self.assertEqual(classify_plate_appearance("A homers on a fly ball"), "home_run")
        self.assertEqual(classify_plate_appearance("A grounds into a double play"), "double_play")
        self.assertEqual(
            classify_plate_appearance("A reaches on dropped 3rd strike (passed ball)"),
            "dropped_third_reached",
        )
        self.assertEqual(classify_plate_appearance("A is intentionally walked"), "intentional_walk")

    def test_softball_innings_parse_as_outs_not_tenths(self):
        self.assertAlmostEqual(parse_innings("6.2"), 6 + 2 / 3)
        with self.assertRaises(ValueError):
            parse_innings("6.3")

    def test_explicit_runner_actions_mutate_state(self):
        state = RunnerState({1: "Runner One", 2: "Runner Two"})
        runs, outs, actions = apply_runner_clauses(
            state,
            "Runner Two scores, Runner One advances to 3rd",
            ["Runner One", "Runner Two"],
        )
        self.assertEqual((runs, outs), (1, 0))
        self.assertEqual(state.runners, {3: "Runner One"})
        self.assertEqual(len(actions), 2)

    def test_explicit_advance_preserves_runner_already_at_destination(self):
        state = RunnerState({1: "Trailing Runner", 2: "Lead Runner"})
        runs, outs, actions = apply_runner_clauses(
            state,
            "Trailing Runner advances to 2nd",
            ["Trailing Runner", "Lead Runner"],
        )
        self.assertEqual((runs, outs), (0, 0))
        self.assertEqual(state.runners, {2: "Trailing Runner", 3: "Lead Runner"})
        self.assertTrue(any(action["action"] == "forced" for action in actions))

    def test_caught_stealing_adds_an_out(self):
        state = RunnerState({1: "Runner"})
        runs, outs, _ = apply_runner_clauses(
            state,
            "Runner caught stealing 2nd, catcher A to second baseman B",
            ["Runner"],
        )
        self.assertEqual((runs, outs), (0, 1))
        self.assertEqual(state.runners, {})

    def test_did_not_score_is_not_counted_as_a_run(self):
        state = RunnerState({3: "Runner"})
        runs, outs, _ = apply_runner_clauses(
            state,
            "Runner did not score",
            ["Runner"],
        )
        self.assertEqual((runs, outs), (0, 0))
        self.assertEqual(state.runners, {3: "Runner"})

    def test_out_at_home_is_an_out_not_a_run(self):
        state = RunnerState({3: "Runner"})
        runs, outs, _ = apply_runner_clauses(
            state,
            "Runner out at home advancing after tag up",
            ["Runner"],
        )
        self.assertEqual((runs, outs), (0, 1))
        self.assertEqual(state.runners, {})

    def test_held_up_is_a_remain_action(self):
        state = RunnerState({2: "Runner"})
        runs, outs, actions = apply_runner_clauses(
            state, "Runner held up at 3rd", ["Runner"]
        )
        self.assertEqual((runs, outs), (0, 0))
        self.assertEqual(state.runners, {3: "Runner"})
        self.assertEqual(actions[0]["action"], "remain")

    def test_pinch_runner_replaces_existing_runner(self):
        state = RunnerState({1: "Old Runner"})
        result = apply_pinch_runner_substitution(
            state,
            "Lineup changed: Pinch runner New Runner in for right fielder Old Runner",
            ["New Runner", "Old Runner"],
        )
        self.assertEqual(result, ("New Runner", "Old Runner", 1))
        self.assertEqual(state.runners, {1: "New Runner"})

    def test_pitcher_change_is_carried_forward(self):
        boxscore = {
            "awayTeamName": "Away",
            "homeTeamName": "Home",
            "hitting": [
                {"Player": name, "teamName": "Away", "R": "0", "H": "0", "BB": "0", "SO": "0"}
                for name in ("Batter One", "Batter Two", "Batter Three")
            ],
            "pitching": [
                {"Player": "Starter Pitcher", "teamName": "Home"},
                {"Player": "Relief Pitcher", "teamName": "Home"},
            ],
        }
        newest_first = [
            {"pitch": "In play.", "play": "Batter Three grounds out to first baseman Fielder One."},
            {"pitch": "Relief Pitcher in for pitcher Starter Pitcher, In play.", "play": "Batter Two singles on a line drive to center fielder Fielder Two."},
            {"pitch": "In play.", "play": "Batter One flies out to left fielder Fielder Three."},
        ]
        events, _ = normalize_game("game", "source", 2026, boxscore, newest_first)
        self.assertEqual(
            [event["pitcher"] for event in events if event["is_plate_appearance"]],
            ["Starter Pitcher", "Relief Pitcher", "Relief Pitcher"],
        )

    def test_explicit_batter_advance_overrides_default_hit_base(self):
        boxscore = {
            "awayTeamName": "Away",
            "homeTeamName": "Home",
            "hitting": [
                {"Player": "Batter One", "teamName": "Away", "R": "0", "H": "1", "BB": "0", "SO": "0"},
                {"Player": "Batter Two", "teamName": "Away", "R": "0", "H": "0", "BB": "0", "SO": "0"},
            ],
            "pitching": [{"Player": "Pitcher One", "teamName": "Home"}],
        }
        newest_first = [
            {"pitch": "In play.", "play": "Batter Two flies out to center fielder Fielder One, Batter One remains at 2nd."},
            {"pitch": "In play.", "play": "Batter One singles on a line drive to center fielder Fielder One, Batter One advances to 2nd on the throw."},
        ]
        events, audit = normalize_game("game", "source", 2026, boxscore, newest_first)
        first, second = [event for event in events if event["is_plate_appearance"]]
        self.assertEqual(first["bases_after"], 2)
        self.assertEqual(first["runners_after"], {"2": "Batter One"})
        self.assertEqual(second["bases_before"], 2)
        self.assertEqual(second["runner_actions"][0]["from_base"], 2)
        self.assertEqual(audit["state_invariant_error_count"], 0)

    def test_runner_state_invariants_detect_duplicate_names(self):
        state = RunnerState({1: "Same Runner", 2: "Same Runner"})
        self.assertTrue(any("duplicate runners" in error for error in state.invariant_errors()))

    def test_single_preserves_unmentioned_forced_runner(self):
        boxscore = {
            "awayTeamName": "Away",
            "homeTeamName": "Home",
            "hitting": [
                {"Player": name, "teamName": "Away", "R": "0", "H": "0", "BB": "0", "SO": "0"}
                for name in ("Runner", "Batter", "Next Batter")
            ],
            "pitching": [{"Player": "Pitcher", "teamName": "Home"}],
        }
        newest_first = [
            {"pitch": "In play.", "play": "Next Batter flies out to left fielder Fielder."},
            {"pitch": "In play.", "play": "Batter singles on a line drive to center fielder Fielder."},
            {"pitch": "In play.", "play": "Runner singles on a line drive to center fielder Fielder."},
        ]
        events, _ = normalize_game("game", "source", 2026, boxscore, newest_first)
        second = [event for event in events if event["is_plate_appearance"]][1]
        self.assertEqual(second["runners_after"], {"1": "Batter", "2": "Runner"})
        self.assertTrue(
            any(action["action"] == "forced" and action["runner"] == "Runner" for action in second["runner_actions"])
        )


if __name__ == "__main__":
    unittest.main()

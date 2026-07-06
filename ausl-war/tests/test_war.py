import unittest

from ausl_war.war import (
    _batted_ball_type,
    _batting_denominator,
    _fielding_target,
    aggregate_offense,
    aggregate_pitching,
    derive_woba_constants,
    double_play_avoidance_runs,
    expanded_baserunning_runs,
    arm_runs,
    add_fip,
    catcher_throwing_runs,
    range_runs,
)


class WarTests(unittest.TestCase):
    def test_fip_is_ausl_centered_and_does_not_create_war(self):
        pitching = [
            {"player_key": "one", "player": "One", "IP": 10.0, "ER": 4},
            {"player_key": "two", "player": "Two", "IP": 10.0, "ER": 8},
        ]
        events = []
        for pitcher, outcomes in (
            ("One", ["strikeout", "strikeout", "walk", "out"]),
            ("Two", ["strikeout", "walk", "walk", "out"]),
        ):
            for event_type in outcomes:
                events.append(
                    {
                        "is_plate_appearance": True,
                        "pitcher": pitcher,
                        "pitcher_key": pitcher.lower(),
                        "event_type": event_type,
                        "play_text": "Batter grounds out" if event_type == "out" else "",
                    }
                )
        audit = add_fip(pitching, events)
        self.assertFalse(audit["war_inclusion"])
        self.assertAlmostEqual(
            sum(row["FIP"] * row["IP"] for row in pitching) / 20,
            audit["league_era"],
        )
        self.assertTrue(all(abs(row["ERA_minus_FIP"] - row["ERA"] + row["FIP"]) < 1e-12 for row in pitching))
        self.assertTrue(all("pitcher_war" not in row for row in pitching))

    def test_catcher_throwing_is_centered_after_shrinkage(self):
        stats = [
            {
                "firstName": name,
                "lastName": "Catcher",
                "fieldingStats": [{"position": "C", "stolenBases": sb, "caughtStealing": cs, "inningsPlayed": 10}],
            }
            for name, sb, cs in (("Good", 2, 3), ("Other", 5, 0))
        ]
        valued = [
            {"event_type": "stolen_base", "run_value": 0.2},
            {"event_type": "caught_stealing", "run_value": -0.5},
        ]
        rows, audit = catcher_throwing_runs(stats, valued)
        self.assertAlmostEqual(sum(row["catcher_throwing_runs"] for row in rows.values()), 0.0)
        self.assertEqual(audit["attempts"], 10)
        self.assertGreater(rows["goodcatcher"]["catcher_throwing_runs"], 0)

    def test_woba_denominator_excludes_ibb_bunts_and_interference(self):
        self.assertEqual(_batting_denominator("single"), 1)
        self.assertEqual(_batting_denominator("intentional_walk"), 0)
        self.assertEqual(_batting_denominator("sacrifice_bunt"), 0)
        self.assertEqual(_batting_denominator("catcher_interference"), 0)

    def test_batted_ball_and_primary_fielder_parse(self):
        text = "A singles on a hard ground ball to third baseman Player Name"
        self.assertEqual(_batted_ball_type(text), "ground")
        self.assertEqual(
            _fielding_target(text, ["Player Name", "Other Player"]),
            ("third baseman", "Player Name"),
        )
        with_later_runner = (
            "A singles to center fielder Actual Fielder, Longer Runner Name advances to 3rd"
        )
        self.assertEqual(
            _fielding_target(with_later_runner, ["Longer Runner Name", "Actual Fielder"]),
            ("center fielder", "Actual Fielder"),
        )

    def test_batting_runs_aggregate_to_league_zero(self):
        event_types = ["out", "single", "double", "triple", "home_run", "walk", "hit_by_pitch"]
        events = []
        for index, event_type in enumerate(event_types):
            events.append(
                {
                    "is_plate_appearance": True,
                    "event_type": event_type,
                    "run_value": -0.3 + index * 0.25,
                    "batter": "Player One" if index % 2 else "Player Two",
                    "batting_team": "Team",
                }
            )
        constants = derive_woba_constants(events, target_events=events)
        offense = aggregate_offense(events, constants)
        self.assertAlmostEqual(sum(row["batting_runs"] for row in offense), 0.0)

    def test_expanded_advancement_and_arm_balance(self):
        re24 = [
            {"outs": outs, "bases": bases, "smoothed_re": (2 - outs) * 0.2 + bases.bit_count() * 0.3}
            for outs in range(3)
            for bases in range(8)
        ]
        events = []
        for runner, destination, fielder in (
            ("Fast Runner", 3, "Good Arm"),
            ("Other Runner", 2, "Other Arm"),
        ):
            after_mask = 1 | (1 << (destination - 1))
            events.append(
                {
                    "is_plate_appearance": True,
                    "event_type": "single",
                    "outs_before": 0,
                    "outs_after": 0,
                    "bases_before": 1,
                    "bases_after": after_mask,
                    "runners_before": {"1": runner},
                    "runners_after": {"1": "Batter", str(destination): runner},
                    "runner_actions": [{"runner": runner, "action": "advance", "from_base": 1, "to_base": destination}],
                    "batter": "Batter",
                    "batting_team": "Offense",
                    "fielding_team": "Defense",
                    "play_text": f"Batter singles on a line drive to center fielder {fielder}, {runner} advances to {destination}rd.",
                }
            )
        offense = [
            {"player_key": "batter", "player": "Batter", "teams": ["Offense"], "reach_opportunities": 2},
            {"player_key": "fastrunner", "player": "Fast Runner", "teams": ["Offense"], "reach_opportunities": 1},
            {"player_key": "otherrunner", "player": "Other Runner", "teams": ["Offense"], "reach_opportunities": 1},
        ]
        players, audit, opportunities = expanded_baserunning_runs(
            events, offense, re24, ["Good Arm", "Other Arm", "Fast Runner", "Other Runner", "Batter"]
        )
        self.assertAlmostEqual(audit["league_non_steal_advancement_runs"], 0.0)
        arm, arm_audit = arm_runs(opportunities)
        self.assertTrue(arm)
        for row in arm.values():
            self.assertAlmostEqual(
                row["arm_runs"], row["pitcher_arm_runs"] + row["non_pitcher_arm_runs"]
            )
        self.assertAlmostEqual(arm_audit["raw_arm_plus_runner_balance"], 0.0)
        self.assertAlmostEqual(arm_audit["league_arm_runs_unshrunk_centered"], 0.0)
        self.assertIn("fastrunner", players)

    def test_range_runs_split_pitcher_from_other_positions(self):
        events = [
            {"event_type": event_type, "play_text": text}
            for event_type, text in (
                ("out", "Batter grounds out to pitcher Pitcher One"),
                ("single", "Batter singles on a ground ball to pitcher Pitcher Two"),
                ("out", "Batter grounds out to shortstop Shortstop One"),
                ("single", "Batter singles on a ground ball to shortstop Shortstop Two"),
            )
        ]
        rows = range_runs(
            events,
            ["Pitcher One", "Pitcher Two", "Shortstop One", "Shortstop Two"],
            conversion_run_value=0.7,
        )
        for row in rows.values():
            self.assertAlmostEqual(
                row["range_runs"], row["pitcher_range_runs"] + row["non_pitcher_range_runs"]
            )
        self.assertEqual(rows["pitcherone"]["pitcher_fielding_opportunities"], 1)
        self.assertEqual(rows["shortstopone"]["non_pitcher_fielding_opportunities"], 1)

    def test_double_play_avoidance_balances_to_zero(self):
        events = [
            {
                "is_plate_appearance": True,
                "event_type": event_type,
                "outs_before": 0,
                "bases_before": 1,
                "batter": player,
                "play_text": f"{player} grounds into a {'double play' if event_type == 'double_play' else 'ground out'} to shortstop Fielder",
                "run_value": run_value,
            }
            for event_type, player, run_value in (
                ("double_play", "Player One", -0.9),
                ("out", "Player Two", -0.2),
            )
        ]
        players, audit = double_play_avoidance_runs(events)
        self.assertEqual(audit["opportunities"], 2)
        self.assertAlmostEqual(
            sum(row["double_play_avoidance_runs"] for row in players.values()), 0.0
        )

    def test_pitching_war_uses_opponent_adjusted_ra7_and_balances(self):
        events = [
            {"season": 2026, "is_plate_appearance": True, "pitcher": pitcher, "batting_team": team, "runs_scored": runs}
            for pitcher, team, runs in (
                ("Pitcher Strong", "Strong", 1),
                ("Pitcher Strong", "Strong", 1),
                ("Pitcher Weak", "Weak", 0),
                ("Pitcher Weak", "Weak", 0),
            )
        ]
        box = [
            {
                "season": 2026, "role": "pitching", "canonical_id": key,
                "team": "Club", "player_key": key, "player": player,
                "innings_decimal": 7.0, "H": 1, "R": 1, "ER": 1, "BB": 0, "SO": 5,
            }
            for key, player in (("pitcherstrong", "Pitcher Strong"), ("pitcherweak", "Pitcher Weak"))
        ]
        pitchers, _ = aggregate_pitching(events, box, games_played=2, runs_per_win=10.0)
        by_key = {row["player_key"]: row for row in pitchers}
        self.assertGreater(
            by_key["pitcherstrong"]["opponent_expected_RA7"],
            by_key["pitcherweak"]["opponent_expected_RA7"],
        )
        self.assertAlmostEqual(
            sum(row["pitching_runs_above_average"] for row in pitchers), 0.0
        )
        self.assertNotIn("pitching_fip_war", by_key["pitcherstrong"])


if __name__ == "__main__":
    unittest.main()

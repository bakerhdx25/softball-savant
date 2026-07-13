import json
import math
import unittest
from collections import defaultdict
from pathlib import Path
from build import (
    CONTACT_EVENT_TYPES,
    NORMALIZED_EVENTS_SOURCE,
    OFFICIAL_EVENTS_SOURCE,
    PA_SOURCE,
    TEAM_META,
    field_location,
    number,
    parse_pitch_sequence,
    team_key,
)


ROOT = Path(__file__).resolve().parent


class SoftballSavantBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = json.loads((ROOT / "data" / "site-data.json").read_text())
        cls.html = (ROOT / "index.html").read_text()
        cls.javascript = (ROOT / "app.js").read_text()
        cls.css = (ROOT / "styles.css").read_text()

    def test_normalized_site_payload_has_every_surface(self):
        self.assertEqual(
            set(self.site),
            {"meta", "directory", "periods", "leaderboards", "tto", "pythagoreanStudy"},
        )
        self.assertEqual(set(self.site["periods"]), {"2025", "2026", "combined"})
        self.assertEqual(set(self.site["leaderboards"]), {"2025", "2026"})
        self.assertEqual(len(self.site["periods"]["2026"]["teams"]), 6)
        self.assertGreaterEqual(self.site["tto"]["meta"]["plate_appearances"], 6192)
        self.assertTrue(any(row.get("wOBA") is not None for row in self.site["leaderboards"]["2026"]))
        self.assertIn("Official AUSL public", self.site["meta"]["sourceNote"])

    def test_directory_includes_current_and_past_players(self):
        self.assertGreaterEqual(len(self.site["directory"]), 140)
        self.assertTrue(any(player["currentRoster"] for player in self.site["directory"]))
        self.assertTrue(any(not player["currentRoster"] for player in self.site["directory"]))
        self.assertTrue(
            all(player["seasons"] or player["currentRoster"] for player in self.site["directory"])
        )

    def test_pythagorean_records_use_standard_formula(self):
        for period in self.site["periods"].values():
            for team in period["teams"]:
                runs = team["summary"]["runs"]
                allowed = team["summary"]["runsAllowed"]
                if not runs and not allowed:
                    self.assertIsNone(team["pythagorean"]["winPct"])
                    continue
                expected_pct = runs**2 / (runs**2 + allowed**2)
                self.assertTrue(math.isclose(team["pythagorean"]["winPct"], expected_pct))
                self.assertEqual(team["pythagorean"]["exponent"], 2.0)

    def test_custom_exponent_is_fit_and_rejected_out_of_sample(self):
        study = self.site["pythagoreanStudy"]
        self.assertEqual(study["teamSeasons"], 10)
        self.assertLess(abs(study["pooledExponent"] - 2.0), 0.3)
        self.assertTrue(all(fold["testMSE"] > fold["standardTestMSE"] for fold in study["crossValidation"]))
        self.assertIn("standard 2.0", study["recommendation"])

    def test_required_navigation_and_deep_routes_are_present(self):
        for route in ("leaderboards", "league", "teams"):
            self.assertIn(f'href="#/{route}"', self.html)
        self.assertNotIn('href="#/methodology"', self.html)
        self.assertNotIn('Players</a>', self.html)
        self.assertIn("#/players/${player.key}", self.javascript)
        self.assertIn("#/teams/${team.key}", self.javascript)
        self.assertIn("window.addEventListener(\"hashchange\"", self.javascript)

    def test_team_page_is_single_destination_with_required_tabs(self):
        for key in ("overview", "roster", "stats", "spray"):
            self.assertIn(f'[\"{key}\"', self.javascript)
        self.assertIn("Spray Charts", self.javascript)
        self.assertIn("Download Scouting Report", self.javascript)
        self.assertIn("PDF report data", self.javascript)
        self.assertIn("Stats period", self.javascript)
        self.assertIn("data-pdf-period", self.javascript)

    def test_player_scouting_features_are_preserved(self):
        for label in (
            "Spray Chart", "Swing Decisions", "Game Logs", "Times Through Order",
            "League Percentiles", "Baserunning", "Fielding", "ERA - FIP",
            "Batter–Pitcher Matchups", "Season History",
        ):
            self.assertIn(label, self.javascript)
        self.assertTrue(any(row["pitches"] > 0 for row in self.site["periods"]["2026"]["leagueApproach"]))
        self.assertTrue(
            any(
                row["pitches"] > 0
                for player in self.site["periods"]["2026"]["players"]
                for row in player["approach"]
            )
        )

    def test_percentile_qualifiers_are_opened_for_short_season_samples(self):
        period = self.site["periods"]["2026"]
        hitter_rate = period["meta"]["hitterQualifierRate"]
        pitcher_rate = period["meta"]["pitcherQualifierRate"]
        self.assertEqual(hitter_rate, 1.5)
        self.assertEqual(pitcher_rate, 0.75)

        active_games = [team["games"] for team in period["teams"] if team["games"]]
        qualifier_games = round(sum(active_games) / len(active_games))
        hitter_qualifier = math.ceil(hitter_rate * qualifier_games)
        pitcher_qualifier = pitcher_rate * qualifier_games
        old_hitter_qualifier = math.ceil(2.0 * qualifier_games)
        old_pitcher_qualifier = 1.0 * qualifier_games
        self.assertLess(hitter_qualifier, old_hitter_qualifier)
        self.assertLess(pitcher_qualifier, old_pitcher_qualifier)

        for player in period["players"]:
            if player.get("percentiles", {}).get("hitting"):
                self.assertGreaterEqual(player["hitting"]["PA"], player["qualifiers"]["hittingPA"])
            if player.get("percentiles", {}).get("pitching"):
                self.assertGreaterEqual(player["pitching"]["IP"], player["qualifiers"]["pitchingIP"])

    def test_pdf_percentile_heading_is_hidden_for_unqualified_players(self):
        pdf_builder = (ROOT.parent / "ausl-scouting-web" / "build_pdfs.py").read_text()
        self.assertIn('if player["percentiles"].get("hitting"):', pdf_builder)
        self.assertIn('drawString(32,228,"League Percentiles")', pdf_builder)

    def test_official_compact_pitch_sequences_restore_swing_decisions(self):
        in_play = parse_pitch_sequence("BB", "single")
        self.assertEqual([pitch["count"] for pitch in in_play], ["0-0", "1-0", "2-0"])
        self.assertFalse(in_play[0]["swing"])
        self.assertTrue(in_play[-1]["swing"])
        self.assertEqual(in_play[-1]["action"], "X")
        self.assertEqual(parse_pitch_sequence("", "single")[0]["count"], "0-0")
        self.assertTrue(parse_pitch_sequence("", "single")[0]["swing"])

        walk = parse_pitch_sequence("BBBB", "walk")
        self.assertEqual(len(walk), 4)
        self.assertEqual(walk[-1]["count"], "3-0")
        self.assertFalse(walk[-1]["swing"])

        strikeout = parse_pitch_sequence("KKBFS", "strikeout")
        self.assertEqual(strikeout[-1]["count"], "1-2")
        self.assertTrue(strikeout[-1]["swing"])

        hbp = parse_pitch_sequence("KB", "hit_by_pitch")
        self.assertEqual(hbp[-1]["count"], "1-1")
        self.assertFalse(hbp[-1]["swing"])
        self.assertFalse(hbp[-1]["called"])

    def test_official_spray_locations_include_shorthand_and_hits(self):
        self.assertEqual(field_location("Morgan Zerkle doubled to left center (1-0 B)."), "Left Field")
        self.assertEqual(field_location("Caroline Jacobsen singled up the middle (0-0)."), "Center Field")
        self.assertEqual(field_location("Cori McMillan singled through the left side (1-1 FB)."), "Shortstop")
        self.assertEqual(field_location("Skylar Wallace grounded out to 2b (0-0)."), "Second Base")
        self.assertEqual(field_location("B Nickles-Camarena flied out to rf (1-1 BK)."), "Right Field")

    def test_spray_totals_reconcile_to_official_contact_events(self):
        plate_appearances = json.loads(
            (ROOT.parent / "ausl-war" / "output" / "tto" / "plate_appearances.json").read_text()
        )

        def official_located_contact(season=None):
            return sum(
                row["event_type"] in CONTACT_EVENT_TYPES
                and bool(field_location(row.get("play_text", "")))
                and (season is None or row["season"] == season)
                for row in plate_appearances
            )

        def site_spray_total(period):
            return sum(
                player["spray"]["total"]
                for player in self.site["periods"][period]["players"]
                if player.get("spray")
            )

        self.assertEqual(site_spray_total("2026"), official_located_contact(2026))
        self.assertEqual(site_spray_total("2025"), official_located_contact(2025))
        self.assertEqual(site_spray_total("combined"), official_located_contact())
        self.assertGreater(site_spray_total("2026"), 2000)

    def test_tto_payload_reconciles_to_current_source_snapshot_and_periods(self):
        plate_appearances = json.loads(PA_SOURCE.read_text(encoding="utf-8"))
        summary = json.loads(
            (ROOT.parent / "ausl-war" / "output" / "tto" / "summary.json").read_text(
                encoding="utf-8"
            )
        )
        tto = self.site["tto"]

        self.assertEqual(tto["meta"]["snapshot"], self.site["meta"]["snapshot"])
        self.assertEqual(tto["meta"]["snapshot"], summary["snapshot_id"])
        self.assertEqual(tto["meta"]["plate_appearances"], len(plate_appearances))
        self.assertEqual(tto["meta"]["plate_appearances"], summary["plate_appearances"])
        self.assertEqual(tto["meta"]["games"], len({row["canonical_id"] for row in plate_appearances}))
        self.assertEqual(tto["meta"]["games"], summary["games"])
        self.assertTrue(tto["meta"]["validation_passed"])

        period_seasons = {"combined": {2025, 2026}, "2025": {2025}, "2026": {2026}}
        for period, seasons in period_seasons.items():
            source_rows = [row for row in plate_appearances if row["season"] in seasons]
            self.assertEqual(tto["league"][period]["PA"], len(source_rows))
            self.assertEqual(
                tto["league"][period]["games"], len({row["canonical_id"] for row in source_rows})
            )
            self.assertEqual(
                sum(row["PA"] for row in tto["league"][period]["same_game"]), len(source_rows)
            )
            self.assertEqual(
                sum(row["PA"] for row in tto["league"][period]["prior_series"]), len(source_rows)
            )
            self.assertEqual(
                sum(
                    team["periods"][period]["PA"]
                    for team in tto["teams"]
                    if team["periods"].get(period)
                ),
                len(source_rows),
            )
            self.assertEqual(
                sum(
                    player["periods"][period]["PA"]
                    for player in tto["players"]
                    if player["periods"].get(period)
                ),
                len(source_rows),
            )

    def test_period_metadata_and_team_records_reconcile_to_official_events(self):
        normalized_events = json.loads(NORMALIZED_EVENTS_SOURCE.read_text(encoding="utf-8"))
        supplemental_events = json.loads(OFFICIAL_EVENTS_SOURCE.read_text(encoding="utf-8"))
        plate_appearances = json.loads(PA_SOURCE.read_text(encoding="utf-8"))

        period_seasons = {"2026": {2026}, "2025": {2025}, "combined": {2025, 2026}}
        for period, seasons in period_seasons.items():
            period_events = [
                row
                for row in [*normalized_events, *supplemental_events]
                if row.get("season") in seasons
            ]
            period_pas = [row for row in plate_appearances if row.get("season") in seasons]
            game_scores = defaultdict(lambda: defaultdict(int))
            game_teams = defaultdict(set)

            for event in period_events:
                game_id = event["canonical_id"]
                batting = team_key(event.get("batting_team"))
                fielding = team_key(event.get("fielding_team"))
                game_teams[game_id].update((batting, fielding))
                game_scores[game_id][batting] += int(number(event.get("runs_scored")))

            self.assertEqual(self.site["periods"][period]["meta"]["games"], len(game_teams))
            self.assertEqual(
                self.site["periods"][period]["meta"]["plateAppearances"], len(period_pas)
            )

            expected_by_team = {}
            for key in TEAM_META:
                games = [game_id for game_id, teams in game_teams.items() if key in teams]
                wins = losses = ties = runs_for = runs_allowed = 0
                for game_id in games:
                    opponent = next(iter(game_teams[game_id] - {key}), None)
                    scored = game_scores[game_id].get(key, 0)
                    allowed = game_scores[game_id].get(opponent, 0)
                    runs_for += scored
                    runs_allowed += allowed
                    wins += int(scored > allowed)
                    losses += int(scored < allowed)
                    ties += int(scored == allowed)
                expected_by_team[key] = {
                    "games": len(games),
                    "record": {"wins": wins, "losses": losses, "ties": ties},
                    "runs": runs_for,
                    "runsAllowed": runs_allowed,
                }

            for team in self.site["periods"][period]["teams"]:
                expected = expected_by_team[team["key"]]
                self.assertEqual(team["games"], expected["games"], (period, team["key"]))
                self.assertEqual(team["record"], expected["record"], (period, team["key"]))
                self.assertEqual(team["summary"]["runs"], expected["runs"], (period, team["key"]))
                self.assertEqual(
                    team["summary"]["runsAllowed"], expected["runsAllowed"], (period, team["key"])
                )

    def test_leaderboards_preserve_all_source_war_rows_and_stats(self):
        source_fields = {
            "total_war",
            "position_war",
            "pitcher_war",
            "offensive_war",
            "defensive_war",
            "baserunning_runs",
            "range_runs",
            "arm_runs",
            "pitching_war",
            "pitcher_defense_war",
            "RA7",
            "ERA",
            "FIP",
            "ERA_minus_FIP",
            "teams",
        }
        for season in (2025, 2026):
            source_rows = json.loads(
                (ROOT.parent / "ausl-war" / "output" / f"combined_{season}.json").read_text(
                    encoding="utf-8"
                )
            )
            site_rows = self.site["leaderboards"][str(season)]
            source_by_key = {row["player_key"]: row for row in source_rows}
            site_by_key = {row["player_key"]: row for row in site_rows}

            self.assertEqual(set(site_by_key), set(source_by_key))
            for key, source in source_by_key.items():
                row = site_by_key[key]
                self.assertFalse(set(source) - set(row), key)
                for field in source_fields:
                    if field in source:
                        self.assertEqual(row[field], source[field], (season, key, field))

    def test_matchup_data_reaches_player_pages(self):
        players = self.site["periods"]["2026"]["players"]
        self.assertTrue(any(player["matchups"] for player in players))
        self.assertIn('data-panel="matchups"', self.javascript)
        self.assertIn('data-panel="history"', self.javascript)
        self.assertIn("data-matchup-search", self.javascript)

    def test_darko_style_surfaces_are_table_first(self):
        self.assertIn("leaderboard-group", self.html)
        self.assertIn("League Stats", self.html)
        self.assertIn("home-standings-table", self.javascript)
        self.assertIn("Team Batting", self.javascript)
        self.assertIn("Team Pitching", self.javascript)
        self.assertIn("League Batting", self.javascript)
        self.assertIn("League Pitching", self.javascript)
        self.assertIn("Times Through the Order", self.javascript)
        for label in ("Off WAR", "Def WAR", "wOBA", "wRAA", "BsR", "Range Runs", "Arm Runs", "RAA", "RA7", "ERA", "FIP", "ERA − FIP"):
            self.assertIn(label, self.javascript)
        for removed_label in ("Hit Runs", "Lg Adj Runs", "Repl Runs", "Pos Adj Runs", "Raw BsR Runs", "Throwing Runs", "Arm Opp", "Total Def WAR", "Flags"):
            self.assertNotIn(removed_label, self.javascript)

    def test_responsive_shell_and_mobile_navigation_exist(self):
        self.assertIn("@media (max-width: 760px)", self.css)
        self.assertIn(".nav-toggle", self.css)
        self.assertIn(".table-scroll", self.css)

    def test_pdf_generation_uses_current_site_payload(self):
        pdf_builder = (ROOT / "build_pdfs.py").read_text()
        data_builder = (ROOT / "build.py").read_text()
        self.assertIn("site-data.json", pdf_builder)
        self.assertIn("generate_team(team, data)", pdf_builder)
        self.assertNotIn("legacy_scout_root", data_builder)

    def test_all_current_pdf_links_resolve(self):
        for team in self.site["periods"]["2026"]["teams"]:
            self.assertTrue((ROOT / team["pdf"]).is_file(), team["pdf"])

    def test_local_headshot_links_resolve(self):
        paths = {player["headshot"] for player in self.site["directory"] if player.get("headshot")}
        paths.update(row["headshot"] for rows in self.site["leaderboards"].values() for row in rows if row.get("headshot"))
        self.assertGreater(len(paths), 100)
        for path in paths:
            self.assertFalse(path.startswith("../"), path)
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()

import json
import math
import unittest
from pathlib import Path


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

    def test_player_scouting_features_are_preserved(self):
        for label in (
            "Spray Chart", "Swing Decisions", "Game Logs", "Times Through Order",
            "League Percentiles", "Baserunning", "Fielding", "ERA - FIP",
            "Batter–Pitcher Matchups", "Season History",
        ):
            self.assertIn(label, self.javascript)

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

    def test_responsive_shell_and_mobile_navigation_exist(self):
        self.assertIn("@media (max-width: 760px)", self.css)
        self.assertIn(".nav-toggle", self.css)
        self.assertIn(".table-scroll", self.css)

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

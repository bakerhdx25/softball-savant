import json
import unittest
from pathlib import Path

import build


class ScoutingSiteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build.build()
        cls.players = {player["key"]: player for player in cls.payload["players"]}

    def test_expected_2026_scope(self):
        self.assertEqual(self.payload["meta"]["season"], 2026)
        self.assertEqual(self.payload["meta"]["games"], 48)
        self.assertEqual(self.payload["meta"]["plateAppearances"], 2868)
        self.assertEqual(len(self.payload["teams"]), 6)
        self.assertEqual(len(self.payload["players"]), 121)

    def test_period_datasets_preserve_current_rosters_and_combine_player_data(self):
        root = Path(__file__).parent
        datasets = {period: json.loads((root / path).read_text(encoding="utf-8")) for period, path in {
            "2026":"data/scouting-data.json", "2025":"data/scouting-data-2025.json", "2025-2026":"data/scouting-data-2025-2026.json"
        }.items()}
        base_teams = {team["key"]: team for team in datasets["2026"]["teams"]}
        for period, data in datasets.items():
            self.assertEqual(data["meta"]["period"], period)
            for team in data["teams"]:
                base = base_teams[team["key"]]
                self.assertEqual(set(team["roster"]), set(base["roster"]))
                self.assertEqual(team["record"], base["record"])
                self.assertEqual(team["summary"], base["summary"])
        players = {period:{player["key"]:player for player in data["players"]} for period,data in datasets.items()}
        self.assertEqual(players["2025-2026"]["morganzerkle"]["hitting"]["PA"], players["2025"]["morganzerkle"]["hitting"]["PA"] + players["2026"]["morganzerkle"]["hitting"]["PA"])
        self.assertIsNone(next(team for team in datasets["2025"]["teams"] if team["key"] == "bandits")["pdf"])

    def test_team_records_rankings_and_rosters_reconcile(self):
        teams = self.payload["teams"]
        self.assertEqual(sum(team["games"] for team in teams), 96)
        self.assertEqual(sum(team["record"]["wins"] for team in teams), 48)
        self.assertEqual(sum(team["record"]["losses"] for team in teams), 48)
        for key in ("record", "runsPerGame", "ERA", "OPS"):
            self.assertEqual(sorted(team["rankings"][key] for team in teams), list(range(1, 7)))
        roster_keys = [key for team in teams for key in team["roster"]]
        self.assertEqual(len(roster_keys), len(set(roster_keys)))
        self.assertEqual(set(roster_keys), set(self.players))

    def test_original_scout_em_out_fields_are_present(self):
        hitter_fields = {"PA", "AB", "H", "K", "BB", "HBP", "HR", "XBH", "SBA", "Bunts", "BA", "OBP", "SLG", "OPS", "K_pct", "BB_pct", "GB_pct"}
        pitcher_fields = {"App", "IP", "ERA", "WHIP", "SO7", "BB7", "S_pct"}
        for player in self.players.values():
            if player["hitting"]:
                self.assertTrue(hitter_fields <= set(player["hitting"]))
            if player["pitching"]:
                self.assertTrue(pitcher_fields <= set(player["pitching"]))

    def test_spray_and_swing_contracts_match_report(self):
        self.assertEqual(set(self.payload["field"]["zones"]), set(build.ZONE_MAP))
        self.assertEqual(self.payload["field"]["image"], "assets/field-clean-v2.svg")
        self.assertEqual((self.payload["field"]["width"], self.payload["field"]["height"]), (800, 620))
        self.assertTrue((Path(__file__).parent / self.payload["field"]["image"]).is_file())
        self.assertTrue(all(len(points) >= 12 for points in self.payload["field"]["zones"].values()))
        home = build.FIELD_HOME
        for outer, inner in ((build.ZONE_MAP["Left Field"][0], build.ZONE_MAP["Third Base"][1]), (build.ZONE_MAP["Right Field"][18], build.ZONE_MAP["First Base"][-1])):
            cross = (outer[0]-home[0])*(inner[1]-home[1]) - (outer[1]-home[1])*(inner[0]-home[0])
            self.assertLess(abs(cross), 300)
        self.assertEqual(len(self.payload["leagueApproach"]), 12)
        for player in self.players.values():
            self.assertEqual(len(player["approach"]), 12)
            self.assertEqual(player["spray"]["total"], sum(player["spray"]["counts"].values()))
            self.assertEqual([row["encounter"] for row in player["seriesExposure"]], ["0", "1", "2+"])
        self.assertEqual(build.field_location("A grounds out, shortstop B to first baseman C."), "Shortstop")

    def test_percentiles_obey_qualifiers(self):
        for player in self.players.values():
            hitting = player["percentiles"]["hitting"]
            pitching = player["percentiles"]["pitching"]
            if hitting:
                self.assertGreaterEqual(player["hitting"]["PA"], player["qualifiers"]["hittingPA"])
                self.assertTrue(all(1 <= context["percentile"] <= 99 for context in hitting.values()))
                self.assertTrue(all(1 <= context["rank"] <= context["of"] for context in hitting.values()))
            if pitching:
                self.assertGreaterEqual(player["pitching"]["IP"], player["qualifiers"]["pitchingIP"])
                self.assertTrue(all(1 <= context["percentile"] <= 99 for context in pitching.values()))

    def test_game_logs_are_one_row_per_game(self):
        for player in self.players.values():
            game_ids = [row["gameId"] for row in player["hittingGameLogs"]]
            self.assertEqual(len(game_ids), len(set(game_ids)))
            for row in player["hittingGameLogs"]:
                self.assertEqual(row["PA"], len(row["plateAppearances"]))
                self.assertRegex(row["result"], r"^[WLT] \d+-\d+$")

    def test_karlyn_pickens_games_use_schedule_dates_and_complete_rows(self):
        rows = self.players["karlynpickens"]["pitchingGameLogs"]
        july = [row for row in rows if row["gameId"] in {"ausl-2026-df00aee444a8828c", "official-ausl-2026-959"}]
        self.assertEqual({row["date"] for row in july}, {"2026-07-03", "2026-07-04"})
        self.assertTrue(all(row["IP"] is not None and row["R"] is not None and row["ER"] is not None for row in july))
        july_four = next(row for row in july if row["date"] == "2026-07-04")
        self.assertEqual((july_four["IP"], july_four["H"], july_four["R"], july_four["ER"], july_four["BB"], july_four["SO"]), (3.1, 3, 3, 3, 2, 4))

    def test_baserunning_routes_are_raw_counts(self):
        for player in self.players.values():
            self.assertIn("firstToThird", player["baserunning"])
            self.assertIn("secondToHome", player["baserunning"])
            self.assertIn("firstToHome", player["baserunning"])
            self.assertNotIn("extraBaseRate", player["baserunning"])

    def test_public_ui_has_no_legacy_branding_or_position_columns(self):
        root = Path(__file__).parent
        public = "\n".join((root / name).read_text(encoding="utf-8") for name in ("index.html", "app.js", "build_pdfs.py"))
        self.assertNotIn("Scout Em Out", public)
        self.assertNotIn("Original Report", public)
        self.assertNotIn("↕", public)
        self.assertNotIn('id="pdf-button"', public)
        self.assertIn("Download Scouting Report", public)
        self.assertIn("PDF report data", public)
        self.assertIn("Player stats period", public)
        self.assertIn("data-overview-period", public)
        self.assertIn("const priorTab = state.tab", public)
        self.assertIn("priorRoleAvailable", public)
        self.assertIn("tabsForRole(state.playerRole).some", public)
        self.assertIn("season-divider", public)
        self.assertIn("Range Runs", public)
        self.assertIn("League Percentiles", public)
        self.assertIn("Pitcher Defense WAR", public)
        self.assertNotIn("swing-toggle", public)
        self.assertIn("decision-pair", public)
        self.assertIn("draw_swing_grid", public)
        self.assertNotIn("AUSL Team Scout | 2026 captured data", public)
        for key in ("tiannabell", "cassidycurd", "rubymeylan"):
            self.assertIsNone(self.players[key]["headshot"])
        self.assertIn('value="2025"', public)
        self.assertIn('value="2025-2026"', public)
        self.assertNotIn("Not qualified for league ranks", public)

    def test_static_and_pdf_artifacts_exist(self):
        root = Path(__file__).parent
        for name in ("index.html", "styles.css", "app.js", "data/scouting-data.json"):
            self.assertGreater((root / name).stat().st_size, 100)
        json.loads((root / "data/scouting-data.json").read_text(encoding="utf-8"))
        for player in self.players.values():
            if player.get("headshot"):
                self.assertTrue((root / player["headshot"]).is_file())
        for team in self.payload["teams"]:
            pdf = root / team["pdf"]
            self.assertTrue(pdf.is_file())
            self.assertGreater(pdf.stat().st_size, 50_000)
        combined = json.loads((root / "data/scouting-data-2025-2026.json").read_text(encoding="utf-8"))
        for team in combined["teams"]:
            pdf = root / team["pdf"]
            self.assertTrue(pdf.is_file())
            self.assertGreater(pdf.stat().st_size, 50_000)


if __name__ == "__main__":
    unittest.main()

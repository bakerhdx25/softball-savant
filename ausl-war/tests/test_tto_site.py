import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-tto-site.py"
SPEC = importlib.util.spec_from_file_location("tto_site", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class TTOSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads(MODULE.SOURCE.read_text(encoding="utf-8"))
        cls.payload = MODULE.build_payload(rows)

    def test_requested_light_interface_and_copy(self):
        html = MODULE.HTML
        self.assertIn("color-scheme: light", html)
        self.assertIn("In-Game Matchups", html)
        self.assertIn("League wOBA", html)
        self.assertNotIn("League OPS", html)
        self.assertNotIn("See how hitters performed", html)
        self.assertNotIn("Method and interpretation", html)
        self.assertNotIn('id="summary"', html)

    def test_series_table_uses_zero_one_and_two_plus(self):
        self.assertEqual(MODULE.SERIES_LABELS, ("0", "1", "2+"))
        self.assertEqual(
            [row["encounter"] for row in self.payload["league"]["combined"]["prior_series"]],
            ["0", "1", "2+"],
        )

    def test_team_aggregates_cover_every_plate_appearance(self):
        teams = self.payload["teams"]
        self.assertEqual([team["name"] for team in teams], ["Bandits", "Blaze", "Cascade", "Spark", "Talons", "Volts"])
        self.assertEqual(
            sum(team["periods"]["combined"]["PA"] for team in teams),
            self.payload["meta"]["plate_appearances"],
        )

    def test_separate_league_team_and_pitcher_tabs_are_present(self):
        html = MODULE.HTML
        for token in ('data-view="league"', 'data-view="teams"', 'data-view="pitchers"', "team-buttons", "pitcher-team", "player-list"):
            self.assertIn(token, html)
        self.assertIn('[hidden] { display: none !important; }', html)
        self.assertNotIn('id="pitcher-select"', html)

    def test_war_headshots_are_attached_to_pitchers(self):
        pitchers = self.payload["players"]
        self.assertGreaterEqual(sum(bool(player["headshot"]) for player in pitchers), 40)
        self.assertIn("entity-mark", MODULE.HTML)

    def test_official_league_and_team_logos_are_attached(self):
        self.assertIn("theausl.com", self.payload["meta"]["league_logo"])
        self.assertTrue(all(team["logo"].endswith("-icon.svg") for team in self.payload["teams"]))


if __name__ == "__main__":
    unittest.main()

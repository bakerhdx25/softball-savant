import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-mobile-leaderboard.py"
SPEC = importlib.util.spec_from_file_location("mobile_leaderboard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class MobileLeaderboardTests(unittest.TestCase):
    def test_uses_light_table_with_two_role_views_and_requested_columns(self):
        html = MODULE.HTML
        self.assertIn('<table>', html)
        self.assertIn('color-scheme: light', html)
        self.assertNotIn('class="cards"', html)
        for view in ('position', 'pitching'):
            self.assertIn(f'data-view="{view}"', html)
        self.assertNotIn('data-view="total"', html)
        for label in ('PA', 'IP', 'WAR', 'Off WAR', 'Def WAR', 'wOBA', 'wRAA', 'BsR', 'Range Runs', 'Arm Runs', 'RAA', 'RA7', 'ERA', 'FIP', 'ERA − FIP'):
            self.assertIn(f"'{label}'", html)
        self.assertIn("['Best WAR'", html)
        self.assertNotIn('Best Position WAR', html)
        self.assertNotIn('Best Pitcher Defense', html)
        self.assertNotIn('GameChanger', html)
        self.assertNotIn('Research snapshot', html)
        self.assertNotIn('SIERA', html)

    def test_mobile_table_scroll_is_contained(self):
        compact = "".join(MODULE.HTML.split())
        self.assertIn('body{margin:0;min-width:280px;overflow-x:hidden', compact)
        self.assertIn('.table-scroll{width:100%;max-width:100%;overflow:auto', compact)
        self.assertIn('--player-width:154px', compact)
        self.assertIn('min-height:44px', compact)

    def test_interactions_and_csv_export_are_present(self):
        html = MODULE.HTML
        for token in ('data-sort', 'aria-sort', 'Download CSV', 'Search players or teams', 'Rows per page', 'Select season', 'Min PA', 'Minimum innings pitched', 'Reset'):
            self.assertIn(token, html)
        self.assertIn('leader-headshot', html)
        self.assertIn('team-logo', html)
        self.assertIn('teamMarkup(player.teams)', html)
        self.assertNotIn("column.key === 'ERA_minus_FIP' ? tone(-number(value))", html)
        for removed in ('detail-panel', 'detail-row', 'aria-expanded', 'Toggle details'):
            self.assertNotIn(removed, html)


if __name__ == "__main__":
    unittest.main()

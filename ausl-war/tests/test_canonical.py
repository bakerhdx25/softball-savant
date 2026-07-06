import unittest

from ausl_war.canonical import (
    canonical_contest_key,
    normalize_team_name,
    split_same_time_contests,
)


class CanonicalContestTests(unittest.TestCase):
    def test_team_name_normalization_removes_ausl_prefix(self):
        self.assertEqual(normalize_team_name("AUSL Blaze"), "blaze")
        self.assertEqual(normalize_team_name("Blaze"), "blaze")

    def test_contest_key_is_independent_of_team_order(self):
        first = canonical_contest_key(2026, ["team-a", "team-b"], "2026-06-01T00:00:00Z")
        second = canonical_contest_key(2026, ["team-b", "team-a"], "2026-06-01T00:00:00Z")
        self.assertEqual(first, second)

    def test_doubleheaders_have_distinct_keys(self):
        first = canonical_contest_key(2026, ["a", "b"], "2026-06-01T18:00:00Z")
        second = canonical_contest_key(2026, ["a", "b"], "2026-06-01T21:00:00Z")
        self.assertNotEqual(first, second)

    def test_same_time_doubleheader_is_paired_by_inverse_score(self):
        rows = [
            {"id": "h1", "home_away": "home", "score": {"team": 5, "opponent_team": 2}},
            {"id": "h2", "home_away": "home", "score": {"team": 3, "opponent_team": 4}},
            {"id": "a1", "home_away": "away", "score": {"team": 2, "opponent_team": 5}},
            {"id": "a2", "home_away": "away", "score": {"team": 4, "opponent_team": 3}},
        ]
        contests = split_same_time_contests(rows)
        self.assertEqual(
            [{row["id"] for row in contest} for contest in contests],
            [{"h1", "a1"}, {"h2", "a2"}],
        )


if __name__ == "__main__":
    unittest.main()

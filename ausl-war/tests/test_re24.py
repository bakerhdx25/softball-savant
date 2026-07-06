import unittest

from ausl_war.re24 import (
    BaseOutState,
    add_run_values,
    annotate_runs_remaining,
    encode_bases,
    estimate_re24,
    event_linear_weights,
    bootstrap_re24,
)


class Re24Tests(unittest.TestCase):
    def test_base_encoding(self):
        self.assertEqual(encode_bases(True, False, True), 5)
        state = BaseOutState(1, 5)
        self.assertTrue(state.on_first)
        self.assertFalse(state.on_second)
        self.assertTrue(state.on_third)

    def test_runs_remaining_are_half_inning_specific(self):
        events = [
            {"canonical_id": "g", "inning": 1, "half": "top", "event_order": 1, "runs_scored": 0},
            {"canonical_id": "g", "inning": 1, "half": "top", "event_order": 2, "runs_scored": 2},
            {"canonical_id": "g", "inning": 1, "half": "top", "event_order": 3, "runs_scored": 0},
        ]
        result = annotate_runs_remaining(events)
        self.assertEqual([row["runs_remaining_before"] for row in result], [2, 2, 0])
        self.assertEqual([row["runs_remaining_after"] for row in result], [2, 0, 0])

    def test_smoothing_emits_all_24_states(self):
        rows = estimate_re24(
            [
                {"outs_before": 0, "bases_before": 0, "runs_remaining_before": 1},
                {"outs_before": 0, "bases_before": 0, "runs_remaining_before": 3},
                {"outs_before": 1, "bases_before": 0, "runs_remaining_before": 0},
                {"outs_before": 2, "bases_before": 0, "runs_remaining_before": 0},
            ],
            prior_pseudocount=2,
        )
        self.assertEqual(len(rows), 24)
        empty_zero_out = next(row for row in rows if row["outs"] == 0 and row["bases"] == 0)
        self.assertEqual(empty_zero_out["raw_re"], 2)

    def test_run_value_uses_terminal_zero(self):
        observations = []
        for outs in range(3):
            for bases in range(8):
                observations.append(
                    {"outs_before": outs, "bases_before": bases, "runs_remaining_before": 1}
                )
        re_rows = estimate_re24(observations, prior_pseudocount=0)
        valued = add_run_values(
            [
                {
                    "outs_before": 2,
                    "bases_before": 0,
                    "outs_after": 3,
                    "bases_after": 0,
                    "runs_scored": 0,
                    "event_type": "out",
                }
            ],
            re_rows,
        )
        self.assertEqual(valued[0]["re_after"], 0)
        self.assertEqual(valued[0]["run_value"], -1)
        self.assertEqual(event_linear_weights(valued)[0]["linear_weight"], -1)

    def test_game_bootstrap_returns_intervals_for_all_states(self):
        events = []
        for game in ("g1", "g2"):
            for outs in range(3):
                events.append(
                    {
                        "canonical_id": game,
                        "outs_before": outs,
                        "bases_before": 0,
                        "runs_remaining_before": 2 - outs,
                    }
                )
        intervals = bootstrap_re24(events, prior_pseudocount=2, replicates=10, seed=1)
        self.assertEqual(len(intervals), 24)
        self.assertLessEqual(intervals[BaseOutState(0, 0)][0], intervals[BaseOutState(0, 0)][1])


if __name__ == "__main__":
    unittest.main()

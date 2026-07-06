# AUSL Times Through the Order and Repeated Exposure

Snapshot: `20260704T165430Z`

## Executive result

Across 6,019 plate appearances in 98 games, hitters produced a 0.786 OPS and 0.354 wOBA the first time they faced the same pitcher in a game. In all later meetings combined, those figures were 0.891 and 0.385. The observed penalties were 0.104 OPS and 0.031 wOBA.

The third same-game meeting contained 507 PA and produced a 0.924 OPS, 0.397 wOBA, and 0.037 context-neutral event runs per PA.

These are league-level descriptive differences. Pitcher survival, score state, substitutions, and the quality of hitters who receive later opportunities create selection effects. The adjusted models below reduce some confounding but do not make the estimates causal.

The adjusted total association remains positive for the third-or-later meeting: 0.067 context-neutral event runs per PA (95% CI 0.015 to 0.120). When pitcher workload is modeled directly, each additional nine batters faced is associated with 0.065 more context-neutral event runs per PA (95% CI 0.027 to 0.104). The exact encounter indicators are no longer positive in that decomposition. The evidence therefore supports deterioration as pitchers progress through a game, but does not isolate a separate familiarity jump at the instant a hitter sees the same pitcher again.

## Same pitcher, same game

| Encounter | PA | AVG | OBP | SLG | OPS | K% | BB% | HR% | wOBA | RV/PA |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3716 | 0.269 | 0.361 | 0.426 | 0.786 | 16.2% | 9.9% | 2.8% | 0.354 | -0.014 |
| 2 | 1711 | 0.301 | 0.368 | 0.508 | 0.875 | 12.9% | 7.2% | 4.0% | 0.380 | 0.010 |
| 3 | 507 | 0.325 | 0.380 | 0.544 | 0.924 | 12.2% | 6.5% | 4.7% | 0.397 | 0.037 |
| 4+ | 85 | 0.338 | 0.400 | 0.608 | 1.008 | 10.6% | 9.4% | 5.9% | 0.415 | 0.070 |

## Season check

| Season / encounter | PA | OPS | wOBA | RV/PA |
|---|---:|---:|---:|---:|
| 2025-1 | 2027 | 0.787 | 0.355 | -0.015 |
| 2025-2 | 870 | 0.889 | 0.388 | 0.016 |
| 2025-3+ | 254 | 1.078 | 0.458 | 0.076 |
| 2026-1 | 1689 | 0.786 | 0.352 | -0.012 |
| 2026-2 | 841 | 0.861 | 0.371 | 0.004 |
| 2026-3+ | 338 | 0.827 | 0.355 | 0.016 |

The direction is present in both seasons from the first to the second encounter, but the third-or-later increase is much larger in 2025. The pooled estimate should therefore be treated as a two-season league average, not a fixed law that is equally large every year.


## Exposure carried across an official series

`Prior series-game encounters` counts only meetings with the same pitcher in earlier games of the current official series. It does not include earlier meetings in the same game.

| Prior series-game encounters | PA | OPS | wOBA | RV/PA |
|---:|---:|---:|---:|---:|
| 0 | 4942 | 0.827 | 0.365 | -0.002 |
| 1-2 | 890 | 0.864 | 0.382 | 0.010 |
| 3+ | 187 | 0.656 | 0.306 | -0.056 |

The series pattern is not monotonic: the 1–2 prior-meeting group is higher than zero exposure, but the 3+ group is lower and contains a much smaller sample. This snapshot does not establish a stable cumulative series penalty.

## Offense by game stage

| Innings | PA | OPS | wOBA | RV/PA |
|---:|---:|---:|---:|---:|
| 1-2 | 1866 | 0.841 | 0.374 | 0.006 |
| 3-4 | 1841 | 0.852 | 0.377 | 0.006 |
| 5+ | 2312 | 0.797 | 0.350 | -0.014 |

League-wide offense is not highest in innings 5 and later. That does not contradict the pitcher-workload result: late innings also contain fresh relievers and selective pitcher removal, while pitchers who remain in the game show deterioration as their batters-faced count rises.


## Adjusted associations

The total-exposure models use batter and pitcher fixed effects, season, and prior-series exposure. The workload-decomposition models add pitcher batters faced and inning band. The latter asks whether an exact repeat meeting adds a discontinuous penalty beyond the pitcher's gradual progression through the game. Standard errors are clustered by game.

| Model | Outcome | Term | Estimate | 95% CI |
|---|---|---|---:|---:|
| total_exposure_association | run_value | same_game_encounter_2 | 0.028 | [-0.001, 0.056] |
| total_exposure_association | run_value | same_game_encounter_3plus | 0.067 | [0.015, 0.120] |
| total_exposure_association | run_value | prior_series_games_1_2 | 0.015 | [-0.022, 0.052] |
| total_exposure_association | run_value | prior_series_games_3plus | -0.040 | [-0.106, 0.025] |
| total_exposure_association | wOBA_value | same_game_encounter_2 | 0.031 | [0.001, 0.061] |
| total_exposure_association | wOBA_value | same_game_encounter_3plus | 0.061 | [0.006, 0.116] |
| total_exposure_association | wOBA_value | prior_series_games_1_2 | 0.021 | [-0.018, 0.059] |
| total_exposure_association | wOBA_value | prior_series_games_3plus | -0.044 | [-0.110, 0.021] |
| total_exposure_association | on_base | same_game_encounter_2 | 0.010 | [-0.018, 0.037] |
| total_exposure_association | on_base | same_game_encounter_3plus | 0.028 | [-0.022, 0.078] |
| total_exposure_association | on_base | prior_series_games_1_2 | 0.020 | [-0.017, 0.057] |
| total_exposure_association | on_base | prior_series_games_3plus | -0.037 | [-0.104, 0.029] |
| workload_decomposition | run_value | same_game_encounter_2 | -0.026 | [-0.075, 0.022] |
| workload_decomposition | run_value | same_game_encounter_3plus | -0.041 | [-0.137, 0.054] |
| workload_decomposition | run_value | prior_series_games_1_2 | 0.024 | [-0.013, 0.061] |
| workload_decomposition | run_value | prior_series_games_3plus | -0.023 | [-0.086, 0.040] |
| workload_decomposition | run_value | pitcher_bf_before_per_9 | 0.065 | [0.027, 0.104] |
| workload_decomposition | run_value | inning_5plus | -0.034 | [-0.065, -0.003] |
| workload_decomposition | wOBA_value | same_game_encounter_2 | -0.024 | [-0.076, 0.028] |
| workload_decomposition | wOBA_value | same_game_encounter_3plus | -0.043 | [-0.147, 0.060] |
| workload_decomposition | wOBA_value | prior_series_games_1_2 | 0.031 | [-0.008, 0.070] |
| workload_decomposition | wOBA_value | prior_series_games_3plus | -0.024 | [-0.088, 0.040] |
| workload_decomposition | wOBA_value | pitcher_bf_before_per_9 | 0.066 | [0.024, 0.107] |
| workload_decomposition | wOBA_value | inning_5plus | -0.041 | [-0.074, -0.008] |
| workload_decomposition | on_base | same_game_encounter_2 | -0.023 | [-0.067, 0.022] |
| workload_decomposition | on_base | same_game_encounter_3plus | -0.021 | [-0.112, 0.070] |
| workload_decomposition | on_base | prior_series_games_1_2 | 0.030 | [-0.007, 0.067] |
| workload_decomposition | on_base | prior_series_games_3plus | -0.018 | [-0.086, 0.049] |
| workload_decomposition | on_base | pitcher_bf_before_per_9 | 0.039 | [0.002, 0.077] |
| workload_decomposition | on_base | inning_5plus | -0.042 | [-0.074, -0.010] |

## Individual pitcher penalties

Positive values mean hitters performed better after their first same-game meeting. Small later samples are retained but flagged; they should not be treated as stable pitcher traits.

| Pitcher | PA | Later PA | First OPS | Later OPS | OPS penalty | First wOBA | Later wOBA | wOBA penalty | Flag |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Rachel Garcia | 410 | 218 | 0.734 | 0.870 | 0.137 | 0.353 | 0.386 | 0.033 |  |
| Megan Faraimo | 340 | 158 | 0.905 | 0.752 | -0.153 | 0.390 | 0.336 | -0.054 |  |
| Montana Fouts | 332 | 163 | 0.479 | 0.632 | 0.152 | 0.224 | 0.275 | 0.051 |  |
| Sam Landry | 322 | 159 | 0.753 | 0.893 | 0.140 | 0.334 | 0.394 | 0.060 |  |
| Lexi Kilfoyl | 315 | 136 | 0.705 | 0.685 | -0.020 | 0.314 | 0.295 | -0.020 |  |
| Payton Gottshall | 281 | 97 | 0.801 | 0.884 | 0.083 | 0.351 | 0.373 | 0.022 |  |
| Georgina Corrick | 274 | 147 | 0.528 | 0.678 | 0.150 | 0.254 | 0.321 | 0.067 |  |
| Aleshia Ocasio | 226 | 104 | 0.937 | 1.227 | 0.291 | 0.415 | 0.501 | 0.086 |  |
| Keilani Ricketts | 217 | 58 | 0.720 | 0.597 | -0.123 | 0.334 | 0.271 | -0.063 |  |
| Emma Lemley | 214 | 80 | 0.906 | 1.014 | 0.108 | 0.394 | 0.426 | 0.031 |  |
| Taylor McQuillin | 205 | 49 | 0.658 | 1.221 | 0.563 | 0.293 | 0.507 | 0.214 |  |
| Aliyah Binford | 184 | 41 | 0.605 | 0.764 | 0.159 | 0.279 | 0.337 | 0.058 |  |
| Odicci Alexander-Bennett | 179 | 44 | 0.845 | 1.073 | 0.229 | 0.376 | 0.440 | 0.064 |  |
| Alana Vawter | 178 | 62 | 0.859 | 1.066 | 0.207 | 0.382 | 0.466 | 0.084 |  |
| Maya Johnson | 165 | 75 | 0.676 | 1.166 | 0.490 | 0.321 | 0.472 | 0.150 |  |
| Raelin Chaffin | 165 | 54 | 0.634 | 1.078 | 0.444 | 0.304 | 0.445 | 0.140 |  |
| Karlyn Pickens | 157 | 76 | 0.616 | 0.710 | 0.094 | 0.286 | 0.315 | 0.029 |  |
| Emiley Kennedy | 140 | 44 | 0.851 | 1.086 | 0.235 | 0.385 | 0.462 | 0.077 |  |
| Amber Fiser | 136 | 73 | 0.671 | 0.744 | 0.073 | 0.294 | 0.327 | 0.033 |  |
| Sarah Willis | 121 | 34 | 0.585 | 1.022 | 0.437 | 0.302 | 0.447 | 0.145 |  |
| Devyn Netz | 115 | 14 | 0.793 | 0.714 | -0.078 | 0.345 | 0.290 | -0.055 | small_later_sample |
| Kenzie Brown | 107 | 61 | 0.555 | 0.805 | 0.251 | 0.281 | 0.364 | 0.083 |  |
| Mariah Lopez | 98 | 17 | 1.185 | 1.471 | 0.286 | 0.479 | 0.571 | 0.092 | small_later_sample |
| NiJaree Canady | 91 | 45 | 1.206 | 1.081 | -0.125 | 0.513 | 0.450 | -0.063 |  |
| Kelly Maxwell | 83 | 38 | 0.861 | 0.745 | -0.115 | 0.408 | 0.342 | -0.066 |  |
| Ally Carda | 75 | 31 | 0.834 | 1.049 | 0.215 | 0.381 | 0.449 | 0.068 |  |
| Mariah Mazón | 71 | 12 | 1.051 | 0.833 | -0.218 | 0.448 | 0.423 | -0.026 | small_later_sample |
| Sam Show | 66 | 12 | 0.983 | 1.417 | 0.433 | 0.449 | 0.609 | 0.160 | small_later_sample |
| Jessica Mullins | 63 | 13 | 0.860 | 1.815 | 0.955 | 0.378 | 0.707 | 0.328 | small_later_sample |
| Lyndsey Grein | 63 | 8 | 0.889 | 0.250 | -0.639 | 0.382 | 0.192 | -0.190 | small_later_sample |
| Jailyn Ford | 53 | 14 | 0.714 | 0.536 | -0.178 | 0.318 | 0.261 | -0.057 | small_later_sample |
| Kat Sandercock | 53 | 26 | 0.566 | 0.929 | 0.364 | 0.268 | 0.380 | 0.112 | small_later_sample |
| Ruby Meylan | 52 | 12 | 0.900 | 2.350 | 1.450 | 0.389 | 0.891 | 0.502 | small_later_sample |
| Hope Trautwein-Valdespino | 47 | 15 | 1.331 | 0.883 | -0.448 | 0.558 | 0.418 | -0.140 | small_later_sample |
| Dallas Escobedo Magee | 42 | 14 | 0.780 | 0.786 | 0.005 | 0.339 | 0.350 | 0.010 | small_later_sample |
| Jala Wright | 42 | 7 | 0.668 | 1.143 | 0.475 | 0.391 | 0.473 | 0.082 | small_later_sample |
| Cassidy Curd | 41 | 3 | 0.691 | 2.667 | 1.976 | 0.310 | 1.038 | 0.728 | small_later_sample |
| Carley Hoover | 40 | 14 | 0.985 | 0.714 | -0.271 | 0.445 | 0.330 | -0.115 | small_later_sample |
| Peja Goold | 39 | 4 | 1.135 | 0.833 | -0.302 | 0.500 | 0.423 | -0.077 | small_later_sample |
| Maddie Penta | 38 | 8 | 1.471 | 0.500 | -0.971 | 0.594 | 0.231 | -0.363 | small_later_sample |
| Bri Copeland | 36 | 8 | 1.443 | 2.550 | 1.107 | 0.583 | 0.847 | 0.264 | small_later_sample |
| Taylor Tinsley | 35 | 22 | 1.357 | 0.714 | -0.643 | 0.571 | 0.334 | -0.237 | small_later_sample |
| Lauren Derkowski | 31 | 6 | 1.031 | 1.833 | 0.802 | 0.445 | 0.718 | 0.273 | small_later_sample |
| Brooke McCubbin | 27 | 12 | 0.739 | 1.222 | 0.483 | 0.390 | 0.577 | 0.188 | small_later_sample |
| Alyssa Denham | 24 | 15 | 0.476 | 0.795 | 0.319 | 0.274 | 0.354 | 0.080 | small_later_sample |
| Sydney Berzon | 11 | 0 | 0.788 | — | — | 0.392 | — | — | small_later_sample |
| Elena Escobar | 8 | 0 | 0.661 | — | — | 0.327 | — | — | small_later_sample |
| Brooke Yanez | 7 | 0 | 1.048 | — | — | 0.570 | — | — | small_later_sample |

## Data quality and interpretation

- Pitcher stint reconstruction changed 435 PA assignments relative to the original carry-forward parser.
- All pitcher-game outs now reconcile exactly to the pitching box score. 35 event blocks remain tied between equally optimal assignments and are flagged in the PA data.
- 82/83 games matched the official AUSL schedule by teams, date, and score; 1 matched uniquely by teams and date despite a source score discrepancy.
- 15 additional completed games absent from the inherited GameChanger PA snapshot were added from official AUSL play-by-play. Every official PA has batter and pitcher IDs, and every game reconciles PA, H, BB, SO, and HR totals to its official box score.
- The MLB-comparable field is a nine-batters-faced band (`mlb_tto_bf9`). The exact batter-pitcher encounter is the primary softball measure because re-entry and nonstandard lineup use can break a simple lineup-turn definition.
- A scheduled series is defined from the official AUSL team pairing, venue, and date cluster; postseason series use the official postseason series identifier.
- Together, the GameChanger-derived games and official AUSL augmentation cover every game marked completed in the captured 2025 and 2026 official schedules. Postponed and suspended duplicate/resumption records are excluded.
- RV/PA is the context-neutral event value derived from the shared AUSL RE24 event weights, making it comparable across both source types. The original contextual RE24 value remains in `re24_run_value` where GameChanger base-out states are available.

## Reproducibility

```bash
PYTHONPATH=src python3 -m ausl_war.cli build-tto --snapshot 20260704T165430Z
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

MLB comparison references:

- https://www.mlb.com/glossary/miscellaneous/third-time-through-the-order-penalty
- https://baseballsavant.mlb.com/csv-docs

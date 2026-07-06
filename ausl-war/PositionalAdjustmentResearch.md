# AUSL Positional Adjustment Research

## Decision

**Insufficient data for an official AUSL positional adjustment.** The WAR model
continues to assign `positional_adjustment_runs = 0.0` to every player. The
candidate values in this study are diagnostics, not WAR inputs.

This is not a finding that all positions have equal value. It is a finding that
the available GameChanger data cannot yet estimate the differences reliably.

## Why WAR needs a positional adjustment

The current range model compares fielders with other players handling the same
position and batted-ball category. That places fielders on a within-position
scale. A positional adjustment would then put those position-relative results
onto a common league-wide scale. This is the role described by
[FanGraphs](https://library.fangraphs.com/misc/war/positional-adjustment/) and
[Baseball-Reference](https://www.baseball-reference.com/about/war_explained_position.shtml).
Baseball-Reference prorates its position values by actual innings and centers
the league total at zero. Importing those MLB run values directly would be
inappropriate for seven-inning professional softball.

The requested [Hardball Times re-examination](https://tht.fangraphs.com/re-examining-wars-defensive-spectrum/)
uses two main signals: how the same players field when moved between positions,
and offensive production by position as evidence of roster scarcity. Its own
discussion identifies selection bias, asymmetric position switches, and
opportunity differences as limitations. Those limitations are more severe in
this AUSL sample.

## Available data

The July 4 snapshot contains 83 games across 2025 and 2026, 166 team-games, and
complete labels for the eight standard non-pitcher positions in 164 team-games.
The box-score `Info` field also contains `P`, `DH`, and `F10`. `F10` is treated
as a lineup/FLEX-style marker rather than a known field coordinate and is not
assigned a positional value. AUSL rules allow a designated player when the
pitcher does not bat, while softball DP/FLEX rules permit defensive assignments
to change independently of batting-order membership. See the
[AUSL format explanation](https://theausl.com/blaze/news/professional-softball-rules-format/)
and [USA Softball rulebook](https://www.usasoftball.com/wp-content/uploads/sites/120/2026/01/1-12-2026-Rule-Book.pdf).

The central limitation is that GameChanger reports the positions a player
played but not the innings or outs at each position. Play text records many
substitutions, but pinch runners, re-entry, DP/FLEX behavior, and position
changes cannot consistently be converted into a complete defensive timeline.
Fielding mentions prove who handled a particular ball; they do not prove who
occupied every position for the rest of the inning.

### Conservative innings audit

An assignment was counted as confirmed only when:

- all eight standard positions appeared exactly once for the team-game;
- no player had multiple standard positions; and
- the entire game had no recorded lineup or courtesy-runner substitution.

Only 10 of 166 team-games (six games) passed. They cover 1,688 of 26,288
possible standard-position outs, or **6.42%**. Seventy-six of 83 games contain
at least one recorded substitution. This fails the predefined 80% innings gate.

## Candidate methods

### Offensive scarcity proxy

Plate appearances were assigned only when a player-game had one standard
position label. Outcome run values were centered within season. The negative of
position offense was scaled to 100 PA, approximately a 25-game AUSL season, and
then opportunity-centered.

| Position | PA | Candidate runs/25 games |
|---|---:|---:|
| C | 537 | +1.87 |
| 1B | 563 | +3.89 |
| 2B | 510 | +1.18 |
| 3B | 526 | -3.80 |
| SS | 557 | -1.66 |
| LF | 557 | -3.14 |
| CF | 533 | -1.09 |
| RF | 518 | +2.82 |

The ordering is not credible as a defensive spectrum: first base receives more
credit than catcher or shortstop, while shortstop is negative. This can reflect
small rosters, individual player quality, injuries, and tactical assignments;
it is not evidence that first base is harder than shortstop.

Leave-one-franchise-out rank correlations were at least 0.81, but that apparent
stability is driven by repeatedly using most of the same small player pool.
The direct rank correlation between the 2025 and 2026 position scales was
**-0.29**; each season also moved at least one position by roughly seven runs
relative to the pooled result. The season gate fails decisively.

### Lower-playing-time depth proxy

The lower half of players by position-specific PA was evaluated as a possible
replacement-depth signal. Samples ranged from 68 to 138 PA by position, and the
result differed sharply from the offensive-scarcity scale—for example, left
field was -11.12 runs while shortstop was +5.63. This is too sensitive to a few
bench players and is not used.

### Within-player fielding transitions

Fielding opportunities were adjusted for position and batted-ball type, then
compared for players observed at two positions. No pair reached the gate of 15
players and 200 opportunities on both sides. The largest pair, LF/RF, contained
11 players and only 127 opportunities on its smaller side. Catcher had only 60
total attributable fielding opportunities. Using these residuals as an
additional adjustment would also risk double-counting the existing range model.

## Reliability gates

| Gate | Result |
|---|---|
| Defensible position innings covering at least 80% | Fail: 6.42% |
| Adequate within-player transition samples | Fail: 0 qualifying pairs |
| Leave-one-team-out rank stability | Pass |
| Between-season rank stability | Fail |
| Opportunity-weighted league centering | Pass |
| No-double-counting design | Pass conceptually |

Because three required gates fail, none of the candidate scales is eligible for
WAR. Centering an unstable estimate at zero would make its arithmetic tidy, not
make it valid.

## What would make implementation possible

The minimum new input is a structured defensive log containing each starting
fielder's position plus the inning/half-inning of every defensive substitution,
re-entry, DP/FLEX change, and position switch. With that data, the study should
be rerun over several comparable AUSL seasons. The implementation gate should
remain closed until position innings are substantially complete, transition
samples grow, and leave-season-out estimates stabilize.

The 2026 standardized scale, if eventually supported, should be expressed per
25 games or 175 defensive innings. The current 25-game schedule is documented
in MLB's [2026 AUSL season FAQ](https://www.mlb.com/news/2026-ausl-regular-season-faq).
Player adjustments should be the innings-weighted sum across positions and the
league total must equal zero.

## Reproduction

```bash
PYTHONPATH=src python3 -m ausl_war.cli research-positions --snapshot 20260704T165430Z
```

Primary outputs are `positional_innings_by_player`,
`positional_samples_and_transitions`, `candidate_positional_scales`,
`positional_sensitivity_cross_validation`, `positional_innings_audit`, and
`positional_adjustment_recommendation` in CSV/JSON form under `output/`.

# AUSL WAR Methodology

## Status

Version 4 reports season-specific Position WAR and Pitcher WAR for every
completed 2025 and 2026 AUSL game. Total WAR remains an export-only sum.

## Contest identity

GameChanger creates a distinct schedule ID for each team's view of a contest.
The same game therefore cannot be deduplicated by UUID. The canonical key is a
hash of:

1. season;
2. the sorted pair of AUSL team IDs; and
3. scheduled start timestamp.

The two source rows must also agree on status and start time, have complementary
home/away designations, and report inverse team/opponent scores. Different start
times preserve doubleheaders as separate contests. Postponed and rescheduled
records remain separate until their source metadata proves they represent the
same contest.

## Value framework

The primary position-player structure is batting runs, baserunning runs,
defensive runs where defensible, positional adjustment where defensible, league
adjustment, and replacement runs, converted with AUSL runs per win.

Pitchers receive one opponent-adjusted, results-based RA7 Pitcher WAR. Park
factors are neutral. The 2025 leaderboard covers all 50 completed games; 12
games absent from the inherited detailed snapshot are reconstructed from
official AUSL box scores and play-by-play. The 2026 leaderboard similarly adds
three newly completed official games for 48 total.

The public [softball-war-model](https://github.com/samt0512/softball-war-model)
was reviewed as inspiration. Its three-state RE model and bottom-quintile
replacement definition are not imported; this pipeline uses full RE24 and the
documented conventional WAR replacement calibration.

## GameChanger collection method

Collection uses Scout Em Out's production HTML scraper, not the repository's
legacy internal API client. The research wrapper calls
`scrapeDataFromSchedulePage` from `../collector/scraper.js`, which opens
rendered schedule, box-score, and play-by-play pages and extracts their visible
DOM content. One home-owned source schedule is selected per canonical contest
before page navigation; the reciprocal schedule row is retained only as a
fallback. This prevents double counting and avoids requesting every game twice.

## RE24 estimation

The normalized event layer records the three-bit base state and outs immediately
before and after each event. Observed runs remaining are calculated within the
same half-inning. A placed extra-inning runner therefore changes the initial base
state but is not counted as a run unless she scores.

Raw state expectancy is the mean observed runs remaining for each of the 24
states. The version 1 smoothed estimator partially pools each state toward the
mean for the same number of outs:

`smoothed RE = (state run sum + alpha * outs-level RE) / (state N + alpha)`

The prior pseudocount is 20. Raw cell size, raw mean, prior mean, and smoothed
mean are published. Event run value is:

`runs on event + RE(after) - RE(before)`

This is the standard 24-state construction described in Jim Albert's
*Beyond Runs Expectancy* and is consistent with the transparent play-allocation
motivation of Baumer, Jensen, and Matthews' openWAR:

- https://doi.org/10.3233/JSA-140001
- https://arxiv.org/abs/1312.7158

## Batting

Context-neutral event weights are the mean RE24 run value of each event. wOBA
weights subtract the league out value and are scaled so 2026 league wOBA equals
2026 league OBP. The denominator excludes intentional walks, sacrifice bunts,
and catcher interference. Batting runs are:

`Batting Runs = ((player wOBA - league wOBA) / wOBA scale) * denominator`

League batting runs balance to zero. Reached-on-error and fielder's-choice
events remain outs in the wOBA numerator while retaining their plate-appearance
denominator effects.

## Baserunning

The parser preserves named runners before and after every event. Explicit batter
destinations override default hit destinations, scores and outs are applied
before advances, and omitted minimum forced movement is recorded but excluded
from runner skill. Every game reconciles to its box score; ambiguous collisions
are listed in the data audit rather than converted into runs.

The component includes SB/CS plus non-forced first-to-third, second-to-home,
first-to-home, tag-up, hold, advancement-out, and batter-stretch opportunities.
Expected advancement is partially pooled by starting base, outs, event type,
batted-ball type, and general fielding direction:

`advancement runs = actual RE24 outcome utility - expected outcome utility`

League advancement runs are centered at zero. Forced advances and wild
pitch/passed-ball movement are excluded. SB/CS remains separately visible.

## Double-play avoidance

Eligible opportunities are ground balls with a runner on first and fewer than
two outs. Actual double plays are compared with a partially pooled expected rate
by outs and general fielding direction. The probability difference is converted
to runs using the observed RE24 gap between double plays and other eligible
ground balls. League double-play runs are centered at zero and remain separate
from wOBA batting runs and runner advancement.

## Defense and position

The range model groups batted balls by ground/line/fly/pop/bunt
and the general responsible position in the play description. It compares actual
out conversion with the league rate for that group, converts the difference to
runs, and shrinks player values toward zero with 20 opportunities of prior
weight. It has no exact location, hang time, exit velocity, or starting position.

Arm value is the opposing side of attributable runner advancement
when exactly one responsible fielder is named. Ambiguous relay chains are
excluded. Raw arm and runner allocations balance exactly; arm opportunities are
then league-centered and player totals are shrunk with 40 opportunities of prior
weight. GameChanger does not describe throw quality or all relay responsibility,
which remains a limitation on interpretation.

Official catcher SB and CS allowed are valued relative to the season league
caught-stealing rate. The difference between the observed AUSL run values of a
successful steal and caught stealing converts excess caught stealings to runs;
20 attempts of prior weight shrink small samples, and post-shrinkage values are
league-centered. Catcher throwing runs enter Defense WAR once. Wild pitches are
pitcher events, not catcher defense. Passed balls are omitted because no complete
authoritative season field is available.

Named batted-ball errors are already failures to convert in the range model and
are not charged again as a separate error component.

No positional adjustment is applied. MLB positional values are not imported
because they have not been validated for professional softball, and GameChanger
does not provide reliable defensive innings by position. The reproducible
analysis in `PositionalAdjustmentResearch.md` confirms only 6.42% of possible
standard-position outs meet the conservative reconstruction gate; transition
samples and between-season stability also fail, so the official value remains
zero.

The position-player leaderboard uses an additive split. `Offensive WAR =
(wRAA + baserunning runs + double-play avoidance runs + league balancing runs
+ replacement runs) / runs per win`. `Defensive WAR = (range runs + arm runs
+ catcher throwing runs + positional adjustment runs) / runs per win`, and
`WAR = Offensive WAR + Defensive WAR`. The more granular `wRAA`, `BsR`, Range
Runs, and Arm Runs columns remain runs above average rather than separate WAR
figures. For display, catcher throwing runs are folded into Arm Runs; the two
sources remain separate in model exports.

The leaderboard has separate Position Players and Pitchers tables. Position
WAR excludes all pitching. Pitcher WAR excludes hitting and baserunning. For
pitchers, pitcher-position range and arm runs are subtracted from the RA7
pitching component and returned as Pitcher Defense WAR, so `Pitcher WAR =
Pitching WAR + Pitcher Defense WAR` without changing the original overall RA7
result. RA7 still contains teammate-defense context because a complete
team-defense adjustment is unavailable.

## Pitching

Pitching WAR begins with actual total runs allowed per seven innings. Opponent
offensive strength is estimated from team runs per plate appearance, shrunk
toward the league rate with 200 plate appearances of prior weight, then weighted
by the opponents each pitcher faced:

`Pitching RAA = (opponent expected RA7 - player RA7) * IP / 7`

Pitching RAA is league-centered, replacement runs are distributed by innings,
and Pitching WAR is `(RAA + replacement runs) / runs per win`. Reliever leverage
and bullpen chaining are not included.

## FIP

FIP is informational and never enters WAR. It uses the standard FanGraphs
inputs—home runs, walks, hit batters, and strikeouts—with the pitching component
scaled from nine to seven innings:

`FIP7 = (7 / 9) * ((13 * HR + 3 * (BB + HBP) - 2 * SO) / IP) + constant`

The constant is calculated separately for each AUSL season so the
innings-weighted league FIP equals the league ERA per seven innings. The
constants are 2.809924 for 2025 and 2.303274 for 2026. `ERA - FIP` is positive
when actual ERA is higher than FIP and negative when actual ERA is lower. The
formula follows https://library.fangraphs.com/pitching/fip/.

## Runs per win and replacement

The seven-inning adaptation of FanGraphs' published Tango runs-per-win shortcut
is:

`RPW = 1.5 * league RA7 + 3`

Version 2 uses the shared FanGraphs/Baseball-Reference overall replacement
calibration of 1,000 WAR per 2,430 games and FanGraphs' 57% position-player / 43%
pitcher allocation. Replacement runs are distributed by PA and IP. The .294
replacement convention is a benchmark rather than an empirical claim about AUSL
reserve talent.

## Conventional WAR calibration references

The position framework and replacement calibration follow published WAR
structures; pitching follows Baseball-Reference's results-based philosophy:

- Position players: https://library.fangraphs.com/war/war-position-players/
- Pitchers: https://www.baseball-reference.com/about/war_explained_pitch.shtml

The formulas are adapted transparently for seven-inning softball; MLB park and
positional constants are not imported.

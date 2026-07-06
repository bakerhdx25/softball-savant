# AUSL WAR Validation Report

Overall status: **PASS**

| Check | Result | Observed | Expected |
|---|---|---|---|
| canonical IDs are unique | PASS | `0` | `0` |
| canonical source pairs have no quality flags | PASS | `0` | `0` |
| all completed contests have immutable HTML artifacts | PASS | `83` | `83` |
| raw manifest contains three artifacts per game | PASS | `249` | `249` |
| raw manifest SHA-256 values match current files | PASS | `[]` | `[]` |
| normalization covers every completed contest | PASS | `83` | `83` |
| all games reconcile runs | PASS | `83` | `83` |
| all games reconcile hits | PASS | `83` | `83` |
| all games reconcile walks | PASS | `83` | `83` |
| all games reconcile strikeouts | PASS | `83` | `83` |
| all games satisfy runner-state invariants | PASS | `83` | `83` |
| no play rows remain unresolved | PASS | `0` | `0` |
| no plate appearances have unknown outcomes | PASS | `0` | `0` |
| every completed non-walkoff half-inning reaches three outs | PASS | `Counter({3: 1020})` | `{3: 1020}` |
| no normalized event begins with three outs | PASS | `0` | `0` |
| every RE24 state has observations | PASS | `24` | `24` |
| position RAA balances to zero | PASS | `-3.34297476853318e-15` | `0` |
| 2025 position RAA balances to zero | PASS | `-1.2212453270876722e-15` | `0` |
| expanded baserunning balances to zero | PASS | `-6.59211183903774e-15` | `0` |
| double-play avoidance balances to zero | PASS | `9.298117831235686e-16` | `0` |
| expanded advancement has no unresolved candidates | PASS | `0` | `0` |
| raw arm and attributed runner value are opposing | PASS | `0.0` | `0` |
| unshrunk arm opportunities are league centered | PASS | `2.0539125955565396e-15` | `0` |
| arm attribution coverage clears inclusion gate | PASS | `0.8246498599439775` | `>= 0.75` |
| RA7 pitching RAA balances to zero | PASS | `8.153200337090993e-16` | `0` |
| WAR pool matches conventional replacement calibration | PASS | `19.75308641975309` | `19.75308641975309` |
| combined player keys are unique | PASS | `121` | `121` |
| every pitcher has opponent-adjusted RA7 context | PASS | `41` | `41` |
| stored total WAR equals position plus pitcher WAR | PASS | `0` | `0` |
| position WAR equals offensive plus defensive WAR | PASS | `0` | `0` |
| pitcher WAR decomposes into pitching and pitcher defense WAR | PASS | `0` | `0` |
| pitching RAA plus pitcher defense reconstructs RA7 RAA | PASS | `0` | `0` |
| wRAA is the public alias for wOBA-derived batting runs | PASS | `0` | `0` |
| Batting WAR converts wRAA | PASS | `0` | `0` |
| Baserunning WAR converts the complete baserunning component | PASS | `0` | `0` |
| Defense WAR converts range arm catcher and positional runs exactly once | PASS | `0` | `0` |
| catcher throwing runs are league centered | PASS | `-6.938893903907228e-18` | `0` |
| 2025 catcher throwing runs are league centered | PASS | `-1.6653345369377348e-16` | `0` |
| display Arm Runs fold catcher throwing into other arm value | PASS | `0` | `0` |
| FIP is present for every pitcher | PASS | `68` | `68` |
| FIP comparison arithmetic is exact | PASS | `0` | `0` |
| 2025 FIP constant matches the season run environment | PASS | `2.8099241674909328` | `2.8099241674909328` |
| 2026 FIP constant matches the season run environment | PASS | `2.303274288781535` | `2.303274288781535` |
| FIP is excluded from WAR arithmetic | PASS | `0` | `0` |
| official schedule supplies all 50 completed 2025 games | PASS | `50` | `50` |
| the exact 12-game 2025 gap is supplemented | PASS | `12` | `12` |
| supplemental games reconcile official runs | PASS | `0` | `0` |
| supplemental games have valid reconstructed runner states | PASS | `0` | `0` |
| supplemental PA reconstruction is complete | PASS | `923` | `923` |
| all completed official games reach the full PA dataset | PASS | `98` | `98` |
| primary rows contain role-specific WAR fields | PASS | `121` | `121` |
| obsolete WAR and interval fields are absent | PASS | `0` | `0` |
| old-versus-new impact report exists | PASS | `True` | `True` |
| positional research decision follows reliability gates | PASS | `insufficient_data` | `implement only if every gate passes` |
| insufficient positional evidence leaves official adjustment at zero | PASS | `0` | `0` |
| positional candidates are research-only | PASS | `0` | `0` |

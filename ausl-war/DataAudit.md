# AUSL WAR Data Audit

Snapshot: `20260704T165430Z`

- 98 completed official games: 50 from 2025 and 48 from 2026.
- The inherited detailed snapshot covers 83 games; official AUSL box scores and play-by-play supply the remaining 15.
- 5,304 normalized events and 6,019 plate appearances.
- Exact game-level reconciliation: 83/83 runs, hits, walks, and strikeouts.
- 2026 pitcher attribution: 100.0% of plate appearances.
- 2026 box-score position availability: 86.0% of hitter-game rows.
- General batted-ball direction/fielder attribution: 1,805/1,916 (94.2%).
- Expanded advancement: 1,785 opportunities; 0 unresolved candidates.
- Double-play avoidance: 209 eligible ground-ball opportunities.
- Arm attribution: 1,472 opportunities (82.5% coverage).
- Confirmed defensive-position innings coverage: 6.4%; positional-adjustment recommendation: `insufficient_data`.
- Runner-state corrections retained in the audit: 8.
- All 24 RE states observed; cell sizes range from 17 to 1143 events.

## Data limitations

GameChanger supplies named runner destinations and general batted-ball direction, enabling advancement, double-play, range, and arm components. It does not supply coordinates, hang time, exit velocity, throwing difficulty, complete relay responsibility, or reliable innings at each defensive position. Forced advances and wild-pitch/passed-ball movement are excluded from runner skill. Park factors and reliever leverage remain unavailable. The positional-adjustment study failed its innings, transition-sample, and between-season stability gates, so the official adjustment remains zero.

## Audited state corrections

- `ausl-2026-2afa123c443e6ef1` event 5: Skylar Wallace — unnamed runner displaced from third; no run inferred
- `ausl-2026-2afa123c443e6ef1` event 21: Skylar Wallace — unnamed runner displaced from third; no run inferred
- `ausl-2025-a94876c9855e5c1b` event 43: Rachel Garcia — unnamed runner displaced from third; no run inferred
- `ausl-2026-4fb9c31739b3dc79` event 35: Sami Williams — unnamed runner displaced from third; no run inferred
- `ausl-2026-d94dca75a1b579a5` event 76: Reese Atwood — unnamed runner displaced from third; no run inferred
- `ausl-2026-7a2532058c5a7568` event 13: Sami Williams — unnamed runner displaced from third; no run inferred
- `ausl-2026-80fda7ca05b7c2e8` event 26: Jaila Lassiter — unnamed runner displaced from third; no run inferred
- `ausl-2026-0ab2caaab52a1239` event 6: Jordan Woolery — unnamed runner displaced from third; no run inferred

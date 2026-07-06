# AUSL Team Scout

An isolated, static prototype for AUSL coaches and staff. It reads the captured
AUSL research outputs and generates a browser-based team scouting report.
It does not import, call, or modify the Scout Em Out application, database,
staging site, or production site.

## Build

From this directory:

```bash
python3 build.py
uv run --with reportlab --with svglib python build_pdfs.py
python3 -m http.server 8042
```

Then open `http://127.0.0.1:8042`.

The builds create `data/scouting-data.json`, six downloadable team reports under
`output/pdf/`, and copy the captured 2026 player
headshots into `assets/headshots/`. All application code is static HTML, CSS,
and JavaScript. Use the **Print / Save PDF** button for a print-friendly version
of the currently selected team or player report.

## Included data

- 2026 team and roster selection
- Team batting, pitching, value, and playing-time summaries
- Player batting, pitching, defense, baserunning, and WAR metrics
- Interactive batted-ball spray view derived from play descriptions
- Swing and called-strike take rates by count
- Recent plate appearances and batter-pitcher matchup history
- Times-through-the-order context for pitchers

Pitch type, velocity, spin, and exact pitch location are intentionally excluded
because the captured source does not provide them.

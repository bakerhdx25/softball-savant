#!/usr/bin/env python3
"""Build a self-contained AUSL pitcher times-through-the-order explorer."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output" / "tto" / "plate_appearances.json"
SUMMARY = ROOT / "output" / "tto" / "summary.json"
DESTINATION = ROOT / "output" / "tto" / "player-explorer.html"
HEADSHOT_SOURCES = (
    ROOT / "output" / "headshots_2026.json",
    ROOT / "output" / "headshots_2025.json",
)
PERIODS = (("combined", None), ("2025", 2025), ("2026", 2026))
GAME_LABELS = ("1", "2", "3", "4+")
SERIES_LABELS = ("0", "1", "2+")
PERSON_DISPLAY_NAMES = {
    "odiccialexanderbennett": "Odicci Alexander-Bennett",
    "paytongottshall": "Payton Gottshall",
}
LEAGUE_LOGO = "https://theausl.com/_next/static/media/logo-ausl.3r7ipfkm332my.svg"
TEAM_ASSETS = {
    "Bandits": ("https://resource.auprosports.com/prod/franchises/1/1-icon.svg", "#43B6E6"),
    "Blaze": ("https://resource.auprosports.com/prod/franchises/2/2-icon.svg", "#FAA21B"),
    "Cascade": ("https://resource.auprosports.com/prod/franchises/6/6-icon.svg", "#A6192E"),
    "Spark": ("https://resource.auprosports.com/prod/franchises/5/5-icon.svg", "#194F90"),
    "Talons": ("https://resource.auprosports.com/prod/franchises/3/3-icon.svg", "#2A4F3A"),
    "Volts": ("https://resource.auprosports.com/prod/franchises/4/4-icon.svg", "#440099"),
}


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def aggregate_rows(rows: list[dict[str, Any]], labels: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "PA_value", "AB_value", "H_value", "TB_value", "BB_value", "HBP_value",
        "SO_value", "HR_value", "OBP_num_value", "OBP_den_value", "wOBA_num_value",
        "wOBA_den_value", "run_value",
    )
    totals = {field: sum(float(row[field]) for row in rows) for field in fields}
    obp = ratio(totals["OBP_num_value"], totals["OBP_den_value"])
    slg = ratio(totals["TB_value"], totals["AB_value"])
    return {
        **labels,
        "PA": len(rows),
        "games": len({row["canonical_id"] for row in rows}),
        "AB": int(totals["AB_value"]),
        "H": int(totals["H_value"]),
        "BB": int(totals["BB_value"]),
        "HBP": int(totals["HBP_value"]),
        "SO": int(totals["SO_value"]),
        "HR": int(totals["HR_value"]),
        "AVG": ratio(totals["H_value"], totals["AB_value"]),
        "OBP": obp,
        "SLG": slg,
        "OPS": (obp or 0.0) + (slg or 0.0),
        "K_pct": ratio(totals["SO_value"], len(rows)),
        "BB_pct": ratio(totals["BB_value"], len(rows)),
        "HR_pct": ratio(totals["HR_value"], len(rows)),
        "wOBA": ratio(totals["wOBA_num_value"], totals["wOBA_den_value"]),
        "RV_per_PA": ratio(totals["run_value"], len(rows)),
    }


def team_name(value: str) -> str:
    normalized = (value or "").lower().strip()
    for nickname in ("bandits", "blaze", "cascade", "spark", "talons", "volts"):
        if normalized.endswith(nickname):
            return nickname.title()
    return (value or "Unknown").replace("AUSL ", "").strip()


def summary_metadata() -> dict[str, Any]:
    if not SUMMARY.exists():
        return {}
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def grouped_stats(
    rows: list[dict[str, Any]], labels: tuple[str, ...], classifier
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = classifier(row)
        if label in labels:
            groups[label].append(row)
    output = []
    for label in labels:
        group = groups.get(label, [])
        output.append(
            aggregate_rows(group, {"encounter": label})
            if group
            else {"encounter": label, "PA": 0}
        )
    return output


def period_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    same_game = grouped_stats(
        rows,
        GAME_LABELS,
        lambda row: str(row["same_game_matchup_number"])
        if row["same_game_matchup_number"] < 4
        else "4+",
    )
    prior_series = grouped_stats(
        rows,
        SERIES_LABELS,
        lambda row: "0"
        if row["prior_series_game_matchups"] == 0
        else "1"
        if row["prior_series_game_matchups"] == 1
        else "2+"
        if row["prior_series_game_matchups"] >= 2 else None,
    )
    first_rows = [row for row in rows if row["same_game_matchup_number"] == 1]
    later_rows = [row for row in rows if row["same_game_matchup_number"] >= 2]
    first = aggregate_rows(first_rows, {}) if first_rows else None
    later = aggregate_rows(later_rows, {}) if later_rows else None
    return {
        "PA": len(rows),
        "games": len({row["canonical_id"] for row in rows}),
        "same_game": same_game,
        "prior_series": prior_series,
        "first": first,
        "later": later,
        "OPS_penalty": later["OPS"] - first["OPS"] if first and later else None,
        "wOBA_penalty": later["wOBA"] - first["wOBA"] if first and later else None,
        "RV_penalty": later["RV_per_PA"] - first["RV_per_PA"] if first and later else None,
    }


def build_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summary_metadata()
    headshots: dict[str, dict[str, Any]] = {}
    for source in reversed(HEADSHOT_SOURCES):
        if source.exists():
            headshots.update(json.loads(source.read_text(encoding="utf-8")))
    player_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        player_rows[row["pitcher_key"]].append(row)

    players = []
    for key, group in player_rows.items():
        display = PERSON_DISPLAY_NAMES.get(
            key, Counter(row["pitcher"] for row in group).most_common(1)[0][0]
        )
        teams = sorted({team_name(row["fielding_team"]) for row in group})
        periods = {}
        for period, season in PERIODS:
            selected = group if season is None else [row for row in group if row["season"] == season]
            periods[period] = period_payload(selected) if selected else None
        players.append(
            {
                "key": key,
                "name": display,
                "teams": teams,
                "seasons": sorted({row["season"] for row in group}),
                "headshot": headshots.get(key, {}).get("source_url"),
                "periods": periods,
            }
        )
    players.sort(key=lambda row: (-row["periods"]["combined"]["PA"], row["name"]))

    teams = []
    for name in sorted({team for player in players for team in player["teams"]}):
        group = [row for row in rows if team_name(row["fielding_team"]) == name]
        periods = {}
        for period, season in PERIODS:
            selected = group if season is None else [row for row in group if row["season"] == season]
            periods[period] = period_payload(selected) if selected else None
        teams.append(
            {
                "key": name.lower(),
                "name": name,
                "logo": TEAM_ASSETS[name][0],
                "color": TEAM_ASSETS[name][1],
                "seasons": sorted({row["season"] for row in group}),
                "periods": periods,
            }
        )

    league = {}
    for period, season in PERIODS:
        selected = rows if season is None else [row for row in rows if row["season"] == season]
        league[period] = period_payload(selected)
    return {
        "meta": {
            "snapshot": summary.get("snapshot_id"),
            "plate_appearances": len(rows),
            "games": len({row["canonical_id"] for row in rows}),
            "pitchers": len(players),
            "league_logo": LEAGUE_LOGO,
            "official_completed_games": summary.get("official_completed_games"),
            "validation_passed": summary.get("validation_passed"),
            "pitch_text_coverage": summary.get("pitch_text_coverage"),
        },
        "league": league,
        "teams": teams,
        "players": players,
    }


HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f4f1eb">
  <link rel="icon" href="data:,">
  <title>AUSL Pitcher TTO Explorer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8; --panel: #ffffff; --raised: #f7f8fa; --soft: #f2f4f7;
      --text: #17191d; --muted: #69717e; --line: #e0e3e8; --strong: #c9ced6;
      --accent: #d84f40; --accent-soft: #d84f4012; --good: #08785a; --bad: #c43d33; --focus: #296fd6;
    }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    html { background: var(--bg); }
    body { margin: 0; min-width: 280px; overflow-x: hidden; background: var(--bg); color: var(--text); font: 14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; -webkit-font-smoothing: antialiased; }
    button, input, select { font: inherit; }
    button, select { cursor: pointer; }
    button:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid color-mix(in srgb, var(--focus) 75%, transparent); outline-offset: 2px; }
    .shell { width: min(100%, 1440px); margin: auto; padding: 0 24px 40px; }
    .topline { display: flex; justify-content: space-between; align-items: center; min-height: 58px; border-bottom: 1px solid var(--line); }
    .brand { font-size: 13px; font-weight: 900; letter-spacing: .14em; text-transform: uppercase; }
    .brand span, .eyebrow { color: var(--accent); }
    .snapshot { color: var(--muted); font-size: 12px; }
    .hero { padding: 34px 0 24px; }
    .eyebrow { margin: 0 0 7px; font-size: 11px; font-weight: 850; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 0; font-size: clamp(30px, 5vw, 54px); line-height: 1; letter-spacing: -.045em; }
    .workspace { border: 1px solid var(--line); background: var(--panel); }
    .toolbar { padding: 14px; border-bottom: 1px solid var(--line); }
    .tabs, .period-tabs { display: flex; gap: 4px; }
    .tab, .period-tab { min-height: 44px; padding: 0 17px; border: 1px solid transparent; background: transparent; color: var(--muted); font-weight: 800; }
    .tab:hover, .period-tab:hover { color: var(--text); background: var(--raised); }
    .tab[aria-selected="true"], .period-tab[aria-selected="true"] { border-color: var(--strong); background: var(--text); color: var(--bg); }
    .period-tab:disabled { cursor: default; opacity: .28; }
    .filters { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px; }
    .selector-group { display: grid; grid-template-columns: minmax(220px, 1fr); gap: 8px; width: min(100%, 780px); }
    .control { width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--strong); border-radius: 0; background: var(--soft); color: var(--text); }
    .team-buttons { display: flex; flex-wrap: wrap; gap: 4px; }
    .team-button { min-height: 44px; padding: 0 16px; border: 1px solid var(--strong); background: var(--soft); color: var(--muted); font-weight: 800; }
    .team-button:hover { color: var(--text); background: var(--raised); }
    .team-button[aria-pressed="true"] { background: var(--text); color: var(--bg); }
    .team-button img { width: 25px; height: 25px; margin-right: 7px; vertical-align: middle; object-fit: contain; }
    .period-tabs { margin-left: auto; flex: none; }
    .content-layout { min-width: 0; }
    .content-layout.has-directory { display: grid; grid-template-columns: 280px minmax(0, 1fr); }
    .pitcher-directory { min-width: 0; border-right: 1px solid var(--line); background: var(--soft); }
    .directory-head { display: grid; gap: 8px; padding: 14px; border-bottom: 1px solid var(--line); }
    .player-list { max-height: 760px; overflow-y: auto; }
    .player-button { display: block; width: 100%; padding: 12px 14px; border: 0; border-bottom: 1px solid var(--line); background: transparent; color: var(--text); text-align: left; }
    .player-button:hover { background: var(--raised); }
    .player-button[aria-current="true"] { box-shadow: inset 3px 0 var(--accent); background: var(--accent-soft); }
    .player-button strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .player-button small { color: var(--muted); }
    .no-results { padding: 22px 14px; color: var(--muted); }
    .content-pane { min-width: 0; }
    .selection-meta { position: relative; display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 52px; padding: 14px; overflow: hidden; color: var(--muted); border-bottom: 1px solid var(--line); }
    .selection-meta.has-image { min-height: 112px; padding-right: 122px; }
    .selection-meta strong { color: var(--text); font-size: 16px; }
    .selection-meta span { display: block; margin-top: 3px; font-size: 12px; }
    .entity-mark { position: absolute; right: 14px; bottom: 0; display: flex; align-items: center; justify-content: center; width: 96px; height: 108px; }
    .entity-mark img { display: block; max-width: 100%; max-height: 100%; object-fit: contain; }
    .entity-mark.headshot img { width: 96px; height: 108px; object-position: bottom center; }
    .entity-mark.team { right: 20px; bottom: 10px; width: 82px; height: 82px; padding: 13px; border-radius: 50%; background: var(--mark-color); }
    .entity-mark.league { right: 16px; bottom: 12px; width: 120px; height: 86px; padding: 9px 12px; border-radius: 4px; background: #0c2136; }
    .positive { color: var(--bad); }
    .negative { color: var(--good); }
    .section { padding: 20px 14px 24px; border-bottom: 1px solid var(--line); }
    .section-title { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
    h3 { margin: 0; font-size: 18px; letter-spacing: -.015em; }
    .section-copy { max-width: 640px; margin: 4px 0 0; color: var(--muted); font-size: 12px; }
    .table-scroll { width: 100%; max-width: 100%; overflow: auto; border: 1px solid var(--line); overscroll-behavior-inline: contain; -webkit-overflow-scrolling: touch; }
    table { width: 100%; min-width: 1000px; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; }
    th, td { height: 50px; padding: 0 13px; border-bottom: 1px solid var(--line); background: var(--panel); text-align: right; white-space: nowrap; }
    th { position: sticky; z-index: 2; top: 0; height: 43px; background: var(--soft); color: var(--muted); font-size: 10px; font-weight: 850; letter-spacing: .08em; text-transform: uppercase; }
    th:first-child, td:first-child { position: sticky; left: 0; z-index: 1; background: var(--panel); text-align: left; font-weight: 850; box-shadow: 1px 0 var(--line); }
    th:first-child { z-index: 3; background: var(--soft); }
    tbody tr:last-child td { border-bottom: 0; }
    tbody tr:hover td { background: var(--raised); }
    .league-col { color: var(--muted); }
    .empty-cell { color: #646b74; }
    .sample-warning { display: none; margin-bottom: 12px; padding: 10px 12px; border-left: 3px solid #b47b16; background: #e4b36316; color: #76500d; font-size: 12px; }
    @media (max-width: 760px) {
      .shell { padding: 0 12px 30px; }
      .filters { display: block; }
      .selector-group { grid-template-columns: 1fr; width: 100%; }
      .team-buttons { display: grid; grid-template-columns: repeat(2, 1fr); }
      .period-tabs { margin: 10px 0 0; }
      .period-tab { flex: 1; }
      .selection-meta { display: block; }
      .content-layout.has-directory { display: block; }
      .pitcher-directory { border-right: 0; border-bottom: 1px solid var(--line); }
      .player-list { max-height: 290px; }
      .section { padding: 18px 12px 22px; }
    }
    @media (max-width: 420px) {
      .topline { min-height: 52px; }
      .snapshot { display: none; }
      .hero { padding: 26px 0 20px; }
      .tab, .period-tab { flex: 1; padding: 0 8px; }
      th, td { padding-left: 10px; padding-right: 10px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="topline">
      <div class="brand">AUSL <span>TTO Lab</span></div>
      <div class="snapshot">__SUMMARY_LABEL__</div>
    </div>
    <header class="hero">
      <p class="eyebrow">AUSL pitching research</p>
      <h1>Times Through the Order</h1>
    </header>
    <section class="workspace" aria-label="Pitcher times through the order explorer">
      <div class="toolbar">
        <div class="tabs" role="tablist" aria-label="Statistics level">
          <button class="tab" role="tab" data-view="league" aria-selected="true">League</button>
          <button class="tab" role="tab" data-view="teams" aria-selected="false">Teams</button>
          <button class="tab" role="tab" data-view="pitchers" aria-selected="false">Pitchers</button>
        </div>
        <div class="filters">
          <div class="selector-group" id="team-controls" hidden>
            <div class="team-buttons" id="team-buttons" aria-label="Select a team"></div>
          </div>
          <div class="period-tabs" role="tablist" aria-label="Season">
            <button class="period-tab" role="tab" data-period="combined" aria-selected="true">2025–26</button>
            <button class="period-tab" role="tab" data-period="2025" aria-selected="false">2025</button>
            <button class="period-tab" role="tab" data-period="2026" aria-selected="false">2026</button>
          </div>
        </div>
      </div>
      <div class="content-layout" id="content-layout">
        <aside class="pitcher-directory" id="pitcher-directory" hidden>
          <div class="directory-head">
            <select class="control" id="pitcher-team" aria-label="Filter pitchers by team"><option value="">All teams</option></select>
            <input class="control" id="search" type="search" placeholder="Search pitchers" autocomplete="off" aria-label="Search pitchers">
          </div>
          <div class="player-list" id="player-list"></div>
        </aside>
        <div class="content-pane">
          <div class="selection-meta" id="selection-meta">
            <div><strong id="player-name"></strong><span id="player-identity"></span></div>
            <div class="entity-mark" id="entity-mark" hidden><img id="entity-image" alt=""></div>
          </div>
          <article class="detail">
            <section class="section">
              <div class="section-title"><h3>In-Game Matchups</h3></div>
              <div class="sample-warning" id="sample-warning">Fewer than 30 later-matchup PA. Treat this pitcher’s penalty as descriptive, not a stable skill estimate.</div>
              <div class="table-scroll"><table><thead id="game-head"></thead><tbody id="game-body"></tbody></table></div>
            </section>
            <section class="section">
              <div class="section-title"><h3>Previous Series Encounters</h3></div>
              <div class="table-scroll"><table><thead id="series-head"></thead><tbody id="series-body"></tbody></table></div>
            </section>
          </article>
        </div>
      </div>
    </section>
  </main>
  <script id="dataset" type="application/json">__DATA__</script>
  <script>
    const DATA = JSON.parse(document.getElementById('dataset').textContent);
    const leagueEntity = { id: 'league', type: 'league', key: 'league', name: 'AUSL League', logo: DATA.meta.league_logo, seasons: [2025, 2026], periods: DATA.league };
    const teamEntities = DATA.teams.map(team => ({ ...team, id: `team-${team.key}`, type: 'team' }));
    const playerEntities = DATA.players.map(player => ({ ...player, id: `pitcher-${player.key}`, type: 'pitcher' }));
    const allEntities = [leagueEntity, ...teamEntities, ...playerEntities];
    const state = { view: 'league', entity: leagueEntity, period: 'combined', query: '', team: '' };
    const $ = id => document.getElementById(id);
    const fmt = (value, digits = 3) => value == null ? '—' : Number(value).toFixed(digits).replace(/^(-?)0\./, '$1.');
    const pct = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
    const teamText = player => player.teams.join(' / ');

    function entityMeta(entity) {
      if (entity.type === 'league') return 'League-wide pitching';
      if (entity.type === 'team') return 'Team pitching';
      return teamText(entity);
    }

    function filteredPitchers() {
      const q = state.query.trim().toLowerCase();
      return playerEntities.filter(player =>
        (!state.team || player.teams.some(team => team.toLowerCase() === state.team))
        && (!q || `${player.name} ${teamText(player)}`.toLowerCase().includes(q))
      );
    }

    function renderPitcherDirectory(selectFirst = false) {
      const players = filteredPitchers();
      if (players.length && (selectFirst || !players.some(player => player.id === state.entity.id))) {
        state.entity = players[0];
        if (!state.entity.periods[state.period]) state.period = 'combined';
      }
      $('player-list').innerHTML = players.length
        ? players.map(player => `<button class="player-button" type="button" data-id="${player.id}" aria-current="${player.id === state.entity.id}"><strong>${player.name}</strong><small>${teamText(player)} · ${player.periods.combined.PA.toLocaleString()} PA</small></button>`).join('')
        : '<div class="no-results">No matching pitchers.</div>';
      $('player-list').querySelectorAll('.player-button').forEach(button => button.addEventListener('click', () => {
        selectEntity(button.dataset.id);
        renderPitcherDirectory();
      }));
    }

    function selectEntity(id, updateHash = true) {
      state.entity = allEntities.find(entity => entity.id === id) || leagueEntity;
      if (!state.entity.periods[state.period]) state.period = 'combined';
      renderDetail();
      if (updateHash) history.replaceState(null, '', `#${state.entity.id}`);
    }

    function setView(view, updateHash = true) {
      state.view = view;
      if (view === 'league') state.entity = leagueEntity;
      if (view === 'teams' && state.entity.type !== 'team') state.entity = teamEntities[0];
      if (view === 'pitchers' && state.entity.type !== 'pitcher') state.entity = playerEntities[0];
      document.querySelectorAll('.tab').forEach(button => button.setAttribute('aria-selected', String(button.dataset.view === view)));
      $('team-controls').hidden = view !== 'teams';
      $('pitcher-directory').hidden = view !== 'pitchers';
      $('content-layout').classList.toggle('has-directory', view === 'pitchers');
      document.querySelectorAll('.team-button').forEach(button => button.setAttribute('aria-pressed', String(view === 'teams' && button.dataset.team === state.entity.key)));
      if (view === 'pitchers') renderPitcherDirectory();
      selectEntity(state.entity.id, updateHash);
    }

    const columns = [
      ['PA', row => row.PA ? row.PA.toLocaleString() : '—'], ['AVG', row => fmt(row.AVG)], ['OBP', row => fmt(row.OBP)],
      ['SLG', row => fmt(row.SLG)], ['OPS', row => fmt(row.OPS)], ['K%', row => pct(row.K_pct)],
      ['BB%', row => pct(row.BB_pct)], ['HR%', row => pct(row.HR_pct)], ['wOBA', row => fmt(row.wOBA)], ['RV/PA', row => fmt(row.RV_per_PA)]
    ];

    function tableHead(firstLabel, compare) {
      return `<tr><th>${firstLabel}</th>${columns.map(([label]) => `<th>${label}</th>`).join('')}${compare ? '<th>League wOBA</th>' : ''}</tr>`;
    }

    function tableRows(rows, leagueRows, compare) {
      return rows.map((row, index) => {
        const empty = !row.PA;
        const cells = columns.map(([, getter]) => `<td class="${empty ? 'empty-cell' : ''}">${getter(row)}</td>`).join('');
        const league = leagueRows[index] && leagueRows[index].PA ? fmt(leagueRows[index].wOBA) : '—';
        return `<tr><td>${row.encounter}</td>${cells}${compare ? `<td class="league-col">${league}</td>` : ''}</tr>`;
      }).join('');
    }

    function renderDetail() {
      const entity = state.entity;
      const period = entity.periods[state.period];
      const league = DATA.league[state.period];
      const compare = entity.type !== 'league';
      $('player-name').textContent = entity.name;
      $('player-identity').textContent = `${entityMeta(entity)} · ${period.PA.toLocaleString()} PA · ${entity.seasons.join(' & ')}`;
      const image = entity.type === 'pitcher' ? entity.headshot : entity.logo;
      $('entity-mark').hidden = !image;
      $('selection-meta').classList.toggle('has-image', Boolean(image));
      if (image) {
        $('entity-mark').className = `entity-mark ${entity.type === 'pitcher' ? 'headshot' : entity.type}`;
        $('entity-mark').style.setProperty('--mark-color', entity.color || 'transparent');
        $('entity-image').src = image;
        $('entity-image').alt = `${entity.name} ${entity.type === 'pitcher' ? 'headshot' : 'logo'}`;
      } else {
        $('entity-image').removeAttribute('src');
        $('entity-image').alt = '';
      }
      document.querySelectorAll('.period-tab').forEach(button => {
        button.disabled = !entity.periods[button.dataset.period];
        button.setAttribute('aria-selected', String(button.dataset.period === state.period));
      });
      const laterPA = period.later ? period.later.PA : 0;
      $('sample-warning').style.display = entity.type === 'pitcher' && laterPA < 30 ? 'block' : 'none';
      $('game-head').innerHTML = tableHead('Meeting', compare);
      $('game-body').innerHTML = tableRows(period.same_game, league.same_game, compare);
      $('series-head').innerHTML = tableHead('Prior meetings', compare);
      $('series-body').innerHTML = tableRows(period.prior_series, league.prior_series, compare);
      document.title = `${entity.name} · AUSL TTO Explorer`;
    }

    $('team-buttons').innerHTML = teamEntities.map(team => `<button class="team-button" type="button" data-team="${team.key}" aria-pressed="false"><img src="${team.logo}" alt="">${team.name}</button>`).join('');
    $('pitcher-team').innerHTML += teamEntities.map(team => `<option value="${team.key}">${team.name}</option>`).join('');
    document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
    document.querySelectorAll('.team-button').forEach(button => button.addEventListener('click', () => {
      selectEntity(`team-${button.dataset.team}`);
      document.querySelectorAll('.team-button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    }));
    $('search').addEventListener('input', event => { state.query = event.target.value; renderPitcherDirectory(true); renderDetail(); });
    $('pitcher-team').addEventListener('change', event => { state.team = event.target.value; renderPitcherDirectory(true); renderDetail(); });
    document.querySelectorAll('.period-tab').forEach(button => button.addEventListener('click', () => { state.period = button.dataset.period; renderDetail(); }));
    const requested = location.hash.slice(1);
    if (requested && allEntities.some(entity => entity.id === requested)) {
      state.entity = allEntities.find(entity => entity.id === requested);
      state.view = state.entity.type === 'team' ? 'teams' : state.entity.type === 'pitcher' ? 'pitchers' : 'league';
    }
    setView(state.view, false);
  </script>
</body>
</html>
'''


def main() -> None:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload = build_payload(rows)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    summary_label = f"2025–26 · {payload['meta']['games']:,} completed games"
    DESTINATION.write_text(
        HTML.replace("__DATA__", serialized).replace("__SUMMARY_LABEL__", summary_label),
        encoding="utf-8",
    )
    print(
        f"Wrote {DESTINATION} ({len(payload['players'])} pitchers, "
        f"{payload['meta']['plate_appearances']:,} PA)"
    )


if __name__ == "__main__":
    main()

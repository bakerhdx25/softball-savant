#!/usr/bin/env python3
"""Build the DARKO-inspired, season-aware AUSL WAR table leaderboard."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "output" / "mobile-leaderboard.html"
TEAM_LOGOS = {
    "bandits": "https://resource.auprosports.com/prod/franchises/1/1-icon.svg",
    "blaze": "https://resource.auprosports.com/prod/franchises/2/2-icon.svg",
    "cascade": "https://resource.auprosports.com/prod/franchises/6/6-icon.svg",
    "spark": "https://resource.auprosports.com/prod/franchises/5/5-icon.svg",
    "talons": "https://resource.auprosports.com/prod/franchises/3/3-icon.svg",
    "volts": "https://resource.auprosports.com/prod/franchises/4/4-icon.svg",
}


HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f5f6f8">
  <link rel="icon" href="data:,">
  <title>AUSL WAR Leaderboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --panel-raised: #f7f8fa;
      --panel-soft: #f2f4f7;
      --text: #17191d;
      --muted: #69717e;
      --line: #e0e3e8;
      --line-strong: #c9ced6;
      --accent: #d84f40;
      --accent-soft: #d84f4012;
      --positive: #08785a;
      --negative: #c43d33;
      --focus: #296fd6;
      --rank-width: 48px;
      --player-width: 204px;
    }

    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body {
      margin: 0;
      min-width: 280px;
      overflow-x: hidden;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    button, input, select { font: inherit; }
    button, select { cursor: pointer; }
    button:focus-visible, input:focus-visible, select:focus-visible, [tabindex]:focus-visible {
      outline: 3px solid color-mix(in srgb, var(--focus) 75%, transparent);
      outline-offset: 2px;
    }

    .shell { width: min(100%, 1440px); margin: 0 auto; padding: 0 24px 40px; }
    .topline {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 58px;
      border-bottom: 1px solid var(--line);
    }
    .brand { font-size: 13px; font-weight: 900; letter-spacing: .14em; text-transform: uppercase; }
    .brand span { color: var(--accent); }
    .hero { padding: 34px 0 24px; }
    .eyebrow { margin: 0 0 7px; color: var(--accent); font-size: 11px; font-weight: 850; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: 0; font-size: clamp(30px, 5vw, 54px); line-height: 1; letter-spacing: -.045em; }
    .dek { max-width: 760px; margin: 12px 0 0; color: var(--muted); font-size: 14px; }

    .leaders { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 18px; }
    .leader-card { position: relative; min-width: 0; min-height: 132px; overflow: hidden; padding: 16px; border: 1px solid var(--line); background: var(--panel); }
    .leader-card.has-headshot { padding-right: 86px; }
    .leader-headshot { position: absolute; right: -5px; bottom: 0; width: 92px; height: 112px; object-fit: contain; object-position: bottom center; }
    .leader-label { color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
    .leader-value { margin-top: 13px; font-size: 28px; font-weight: 900; letter-spacing: -.04em; line-height: 1; }
    .leader-name { overflow: hidden; margin-top: 7px; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
    .leader-team { overflow: hidden; margin-top: 4px; color: var(--muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }

    .workspace { border: 1px solid var(--line); background: var(--panel); }
    .toolbar { padding: 14px; border-bottom: 1px solid var(--line); }
    .tabs { display: flex; gap: 4px; }
    .tab {
      min-height: 44px;
      padding: 0 17px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--muted);
      font-weight: 800;
    }
    .tab:hover { color: var(--text); background: var(--panel-raised); }
    .tab[aria-selected="true"] { border-color: var(--line-strong); background: var(--text); color: var(--bg); }
    .filters { display: grid; grid-template-columns: minmax(210px, 1fr) 125px 175px 115px 110px auto auto; gap: 8px; margin-top: 12px; }
    .control {
      width: 100%;
      min-height: 44px;
      border: 1px solid var(--line-strong);
      border-radius: 0;
      background: var(--panel-soft);
      color: var(--text);
    }
    input.control { padding: 0 12px; }
    select.control { padding: 0 30px 0 10px; }
    .download { padding: 0 15px; font-weight: 800; white-space: nowrap; }
    .download:hover { border-color: var(--accent); background: var(--accent-soft); }
    .reset { padding: 0 13px; border-color: transparent; background: transparent; color: var(--muted); font-weight: 750; }
    .reset:hover { color: var(--text); background: var(--panel-raised); }

    .table-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; padding: 0 14px; color: var(--muted); font-size: 12px; }
    .table-meta strong { color: var(--text); }
    .scroll-hint { display: none; }
    .table-scroll { width: 100%; max-width: 100%; overflow: auto; border-top: 1px solid var(--line); overscroll-behavior-inline: contain; -webkit-overflow-scrolling: touch; }
    table { width: 100%; min-width: 1050px; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; }
    th, td { height: 50px; padding: 0 13px; border-bottom: 1px solid var(--line); background: var(--panel); white-space: nowrap; }
    th {
      position: sticky;
      z-index: 4;
      top: 0;
      height: 43px;
      background: #f2f4f7;
      color: var(--muted);
      font-size: 10px;
      font-weight: 850;
      letter-spacing: .08em;
      text-align: right;
      text-transform: uppercase;
    }
    th:first-child, th:nth-child(2), th:nth-child(3) { text-align: left; }
    .sort-button { display: inline-flex; align-items: center; gap: 5px; min-height: 42px; padding: 0; border: 0; background: transparent; color: inherit; font: inherit; font-weight: inherit; letter-spacing: inherit; text-transform: inherit; }
    .sort-button:hover { color: var(--text); }
    .sort-mark { width: 9px; color: var(--accent); }
    td { text-align: right; }
    td.team-cell { max-width: 160px; overflow: hidden; color: var(--muted); text-align: left; text-overflow: ellipsis; }
    .team-list { display: inline-flex; max-width: 100%; align-items: center; gap: 6px; vertical-align: middle; }
    .team-entry { display: inline-flex; min-width: 0; align-items: center; gap: 5px; }
    .team-entry span { overflow: hidden; text-overflow: ellipsis; }
    .team-logo { width: 18px; height: 18px; flex: 0 0 18px; object-fit: contain; }
    .team-separator { color: var(--line-strong); }
    .leader-team .team-logo { width: 16px; height: 16px; flex-basis: 16px; }
    .rank-col { position: sticky; z-index: 3; left: 0; width: var(--rank-width); min-width: var(--rank-width); max-width: var(--rank-width); color: var(--muted); text-align: center !important; }
    .player-col { position: sticky; z-index: 3; left: var(--rank-width); width: var(--player-width); min-width: var(--player-width); max-width: var(--player-width); text-align: left !important; box-shadow: 1px 0 0 var(--line); }
    th.rank-col, th.player-col { z-index: 6; background: #f2f4f7; }
    .player-row:hover td, .player-row:hover .rank-col, .player-row:hover .player-col { background: var(--panel-raised); }
    .player-name { overflow: hidden; font-weight: 800; text-overflow: ellipsis; white-space: nowrap; }
    .positive { color: var(--positive); }
    .negative { color: var(--negative); }
    .primary-metric { font-weight: 900; }
    .empty { padding: 48px 16px; color: var(--muted); text-align: center; }

    .pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-height: 58px; padding: 8px 14px; }
    .page-button { min-width: 44px; min-height: 44px; border: 1px solid var(--line-strong); background: var(--panel-soft); color: var(--text); }
    .page-button:disabled { cursor: default; opacity: .35; }
    .page-label { min-width: 110px; color: var(--muted); text-align: center; }

    .method { margin-top: 18px; border: 1px solid var(--line); background: var(--panel); }
    .method h2 { margin: 0; padding: 14px; font-size: 14px; font-weight: 800; }
    .method p { max-width: 920px; margin: 0 14px 13px; color: var(--muted); font-size: 13px; }

    @media (max-width: 760px) {
      :root { --player-width: 170px; }
      .shell { padding: 0 12px 30px; }
      .topline { min-height: 52px; }
      .hero { padding: 25px 0 19px; }
      .leaders { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .leader-card { padding: 13px; }
      .leader-card.has-headshot { padding-right: 72px; }
      .leader-headshot { width: 78px; height: 96px; }
      .leader-value { margin-top: 9px; font-size: 24px; }
      .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .filters .page-size { display: none; }
      .download, .reset { grid-column: auto; }
      .scroll-hint { display: inline; }
    }
    @media (max-width: 420px) {
      :root { --rank-width: 42px; --player-width: 154px; }
      .shell { padding-left: 8px; padding-right: 8px; }
      h1 { font-size: 34px; }
      .dek { font-size: 13px; }
      .tab { flex: 1; padding: 0 8px; }
      .filters { grid-template-columns: 1fr; }
      th, td { padding-left: 10px; padding-right: 10px; }
      .pager { justify-content: center; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="topline">
      <div class="brand">AUSL <span>WAR Lab</span></div>
    </div>

    <header class="hero">
      <p class="eyebrow">AUSL player value</p>
      <h1>Player Leaderboard</h1>
      <p class="dek">Separate sortable leaderboards for AUSL position players and pitchers. Two-way players appear independently in each role.</p>
    </header>

    <section class="leaders" id="leaders" aria-label="League leaders"></section>

    <section class="workspace" aria-label="AUSL WAR leaderboard">
      <div class="toolbar">
        <div class="tabs" role="tablist" aria-label="Leaderboard view">
          <button class="tab" role="tab" aria-selected="true" data-view="position">Position Players</button>
          <button class="tab" role="tab" aria-selected="false" data-view="pitching">Pitchers</button>
        </div>
        <div class="filters">
          <input class="control" id="search" type="search" placeholder="Search players or teams" autocomplete="off" aria-label="Search players or teams">
          <select class="control" id="season" aria-label="Select season"><option value="2026">2026</option><option value="2025">2025</option></select>
          <select class="control" id="team" aria-label="Filter by team"><option value="">All teams</option></select>
          <input class="control" id="minimum" type="number" min="0" step="1" inputmode="numeric" placeholder="Min PA" aria-label="Minimum plate appearances">
          <select class="control page-size" id="page-size" aria-label="Rows per page">
            <option value="25">25 rows</option><option value="50">50 rows</option><option value="999">All rows</option>
          </select>
          <button class="control download" id="download" type="button">Download CSV</button>
          <button class="control reset" id="reset" type="button">Reset</button>
        </div>
      </div>

      <div class="table-meta"><span id="count"></span><span class="scroll-hint">Swipe table for more →</span></div>
      <div class="table-scroll" id="table-scroll" tabindex="0" aria-label="Scrollable player statistics table">
        <table>
          <thead id="table-head"></thead>
          <tbody id="table-body"></tbody>
        </table>
      </div>
      <div class="pager">
        <button class="page-button" id="previous" type="button" aria-label="Previous page">‹</button>
        <span class="page-label" id="page-label"></span>
        <button class="page-button" id="next" type="button" aria-label="Next page">›</button>
      </div>
    </section>

    <section class="method">
      <h2>Definitions and limitations</h2>
      <p>Position-player WAR excludes pitching and equals Offensive WAR plus Defensive WAR. Offensive WAR includes batting, baserunning, league balancing, and replacement value. Defensive WAR includes range, throwing, catcher throwing, and any positional adjustment. wRAA, BsR, Range Runs, and Arm Runs are runs above average.</p>
      <p>Pitcher WAR excludes hitting and baserunning. Pitcher-position fielding is separated from the RA7 component so WAR equals Pitching WAR plus Defense WAR without changing the original RA7 result. RA7 still contains teammate-defense context because complete team-defense adjustment is unavailable.</p>
      <p>FIP is shown for comparison and is not part of WAR. It uses home runs, walks, hit batters, and strikeouts, converted to seven innings with a season-specific constant that makes league-average FIP equal league-average ERA. ERA − FIP above zero means ERA is higher than FIP.</p>
      <p>These are research estimates, not official AUSL statistics. Park factor is neutral and reliever leverage is unavailable.</p>
    </section>
  </main>

  <script id="player-data" type="application/json">__PLAYER_DATA__</script>
  <script>
    const datasets = JSON.parse(document.getElementById('player-data').textContent);
    const teamLogos = __TEAM_LOGOS__;
    const leaders = document.getElementById('leaders');
    const head = document.getElementById('table-head');
    const body = document.getElementById('table-body');
    const count = document.getElementById('count');
    const search = document.getElementById('search');
    const seasonControl = document.getElementById('season');
    const team = document.getElementById('team');
    const minimum = document.getElementById('minimum');
    const pageSizeControl = document.getElementById('page-size');
    const previous = document.getElementById('previous');
    const next = document.getElementById('next');
    const pageLabel = document.getElementById('page-label');
    const download = document.getElementById('download');
    const reset = document.getElementById('reset');
    const tabs = [...document.querySelectorAll('.tab')];

    const numeric = (key, label, format = 'signed2', title = label, primary = false) => ({ key, label, format, title, numeric: true, primary });
    const text = (key, label, title = label) => ({ key, label, title, numeric: false });
    const rankColumn = { key: '__rank', label: '#', title: 'Current rank', numeric: false, rank: true };
    const playerColumn = text('player', 'Player');
    const teamColumn = text('team_display', 'Team');
    const columns = {
      position: [rankColumn, playerColumn, teamColumn,
        numeric('position_war', 'WAR', 'signed2', 'Position-player WAR; excludes pitching', true),
        numeric('offensive_war', 'Off WAR', 'signed2', 'WAR with fielding held average; includes replacement and league balancing'),
        numeric('defensive_war', 'Def WAR', 'signed2', 'Range, arm, catcher throwing, and positional value converted to wins'),
        numeric('PA', 'PA', 'integer', 'Plate Appearances'),
        numeric('wOBA', 'wOBA', 'decimal3', 'Weighted On-Base Average'),
        numeric('wRAA', 'wRAA', 'signed2', 'Weighted Runs Above Average'),
        numeric('baserunning_component_runs', 'BsR', 'signed2', 'Baserunning and double-play runs above average'),
        numeric('range_runs', 'Range Runs', 'signed2', 'Non-pitcher Range Runs'),
        numeric('throwing_runs', 'Arm Runs', 'signed2', 'Throwing runs above average, including catcher stolen-base prevention')],
      pitching: [rankColumn, playerColumn, teamColumn,
        numeric('IP', 'IP', 'decimal1', 'Innings Pitched'),
        numeric('pitcher_war', 'WAR', 'signed2', 'Pitcher WAR; excludes hitting and baserunning', true),
        numeric('pitching_war', 'Pitch WAR', 'signed2', 'Opponent-adjusted RA7 component with pitcher fielding separated'),
        numeric('pitcher_defense_war', 'Def WAR', 'signed2', 'Pitcher-position fielding value'),
        numeric('pitching_runs_above_average', 'RAA', 'signed2', 'Pitching Runs Above Average with pitcher fielding separated'),
        numeric('RA7', 'RA7', 'decimal2', 'Runs Allowed per Seven Innings'),
        numeric('ERA', 'ERA', 'decimal2', 'Earned Runs Allowed per Seven Innings'),
        numeric('FIP', 'FIP', 'decimal2', 'Fielding Independent Pitching on a seven-inning scale'),
        numeric('ERA_minus_FIP', 'ERA − FIP', 'signed2', 'Positive means ERA is higher than FIP')]
    };
    const eligible = {
      position: p => p.PA > 0 || p.advancement_opportunities > 0 || p.arm_opportunities > 0 || p.defense_runs !== 0,
      pitching: p => p.IP > 0
    };

    let view = 'position';
    let selectedSeason = '2026';
    let players = datasets[selectedSeason];
    let sortKey = 'position_war';
    let sortDirection = 'desc';
    let page = 1;

    const escapeHtml = value => String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
    const number = value => Number(value || 0);
    const formats = {
      signed2: value => `${number(value) > 0 ? '+' : ''}${number(value).toFixed(2)}`,
      decimal1: value => number(value).toFixed(1),
      decimal2: value => number(value).toFixed(2),
      decimal3: value => number(value).toFixed(3),
      integer: value => String(Math.round(number(value)))
    };
    const tone = value => number(value) > 0 ? 'positive' : number(value) < 0 ? 'negative' : '';
    const teamLogo = name => Object.entries(teamLogos).find(([nickname]) => name.toLowerCase().endsWith(nickname))?.[1] || '';
    function teamMarkup(teams) {
      return `<span class="team-list">${teams.map(name => {
        const logo = teamLogo(name);
        return `<span class="team-entry">${logo ? `<img class="team-logo" src="${escapeHtml(logo)}" alt="">` : ''}<span>${escapeHtml(name)}</span></span>`;
      }).join('<span class="team-separator" aria-hidden="true">·</span>')}</span>`;
    }
    const rounded2 = value => Math.round((number(value) + Number.EPSILON) * 100) / 100;
    function displayValue(player, column) {
      if (column.key === 'offensive_war') {
        return rounded2(player.position_war) - rounded2(player.defensive_war);
      }
      if (column.key === 'pitching_war') {
        return rounded2(player.pitcher_war) - rounded2(player.pitcher_defense_war);
      }
      return player[column.key];
    }

    function preparePlayers() {
      players = datasets[selectedSeason];
      players.forEach(player => { player.team_display = player.teams.join(' · '); });
      const allTeams = [...new Set(players.flatMap(player => player.teams))].sort();
      team.innerHTML = `<option value="">All teams</option>${allTeams.map(name => `<option>${escapeHtml(name)}</option>`).join('')}`;
    }
    preparePlayers();

    function filteredRows() {
      const query = search.value.trim().toLowerCase();
      const selectedTeam = team.value;
      const threshold = Math.max(0, number(minimum.value));
      const thresholdKey = view === 'pitching' ? 'IP' : 'PA';
      return players
        .filter(eligible[view])
        .filter(player => number(player[thresholdKey]) >= threshold)
        .filter(player => !selectedTeam || player.teams.includes(selectedTeam))
        .filter(player => !query || `${player.player} ${player.team_display}`.toLowerCase().includes(query))
        .sort((a, b) => {
          const first = a[sortKey];
          const second = b[sortKey];
          const comparison = typeof first === 'string'
            ? String(first).localeCompare(String(second))
            : number(first) - number(second);
          return (sortDirection === 'asc' ? comparison : -comparison) || a.player.localeCompare(b.player);
        });
    }

    function metricCell(player, column) {
      const value = displayValue(player, column);
      const valueTone = tone(value);
      return `<td class="${column.primary ? 'primary-metric ' : ''}${column.numeric ? valueTone : ''}">${column.numeric ? formats[column.format](value) : escapeHtml(value)}</td>`;
    }

    function renderHead() {
      const cells = columns[view].map((column, index) => {
        const classes = column.rank ? 'rank-col' : column.key === 'player' ? 'player-col' : '';
        if (column.rank) return `<th class="${classes}" scope="col">#</th>`;
        const active = sortKey === column.key;
        const mark = active ? (sortDirection === 'asc' ? '▲' : '▼') : '↕';
        return `<th class="${classes}" scope="col" aria-sort="${active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}"><button class="sort-button" type="button" data-sort="${column.key}" title="${escapeHtml(column.title)}">${escapeHtml(column.label)} <span class="sort-mark">${mark}</span></button></th>`;
      });
      head.innerHTML = `<tr>${cells.join('')}</tr>`;
    }

    function leaderSpecs() {
      if (view === 'pitching') return [
        ['Best WAR', 'pitcher_war', 'max', p => p.IP > 0, 'signed2'],
        ['Best Pitching RAA', 'pitching_runs_above_average', 'max', p => p.IP > 0, 'signed2'],
        ['Lowest RA7 · 7+ IP', 'RA7', 'min', p => p.IP >= 7, 'decimal2'],
        ['Lowest FIP · 7+ IP', 'FIP', 'min', p => p.IP >= 7, 'decimal2']
      ];
      return [
        ['Best WAR', 'position_war', 'max', eligible.position, 'signed2'],
        ['Best Offensive WAR', 'offensive_war', 'max', eligible.position, 'signed2'],
        ['Best Defensive WAR', 'defensive_war', 'max', eligible.position, 'signed2'],
        ['Best BsR', 'baserunning_component_runs', 'max', eligible.position, 'signed2'],
        ['Best wOBA · 20+ PA', 'wOBA', 'max', p => p.PA >= 20, 'decimal3'],
      ];
    }

    function renderLeaders() {
      leaders.innerHTML = leaderSpecs().map(([label, key, direction, predicate, format]) => {
        const pool = players.filter(predicate);
        const leader = [...pool].sort((a, b) => direction === 'min' ? number(a[key]) - number(b[key]) : number(b[key]) - number(a[key]))[0];
        const image = leader.headshot ? `<img class="leader-headshot" src="${escapeHtml(leader.headshot)}" alt="${escapeHtml(leader.player)} headshot">` : '';
        return `<article class="leader-card ${image ? 'has-headshot' : ''}"><div class="leader-label">${label}</div><div class="leader-value ${format.startsWith('signed') ? tone(leader[key]) : ''}">${formats[format](leader[key])}</div><div class="leader-name">${escapeHtml(leader.player)}</div><div class="leader-team">${teamMarkup(leader.teams)}</div>${image}</article>`;
      }).join('');
    }

    function render() {
      const rows = filteredRows();
      const size = Number(pageSizeControl.value);
      const pages = Math.max(1, Math.ceil(rows.length / size));
      page = Math.min(page, pages);
      const start = (page - 1) * size;
      const visible = rows.slice(start, start + size);
      renderHead();
      renderLeaders();
      count.innerHTML = `<strong>${rows.length}</strong> players · sorted by ${escapeHtml(columns[view].find(column => column.key === sortKey)?.label || 'WAR')}`;
      if (!visible.length) {
        body.innerHTML = `<tr><td colspan="${columns[view].length}" class="empty">No players match these filters.</td></tr>`;
      } else {
        body.innerHTML = visible.map((player, pageIndex) => {
          const rank = start + pageIndex + 1;
          const cells = columns[view].slice(2).map(column => column.key === 'team_display'
            ? `<td class="team-cell" title="${escapeHtml(player.team_display)}">${teamMarkup(player.teams)}</td>`
            : metricCell(player, column)).join('');
          return `<tr class="player-row" data-player-key="${escapeHtml(player.player_key)}">
            <td class="rank-col">${rank}</td>
            <td class="player-col"><span class="player-name">${escapeHtml(player.player)}</span></td>
            ${cells}
          </tr>`;
        }).join('');
      }
      pageLabel.textContent = `Page ${page} of ${pages}`;
      previous.disabled = page <= 1;
      next.disabled = page >= pages;
    }

    head.addEventListener('click', event => {
      const button = event.target.closest('[data-sort]');
      if (!button) return;
      const key = button.dataset.sort;
      if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
      else { sortKey = key; sortDirection = key === 'player' || key === 'team_display' ? 'asc' : 'desc'; }
      page = 1; render();
    });
    tabs.forEach(tab => tab.addEventListener('click', () => {
      view = tab.dataset.view;
      sortKey = view === 'pitching' ? 'pitcher_war' : 'position_war';
      minimum.placeholder = view === 'pitching' ? 'Min IP' : 'Min PA';
      minimum.setAttribute('aria-label', view === 'pitching' ? 'Minimum innings pitched' : 'Minimum plate appearances');
      minimum.value = '';
      sortDirection = 'desc'; page = 1;
      tabs.forEach(item => item.setAttribute('aria-selected', String(item === tab)));
      render();
    }));
    search.addEventListener('input', () => { page = 1; render(); });
    seasonControl.addEventListener('change', () => {
      selectedSeason = seasonControl.value;
      document.title = `AUSL ${selectedSeason} WAR Leaderboard`;
      preparePlayers();
      page = 1; render();
    });
    team.addEventListener('change', () => { page = 1; render(); });
    minimum.addEventListener('input', () => { page = 1; render(); });
    pageSizeControl.addEventListener('change', () => { page = 1; render(); });
    previous.addEventListener('click', () => { page -= 1; render(); });
    next.addEventListener('click', () => { page += 1; render(); });
    reset.addEventListener('click', () => {
      search.value = '';
      team.value = '';
      minimum.value = '';
      page = 1; render();
    });
    download.addEventListener('click', () => {
      const rows = filteredRows();
      const exportColumns = columns[view].filter(column => !column.rank);
      const quote = value => `"${String(value).replaceAll('"', '""')}"`;
      const csv = [exportColumns.map(column => quote(column.label)).join(','), ...rows.map(player => exportColumns.map(column => quote(column.numeric ? formats[column.format](displayValue(player, column)) : player[column.key])).join(','))].join('\n');
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a'); link.href = url; link.download = `ausl-${selectedSeason}-${view}-war.csv`; link.click(); URL.revokeObjectURL(url);
    });
    render();
  </script>
</body>
</html>
'''


def main() -> None:
    datasets = {}
    for season in (2025, 2026):
        players = json.loads((ROOT / "output" / f"combined_{season}.json").read_text())
        position_rows = {
            row["player_key"]: row
            for row in json.loads((ROOT / "output" / f"position_players_{season}.json").read_text())
        }
        headshots = json.loads((ROOT / "output" / f"headshots_{season}.json").read_text())
        for player in players:
            position = position_rows.get(player["player_key"], {})
            for field in ("wOBA", "H", "HR", "BB", "SO"):
                player[field] = position.get(field, 0)
            player["headshot"] = headshots.get(player["player_key"], {}).get("local_path")
        datasets[str(season)] = players
    payload = json.dumps(datasets, separators=(",", ":")).replace("</", "<\\/")
    logo_payload = json.dumps(TEAM_LOGOS, separators=(",", ":"))
    DESTINATION.write_text(
        HTML.replace("__PLAYER_DATA__", payload).replace("__TEAM_LOGOS__", logo_payload),
        encoding="utf-8",
    )
    print(
        f"Wrote {DESTINATION} with "
        + ", ".join(f"{season}: {len(rows)} players" for season, rows in datasets.items())
    )


if __name__ == "__main__":
    main()

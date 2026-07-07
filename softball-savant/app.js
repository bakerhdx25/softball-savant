const state = { site: null, datasets: {}, data: null, view: "home", period: "2026", pdfPeriod: "2026", leaguePeriod: "combined", team: null, teamTab: "overview", player: null, rosterRole: "all", playerRole: "hitting", query: "", tab: "snapshot", leaderboardRole: "position", leaderboardGroup: "war", leaderboardSeason: "2026", leaderboardSort: "position_war", leaderboardDirection: "desc" };
const DATA_URLS = [
  window.SOFTBALL_SAVANT_DATA_URL,
  "https://bakerhdx25.github.io/softball-savant/data/site-data.json",
  "data/site-data.json",
].filter(Boolean);
const COMPACT_ZONE_LABEL_ANCHORS = { "Third Base":[304,409], "Shortstop":[366,361], "Second Base":[434,361], "First Base":[496,409] };
const $ = id => document.getElementById(id);
const h = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const n = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const fixed = (value, digits = 2) => value == null ? "-" : Number(value).toFixed(digits);
const rate = value => value == null ? "-" : Number(value).toFixed(3).replace(/^0/, "").replace(/^-0/, "-.");
const pct = (value, digits = 1) => value == null ? "-" : `${(Number(value) * 100).toFixed(digits)}%`;
const signed = (value, digits = 2) => value == null ? "-" : `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(digits)}`;
const dateLabel = value => value ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(new Date(`${value}T12:00:00`)) : "-";
const playerByKey = key => state.data.players.find(player => player.key === key);
const selectedTeam = () => state.data.teams.find(team => team.key === state.team);
const ordinal = value => `${value}${value % 100 >= 11 && value % 100 <= 13 ? "th" : value % 10 === 1 ? "st" : value % 10 === 2 ? "nd" : value % 10 === 3 ? "rd" : "th"}`;
const teamLabel = key => state.datasets["2026"]?.teams.find(team => team.key === key)?.short || key;
const pythRecord = team => {
  const expectedWins = Math.round(n(team.pythagorean?.expectedWins));
  return `${expectedWins}-${Math.max(0, team.games - expectedWins)}`;
};

function empty(message) { return `<div class="empty-state">${h(message)}</div>`; }
function metric(label, value, note = "") { return `<div class="metric-card"><span class="metric-label">${h(label)}</span><span class="metric-value">${h(value)}</span>${note ? `<span class="metric-note">${h(note)}</span>` : ""}</div>`; }
function rankCard(label, value, rank) { return `<div class="rank-card"><span class="metric-label">${h(label)}</span><strong>${h(value)}</strong><span class="rank-pill">${ordinal(rank)} of 6</span></div>`; }
function sortHead(label, key = label) { return `<th><button type="button" class="sort-button" data-sort="${h(key)}">${h(label)}<svg class="sort-icon" viewBox="0 0 12 16" aria-hidden="true"><path class="sort-up" d="M2 6 6 2l4 4"></path><path class="sort-down" d="m2 10 4 4 4-4"></path></svg></button></th>`; }
function cell(value, display = value, className = "") { return `<td${className ? ` class="${className}"` : ""} data-sort-value="${h(value ?? "")}">${className === "player-cell" ? display : h(display ?? "-")}</td>`; }

function teamCard(team) {
  const record = `${team.record.wins}-${team.record.losses}${team.record.ties ? `-${team.record.ties}` : ""}`;
  return `<button class="team-card" type="button" data-team="${team.key}" style="--card-color:${team.color}"><span class="team-card-code">${team.code} · ${record}</span><strong>${h(team.name)}</strong><img src="${h(team.logo)}" alt="" loading="lazy"></button>`;
}

function renderLanding() {
  $("teams-directory").innerHTML = state.data.teams.map(teamCard).join("");
  $("teams-directory").querySelectorAll("[data-team]").forEach(button => button.addEventListener("click", () => selectTeam(button.dataset.team)));
}

function setTheme(team) {
  document.documentElement.style.setProperty("--team", team.color);
  document.documentElement.style.setProperty("--team-ink", team.ink);
}

function setHash() {
  const path = state.player ? `/players/${state.player}` : state.team ? `/teams/${state.team}` : "/";
  history.replaceState(null, "", `#${path}`);
}

function selectTeam(key, updateHash = true) {
  state.period = "2026"; state.data = state.datasets["2026"];
  const team = state.data.teams.find(item => item.key === key) || state.data.teams[0];
  state.team = team.key; state.player = null; state.teamTab = "overview"; state.query = ""; state.rosterRole = "all"; state.tab = "snapshot";
  $("player-search").value = "";
  document.querySelectorAll("[data-role]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.role === "all")));
  showView("report"); setTheme(team); renderTeam();
  if (updateHash) setHash();
  window.scrollTo({ top: 0, behavior: "instant" });
}

function showLanding() {
  location.hash = "#/";
}

function showTeamOverview(updateHash = true) {
  state.player = null; state.tab = "snapshot";
  $("team-overview").hidden = false; $("player-report").hidden = true;
  renderRoster(selectedTeam()); renderTeamOverview(selectedTeam());
  document.title = `${selectedTeam().name} · Softball Savant`;
  if (updateHash) setHash();
  window.scrollTo({ top: $("team-hero").offsetTop, behavior: "smooth" });
}

function renderTeamHero(team) {
  const record = `${team.record.wins}-${team.record.losses}${team.record.ties ? `-${team.record.ties}` : ""}`;
  const pdfTeam = state.datasets[state.pdfPeriod].teams.find(item => item.key === team.key);
  $("team-hero").innerHTML = `<div class="team-hero-copy"><p class="eyebrow">${team.code}</p><h1>${h(team.name)}</h1><p>${record}</p><div class="report-download no-print"><label>PDF report data<select data-pdf-period><option value="2026" ${state.pdfPeriod === "2026" ? "selected" : ""}>2026</option><option value="2025-2026" ${state.pdfPeriod === "2025-2026" ? "selected" : ""}>2025–26</option></select></label><a class="hero-download" href="${h(pdfTeam.pdf)}" download>Download Scouting Report</a></div></div><img class="team-logo" src="${h(team.logo)}" alt="${h(team.short)} logo">`;
  $("team-hero").querySelector("[data-pdf-period]").addEventListener("change", event => { state.pdfPeriod = event.target.value; renderTeamHero(selectedTeam()); });
}

function renderRoster(team) {
  const query = state.query.trim().toLowerCase();
  const players = team.roster.map(playerByKey).filter(Boolean).filter(player => {
    const roleMatch = state.rosterRole === "all" || (state.rosterRole === "hitters" && player.hitting) || (state.rosterRole === "pitchers" && player.pitching);
    return roleMatch && (!query || `${player.name} ${player.jersey || ""}`.toLowerCase().includes(query));
  }).sort((a, b) => state.rosterRole === "hitters" ? n(b.hitting?.PA) - n(a.hitting?.PA) || a.name.localeCompare(b.name) : state.rosterRole === "pitchers" ? n(b.pitching?.IP) - n(a.pitching?.IP) || a.name.localeCompare(b.name) : a.name.localeCompare(b.name));
  $("roster-list").innerHTML = players.length ? players.map(player => {
    const stat = state.rosterRole === "pitchers" && player.pitching ? `${fixed(player.pitching.IP, 1)} IP` : state.rosterRole === "hitters" && player.hitting ? `${player.hitting.PA} PA` : player.hitting && player.pitching ? `${player.hitting.PA} PA · ${fixed(player.pitching.IP, 1)} IP` : player.hitting ? `${player.hitting.PA} PA` : player.pitching ? `${fixed(player.pitching.IP, 1)} IP` : "Roster";
    const avatar = `<span class="roster-avatar ${player.headshot ? "" : "empty"}">${player.headshot ? `<img src="${h(player.headshot)}" alt="">` : ""}</span>`;
    return `<button class="roster-player" type="button" data-player="${player.key}" aria-current="${state.player === player.key}">${avatar}<span><strong>${player.jersey ? `#${h(player.jersey)} ` : ""}${h(player.name)}</strong></span><span class="roster-stat">${h(stat)}</span></button>`;
  }).join("") : empty("No players match this filter.");
  $("roster-list").querySelectorAll("[data-player]").forEach(button => button.addEventListener("click", () => selectPlayer(button.dataset.player)));
}

function clickableName(player) { return `<button class="table-player" data-player="${player.key}" type="button">${h(player.name)}</button>`; }

function hittingTable(players) {
  if (!players.length) return empty("No hitting data is available.");
  return `<div class="table-scroll"><table class="scout-table sortable-table"><thead><tr>${sortHead("Player")}${["PA","AB","H","HR","XBH","SBA","Bunts","BA","OBP","SLG","OPS","K%","BB%","GB%","wOBA","wRAA","Off WAR","BsR"].map(label => sortHead(label)).join("")}</tr></thead><tbody>${players.map(player => {
    const s = player.hitting; const a = player.advancedHitting || {};
    return `<tr>${cell(player.name, clickableName(player), "player-cell")}${cell(s.PA)}${cell(s.AB)}${cell(s.H)}${cell(s.HR)}${cell(s.XBH)}${cell(s.SBA)}${cell(s.Bunts)}${cell(s.BA, rate(s.BA))}${cell(s.OBP, rate(s.OBP))}${cell(s.SLG, rate(s.SLG))}${cell(s.OPS, rate(s.OPS))}${cell(s.K_pct, pct(s.K_pct))}${cell(s.BB_pct, pct(s.BB_pct))}${cell(s.GB_pct, pct(s.GB_pct))}${cell(a.wOBA, rate(a.wOBA))}${cell(a.wRAA, signed(a.wRAA, 1))}${cell(a.offensive_war, signed(a.offensive_war))}${cell(a.baserunning_runs, signed(a.baserunning_runs, 1))}</tr>`;
  }).join("")}</tbody></table></div>`;
}

function pitchingTable(players) {
  if (!players.length) return empty("No pitching data is available.");
  return `<div class="table-scroll"><table class="sortable-table"><thead><tr>${["Pitcher","App","IP","ERA","FIP","WHIP","SO/7","BB/7","S%","WAR"].map(label => sortHead(label)).join("")}</tr></thead><tbody>${players.map(player => {
    const s = player.pitching; const a = player.advancedPitching || {};
    return `<tr>${cell(player.name, clickableName(player), "player-cell")}${cell(s.App)}${cell(s.IP, fixed(s.IP, 1))}${cell(s.ERA, fixed(s.ERA))}${cell(a.FIP, fixed(a.FIP))}${cell(s.WHIP, fixed(s.WHIP))}${cell(s.SO7, fixed(s.SO7))}${cell(s.BB7, fixed(s.BB7))}${cell(s.S_pct, pct(s.S_pct))}${cell(a.pitcher_war, signed(a.pitcher_war))}</tr>`;
  }).join("")}</tbody></table></div>`;
}

function fieldingTable(players) {
  const rows = players.filter(player => player.fielding && player.fielding.totalChances);
  return `<div class="table-scroll"><table class="sortable-table"><thead><tr>${["Player","Errors","Chances","Fielding %","Range Runs","Arm Runs","Def WAR"].map(label => sortHead(label)).join("")}</tr></thead><tbody>${rows.map(player => {
    const f = player.fielding; const a = player.advancedHitting || {};
    return `<tr>${cell(player.name, clickableName(player), "player-cell")}${cell(f.errors)}${cell(f.totalChances)}${cell(f.fieldingPct, rate(f.fieldingPct))}${cell(a.range_runs, signed(a.range_runs, 1))}${cell(a.throwing_runs, signed(a.throwing_runs, 1))}${cell(a.defensive_war, signed(a.defensive_war))}</tr>`;
  }).join("")}</tbody></table></div>`;
}

function zoneColor(percentage) {
  if (percentage > 0.30) return "#075b2a";
  if (percentage > 0.20) return "#4d9348";
  if (percentage > 0.10) return "#acd276";
  return "#ffffff";
}

function sprayChart(player, compact = false) {
  const counts = player.spray.counts; const total = player.spray.total;
  const zones = Object.entries(state.data.field.zones).map(([location, points]) => {
    const percentage = total ? n(counts[location]) / total : 0; const color = zoneColor(percentage);
    const anchor = (compact ? COMPACT_ZONE_LABEL_ANCHORS[location] : null) || state.data.field.labelAnchors?.[location];
    const cx = anchor?.[0] ?? points.reduce((sum, point) => sum + point[0], 0) / points.length;
    const cy = anchor?.[1] ?? points.reduce((sum, point) => sum + point[1], 0) / points.length;
    return `<g><polygon points="${points.map(point => point.join(",")).join(" ")}" fill="${color}"><title>${h(location)}: ${n(counts[location])} (${pct(percentage, 0)})</title></polygon>${n(counts[location]) ? `<g class="zone-label ${percentage > .20 ? "on-dark" : ""}"><text x="${cx}" y="${cy + (compact ? 4 : 6)}">${pct(percentage, 0)}</text></g>` : ""}</g>`;
  }).join("");
  const pc = n(counts.Pitcher) + n(counts.Catcher); const pcPct = total ? pc / total : 0;
  const field = state.data.field;
  return `<div class="scout-spray ${compact ? "compact" : ""}"><svg viewBox="0 0 ${field.width} ${field.height}" role="img" aria-label="${h(player.name)} spray chart"><rect width="${field.width}" height="${field.height}" fill="#fff"></rect><g class="field-zones">${zones}</g><image class="field-linework" href="${h(field.image)}" x="0" y="0" width="${field.width}" height="${field.height}"></image><g class="pc-label"><rect x="310" y="582" width="180" height="28" rx="14"></rect><text x="400" y="601">Pitcher/Catcher ${pct(pcPct, 0)}</text></g></svg></div>`;
}

function sprayOverview(team) {
  const players = team.leaders.sprayOverview.map(playerByKey).filter(Boolean);
  return `<section class="subsection report-section"><div class="subsection-head"><h3>Top Player Spray Charts</h3></div><div class="spray-overview">${players.map(player => `<button class="spray-card" type="button" data-player="${player.key}"><strong>${h(player.name)}</strong><small>${player.hitting.PA} PA · ${rate(player.hitting.OPS)} OPS</small>${sprayChart(player, true)}</button>`).join("")}</div></section>`;
}

function renderTeamOverview(team) {
  const roster = team.roster.map(playerByKey).filter(Boolean);
  const hitters = roster.filter(player => player.hitting).sort((a, b) => b.hitting.PA - a.hitting.PA);
  const pitchers = roster.filter(player => player.pitching).sort((a, b) => b.pitching.IP - a.pitching.IP);
  const rosterCards = roster.map(player => `<button class="directory-player compact" type="button" data-player="${player.key}">${player.headshot ? `<img src="${h(player.headshot)}" alt="">` : `<span class="avatar-fallback">${h(player.name.split(" ").map(part => part[0]).join("").slice(0,2))}</span>`}<span><strong>${h(player.name)}</strong></span></button>`).join("");
  $("team-overview").innerHTML = `<div class="overview">
    <div class="team-page-tabs no-print" role="tablist" aria-label="Team sections">${[["overview","Overview"],["roster","Roster"],["stats","Stats"],["spray","Spray Charts"]].map(([key,label]) => `<button type="button" data-team-tab="${key}" aria-selected="${state.teamTab === key}">${label}</button>`).join("")}</div>
    <section class="team-panel ${state.teamTab === "overview" ? "active" : ""}" data-team-panel="overview"><div class="section-heading"><h2>Overview</h2></div>${teamOverviewTables(team, hitters, pitchers)}</section>
    <section class="team-panel ${state.teamTab === "roster" ? "active" : ""}" data-team-panel="roster"><div class="section-heading"><h2>Roster</h2></div><div class="team-roster-grid">${rosterCards}</div></section>
    <section class="team-panel ${state.teamTab === "stats" ? "active" : ""}" data-team-panel="stats"><div class="player-period-bar no-print"><label class="period-picker overview-period">Stats period<select data-overview-period><option value="2026" ${state.period === "2026" ? "selected" : ""}>2026</option><option value="2025" ${state.period === "2025" ? "selected" : ""}>2025</option><option value="2025-2026" ${state.period === "2025-2026" ? "selected" : ""}>2025–26</option></select></label></div><section class="subsection report-section"><div class="subsection-head"><h3>Hitting</h3></div>${hittingTable(hitters)}</section><section class="subsection report-section"><div class="subsection-head"><h3>Pitching</h3></div>${pitchingTable(pitchers)}</section><section class="subsection report-section"><div class="subsection-head"><h3>Fielding</h3></div>${fieldingTable(roster)}</section></section>
    <section class="team-panel ${state.teamTab === "spray" ? "active" : ""}" data-team-panel="spray"><div class="section-heading"><h2>Spray Charts</h2></div>${sprayOverview(team)}</section>
  </div>`;
  const periodControl = $("team-overview").querySelector("[data-overview-period]");
  if (periodControl) periodControl.addEventListener("change", event => setOverviewPeriod(event.target.value));
  $("team-overview").querySelectorAll("[data-team-tab]").forEach(button => button.addEventListener("click", () => { state.teamTab = button.dataset.teamTab; renderTeamOverview(selectedTeam()); }));
  bindPlayerLinks($("team-overview")); bindSortableTables($("team-overview"));
}

function setOverviewPeriod(period) {
  if (!state.datasets[period]) return;
  state.period = period; state.data = state.datasets[period];
  renderRoster(selectedTeam()); renderTeamOverview(selectedTeam());
}

function recentTeamGames(team) {
  const games = new Map();
  team.roster.map(playerByKey).filter(Boolean).forEach(player => {
    [...(player.hittingGameLogs || []), ...(player.pitchingGameLogs || [])].forEach(game => {
      const key = game.gameId || `${game.date}-${game.opponent}-${game.result}`;
      if (!games.has(key)) games.set(key, { date: game.date, opponent: game.opponent, result: game.result });
    });
  });
  return [...games.values()].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 6);
}

function teamOverviewTables(team, hitters, pitchers) {
  const standings = state.data.teams.filter(item => item.games > 0).sort((a,b) => b.record.wins / b.games - a.record.wins / a.games);
  const rank = standings.findIndex(item => item.key === team.key) + 1;
  const py = team.pythagorean || {};
  const recent = recentTeamGames(team);
  const leaders = [
    ["Pos WAR", hitters.filter(player => player.advancedHitting).sort((a,b) => n(b.advancedHitting.position_war) - n(a.advancedHitting.position_war))[0], player => signed(player.advancedHitting.position_war)],
    ["OPS", hitters.filter(player => player.hitting).sort((a,b) => n(b.hitting.OPS) - n(a.hitting.OPS))[0], player => rate(player.hitting.OPS)],
    ["P WAR", pitchers.filter(player => player.advancedPitching).sort((a,b) => n(b.advancedPitching.pitcher_war) - n(a.advancedPitching.pitcher_war))[0], player => signed(player.advancedPitching.pitcher_war)],
  ].filter(([, player]) => player);
  const leadersTable = `<section class="overview-card leaders-card"><h3>Team Leaders</h3><table><tbody>${leaders.map(([label, player, value]) => `<tr><td><abbr title="${label === "Pos WAR" ? "Position Player WAR" : label === "P WAR" ? "Pitcher WAR" : label}">${h(label)}</abbr></td><td>${clickableName(player)}</td><td>${value(player)}</td></tr>`).join("")}</tbody></table></section>`;
  const standingTable = `<section class="overview-card"><h3>Standing</h3><table><tbody><tr><td>Rank</td><td>${ordinal(rank)}</td></tr><tr><td>Record</td><td>${team.record.wins}-${team.record.losses}${team.record.ties ? `-${team.record.ties}` : ""}</td></tr><tr><td>Run Diff</td><td>${signed(team.summary.runs - team.summary.runsAllowed, 0)}</td></tr><tr><td>Expected W-L</td><td>${pythRecord(team)}</td></tr></tbody></table></section>`;
  const recentTable = `<section class="overview-card wide"><h3>Recent Games</h3>${recent.length ? `<table><thead><tr><th>Date</th><th>Opponent</th><th>Result</th></tr></thead><tbody>${recent.map(game => `<tr><td>${dateLabel(game.date)}</td><td>${h(game.opponent)}</td><td>${h(game.result)}</td></tr>`).join("")}</tbody></table>` : empty("No recent games available.")}</section>`;
  return `<div class="overview-card-grid">${standingTable}${leadersTable}${recentTable}</div>`;
}

function identity(player, team) {
  const details = [team?.short, player.batsThrows ? `B/T ${player.batsThrows}` : null].filter(Boolean).join(" · ");
  return `<header class="player-identity"><div><button class="team-overview-link no-print" type="button" data-team-overview>← Team Overview</button><h2>${player.jersey ? `<small>#${h(player.jersey)}</small>` : ""}${h(player.name)}</h2>${details ? `<p>${h(details)}</p>` : ""}</div>${player.headshot ? `<img class="player-headshot" src="${h(player.headshot)}" alt="${h(player.name)} headshot">` : ""}</header>`;
}

function roleToggle(player) {
  if (!(player.hitting && player.pitching)) return "";
  return `<div class="role-toggle no-print" role="group" aria-label="Player role"><button type="button" data-player-role="hitting" aria-pressed="${state.playerRole === "hitting"}">Hitting</button><button type="button" data-player-role="pitching" aria-pressed="${state.playerRole === "pitching"}">Pitching</button></div>`;
}

function basicGrid(rows, pitching = false) {
  return `<div class="original-stat-grid ${pitching ? "pitching" : ""}">${rows.map(([label, value]) => `<div><span>${h(label)}</span><strong>${h(value)}</strong></div>`).join("")}</div>`;
}

function originalHittingGrid(player) {
  const s = player.hitting;
  return basicGrid([["PA",s.PA],["AB",s.AB],["H",s.H],["K",s.K],["BB",s.BB],["HR",s.HR],["XBH",s.XBH],["SBA",s.SBA],["Bunts",s.Bunts],["HBP",s.HBP],["BA",rate(s.BA)],["OBP",rate(s.OBP)],["SLG",rate(s.SLG)],["OPS",rate(s.OPS)],["K%",pct(s.K_pct)],["BB%",pct(s.BB_pct)],["GB%",pct(s.GB_pct)]]);
}

function originalPitchingGrid(player) {
  const s = player.pitching;
  return basicGrid([["App",s.App],["IP",fixed(s.IP,1)],["ERA",fixed(s.ERA)],["FIP",fixed(player.advancedPitching?.FIP)],["WHIP",fixed(s.WHIP)],["SO/7",fixed(s.SO7)],["BB/7",fixed(s.BB7)],["S%",pct(s.S_pct)],["W-L",`${s.W}-${s.L}`]], true);
}

function contextValue(label, context) {
  const value = context.value;
  if (["wOBA"].includes(label)) return rate(value);
  if (["BB%", "K%", "HR rate"].includes(label)) return pct(value);
  if (["ERA", "FIP", "WHIP", "K/7", "BB/7"].includes(label)) return fixed(value);
  if (["Baserunning", "Range", "Arm"].includes(label)) return signed(value, 1);
  return signed(value);
}

function percentilePanel(player, role) {
  const values = player.percentiles[role];
  const qualifier = role === "hitting" ? `${player.qualifiers.hittingPA} PA` : `${fixed(player.qualifiers.pitchingIP, 1)} IP`;
  if (!values) return `<div class="qualifier-note">Not qualified (${qualifier} required)</div>`;
  return `<p class="percentile-key">Circle = percentile · right column = rank among qualified players</p><div class="percentile-list">${Object.entries(values).map(([label, context]) => { const displayLabel = label === "Position WAR" || label === "Pitcher WAR" ? "WAR" : label; return `<div class="percentile-row"><span class="percentile-name">${h(displayLabel)} <b>${h(contextValue(label, context))}</b></span><div class="percentile-track"><i style="left:50%"></i><span style="left:${context.percentile}%" aria-label="${ordinal(context.percentile)} percentile">${context.percentile}</span></div><strong class="percentile-rank"><span>${ordinal(context.rank)}</span><small>of ${context.of}</small></strong></div>`; }).join("")}</div>`;
}

function baserunningGrid(player) {
  const b = player.baserunning;
  return `<section class="detail-card subsection"><h3>Baserunning</h3><div class="metric-grid compact">${metric("BsR", signed(b.runs, 1))}${metric("Extra Bases Taken", b.extraBasesTaken)}${metric("1st → 3rd", b.firstToThird)}${metric("2nd → Home", b.secondToHome)}${metric("1st → Home", b.firstToHome)}${metric("Advancement Outs", b.advancementOuts)}</div></section>`;
}

function fieldingGrid(player) {
  const f = player.fielding;
  if (!f || !f.totalChances) return "";
  return `<section class="detail-card subsection"><h3>Fielding</h3><div class="metric-grid compact">${metric("Chances",f.totalChances)}${metric("Putouts",f.putOuts)}${metric("Assists",f.assists)}${metric("Errors",f.errors)}${metric("Fielding %",rate(f.fieldingPct))}${metric("Caught Stealing",f.caughtStealing || 0)}</div></section>`;
}

function hitterSnapshot(player) {
  const a = player.advancedHitting || {};
  return `<div class="tab-panel active" data-panel="snapshot"><div class="snapshot-layout"><section class="detail-card"><h3>Stats</h3>${originalHittingGrid(player)}</section><section class="detail-card"><h3>Advanced Stats</h3><div class="metric-grid compact">${metric("wOBA",rate(a.wOBA))}${metric("wRAA",signed(a.wRAA,1))}${metric("Offensive WAR",signed(a.offensive_war))}${metric("Defensive WAR",signed(a.defensive_war))}${metric("Range Runs",signed(a.range_runs,1))}${metric("Arm Runs",signed(a.throwing_runs,1))}${metric("WAR",signed(a.position_war))}</div></section></div>${baserunningGrid(player)}${fieldingGrid(player)}<section class="detail-card subsection"><h3>League Percentiles</h3>${percentilePanel(player,"hitting")}</section></div>`;
}

function pitcherSnapshot(player) {
  const a = player.advancedPitching || {};
  return `<div class="tab-panel active" data-panel="snapshot"><div class="snapshot-layout"><section class="detail-card"><h3>Stats</h3>${originalPitchingGrid(player)}</section><section class="detail-card"><h3>Advanced Stats</h3><div class="metric-grid compact">${metric("ERA - FIP",signed(a.ERA_minus_FIP))}${metric("Pitching WAR",signed(a.pitching_war))}${metric("Pitcher Defense WAR",signed(a.pitcher_defense_war))}${metric("WAR",signed(a.pitcher_war))}${metric("Batters Faced",n(a.batters_faced_from_play_by_play))}</div></section></div><section class="detail-card subsection"><h3>League Percentiles</h3>${percentilePanel(player,"pitching")}</section></div>`;
}

function sprayPanel(player) {
  const combined = Object.entries(player.spray.counts).reduce((rows, [location, count]) => {
    const name = location === "Pitcher" || location === "Catcher" ? "Pitcher/Catcher" : location;
    rows[name] = (rows[name] || 0) + count; return rows;
  }, {});
  return `<div class="tab-panel" data-panel="spray"><div class="subsection-head"><h3>Spray Chart</h3></div><div class="single-spray">${sprayChart(player)}</div><div class="spray-detail-grid">${Object.entries(combined).filter(([, count]) => count).sort((a,b) => b[1]-a[1]).map(([location,count]) => `<div><span>${h(location)}</span><strong>${count}</strong><small>${pct(count/player.spray.total,0)}</small></div>`).join("")}</div></div>`;
}

function swingPanel(player) {
  const baseline = Object.fromEntries(state.data.leagueApproach.map(row => [row.count,row]));
  const decision = (label, playerValue, leagueValue) => {
    const delta = playerValue == null || leagueValue == null ? null : playerValue - leagueValue;
    const deltaClass = delta == null ? "neutral" : delta > .025 ? "above" : delta < -.025 ? "below" : "neutral";
    return `<div class="decision-metric"><span>${label}</span><b>${pct(playerValue,0)}</b><small>Lg ${pct(leagueValue,0)}</small><em class="${deltaClass}">${delta == null ? "-" : `${delta > 0 ? "+" : ""}${(delta*100).toFixed(0)}`}</em></div>`;
  };
  const cells = [];
  for (let balls = 0; balls <= 3; balls += 1) {
    cells.push(`<div class="matrix-row-label"><strong>${balls}</strong><span>balls</span></div>`);
    for (let strikes = 0; strikes <= 2; strikes += 1) {
      const count = `${balls}-${strikes}`; const row = player.approach.find(item => item.count === count); const league = baseline[count];
      cells.push(`<div class="matrix-cell"><header><strong>${count}</strong><span>n=${row.pitches}</span></header><div class="decision-pair">${decision("Swing",row.swingPct,league.swingPct)}${decision("Take strike",row.calledStrikePct,league.calledStrikePct)}</div></div>`);
    }
  }
  return `<div class="tab-panel" data-panel="swing"><div class="subsection-head swing-head"><h3>Swing Decisions</h3></div><div class="count-matrix"><div class="matrix-corner">Count</div><div class="matrix-col-label">0 strikes</div><div class="matrix-col-label">1 strike</div><div class="matrix-col-label">2 strikes</div>${cells.join("")}</div></div>`;
}

function hitterGameLogs(player) {
  if (!player.hittingGameLogs.length) return empty("No game logs are available.");
  return `<div class="table-scroll"><div class="game-logs"><div class="game-log-grid game-log-header"><span>Date</span><span>Team</span><span>Result</span><span>AB</span><span>H</span><span>HR</span><span>BB</span><span>K</span><span>BA</span><span>OPS</span></div>${player.hittingGameLogs.map((game,index,games) => `${index && game.date.slice(0,4) !== games[index-1].date.slice(0,4) ? `<div class="season-divider">${h(game.date.slice(0,4))} Season</div>` : ""}<details class="game-log"><summary class="game-log-grid"><span>${dateLabel(game.date)}</span><span>${h(game.opponent)}</span><span>${h(game.result)}</span><span>${game.AB}</span><span>${game.H}</span><span>${game.HR}</span><span>${game.BB}</span><span>${game.SO}</span><span>${rate(game.BA)}</span><span>${rate(game.OPS)}</span></summary><div class="pa-list">${game.plateAppearances.map(pa => `<div><strong>${h(pa.result)} vs. ${h(pa.pitcher)}</strong>${pa.sequence ? `<span>${h(pa.sequence)}</span>` : ""}<small>${h(pa.play)}</small></div>`).join("")}</div></details>`).join("")}</div></div>`;
}

function pitcherGameLogs(player) {
  if (!player.pitchingGameLogs.length) return empty("No pitching game logs are available.");
  return `<div class="table-scroll"><table><thead><tr><th>Date</th><th>Team</th><th>Result</th><th>IP</th><th>BF</th><th>H</th><th>R</th><th>ER</th><th>BB</th><th>SO</th></tr></thead><tbody>${player.pitchingGameLogs.map((game,index,games) => `${index && game.date.slice(0,4) !== games[index-1].date.slice(0,4) ? `<tr class="season-divider-row"><td colspan="10">${h(game.date.slice(0,4))} Season</td></tr>` : ""}<tr><td>${dateLabel(game.date)}</td><td>${h(game.opponent)}</td><td>${h(game.result)}</td><td>${fixed(game.IP,1)}</td><td>${game.BF}</td><td>${game.H}</td><td>${game.R}</td><td>${game.ER}</td><td>${game.BB}</td><td>${game.SO}</td></tr>`).join("")}</tbody></table></div>`;
}

function gameLogsPanel(player, role) { return `<div class="tab-panel" data-panel="games"><div class="subsection-head"><h3>Game Logs</h3></div>${role === "hitting" ? hitterGameLogs(player) : pitcherGameLogs(player)}</div>`; }

function matchupsPanel(player) {
  if (!player.matchups?.length) return `<div class="tab-panel" data-panel="matchups">${empty("No matchup history is available.")}</div>`;
  return `<div class="tab-panel" data-panel="matchups"><div class="subsection-head"><h3>Batter–Pitcher Matchups</h3><input class="table-search" type="search" data-matchup-search placeholder="Search matchups"></div><div class="table-scroll"><table><thead><tr><th>Pitcher</th><th>PA</th><th>AB</th><th>H</th><th>HR</th><th>BB</th><th>SO</th><th>BA</th><th>OBP</th><th>SLG</th><th>OPS</th></tr></thead><tbody>${player.matchups.map(row => `<tr data-matchup-row="${h(row.pitcher)}"><td>${state.site.directory.some(item => item.key === row.pitcherKey) ? `<a class="table-player-link" href="#/players/${row.pitcherKey}">${h(row.pitcher)}</a>` : h(row.pitcher)}</td><td>${row.PA}</td><td>${row.AB}</td><td>${row.H}</td><td>${row.HR}</td><td>${row.BB}</td><td>${row.SO}</td><td>${rate(row.BA)}</td><td>${rate(row.OBP)}</td><td>${rate(row.SLG)}</td><td>${rate(row.OPS)}</td></tr>`).join("")}</tbody></table></div></div>`;
}

function bindMatchupSearch(container) {
  const input = container.querySelector("[data-matchup-search]");
  if (!input) return;
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    container.querySelectorAll("[data-matchup-row]").forEach(row => {
      row.hidden = query && !row.dataset.matchupRow.toLowerCase().includes(query);
    });
  });
}

function seasonHistoryPanel() {
  const rows = ["2026","2025"].map(season => ({season, player: state.datasets[season].players.find(item => item.key === state.player)})).filter(row => row.player);
  const role = state.playerRole;
  if (role === "pitching") {
    const pitcherRows = rows.filter(({player}) => player.pitching);
    return `<div class="tab-panel" data-panel="history"><div class="subsection-head"><h3>Season History</h3></div><div class="table-scroll"><table><thead><tr><th>Season</th><th>Team</th><th>IP</th><th>ERA</th><th>FIP</th><th>WHIP</th><th>SO</th><th>BB</th><th>Pitcher WAR</th></tr></thead><tbody>${pitcherRows.map(({season,player}) => `<tr><td>${season}</td><td>${h(state.datasets[season].teams.find(team => team.key === player.team)?.short || player.team)}</td><td>${fixed(player.pitching.IP,1)}</td><td>${fixed(player.pitching.ERA)}</td><td>${player.advancedPitching ? fixed(player.advancedPitching.FIP) : "—"}</td><td>${fixed(player.pitching.WHIP)}</td><td>${player.pitching.SO}</td><td>${player.pitching.BB}</td><td>${player.advancedPitching ? signed(player.advancedPitching.pitcher_war) : "—"}</td></tr>`).join("")}</tbody></table></div></div>`;
  }
  const hitterRows = rows.filter(({player}) => player.hitting);
  return `<div class="tab-panel" data-panel="history"><div class="subsection-head"><h3>Season History</h3></div><div class="table-scroll"><table><thead><tr><th>Season</th><th>Team</th><th>PA</th><th>H</th><th>HR</th><th>BA</th><th>OBP</th><th>SLG</th><th>OPS</th><th>Position WAR</th></tr></thead><tbody>${hitterRows.map(({season,player}) => `<tr><td>${season}</td><td>${h(state.datasets[season].teams.find(team => team.key === player.team)?.short || player.team)}</td><td>${player.hitting.PA}</td><td>${player.hitting.H}</td><td>${player.hitting.HR}</td><td>${rate(player.hitting.BA)}</td><td>${rate(player.hitting.OBP)}</td><td>${rate(player.hitting.SLG)}</td><td>${rate(player.hitting.OPS)}</td><td>${player.advancedHitting ? signed(player.advancedHitting.position_war) : "—"}</td></tr>`).join("")}</tbody></table></div></div>`;
}

function ttoPanel(player) {
  if (!player.tto.length) return `<div class="tab-panel" data-panel="tto">${empty("No times-through-the-order data is available.")}</div>`;
  const exposureTable = rows => `<div class="table-scroll"><table><thead><tr><th>Meeting</th><th>PA</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th><th>K%</th><th>BB%</th><th>wOBA</th></tr></thead><tbody>${rows.map(row => `<tr><td>${h(row.encounter)}</td><td>${row.PA}</td><td>${rate(row.AVG)}</td><td>${rate(row.OBP)}</td><td>${rate(row.SLG)}</td><td>${rate(row.OPS)}</td><td>${pct(row.K_pct)}</td><td>${pct(row.BB_pct)}</td><td>${rate(row.wOBA)}</td></tr>`).join("")}</tbody></table></div>`;
  return `<div class="tab-panel" data-panel="tto"><div class="subsection-head"><h3>Times Through the Order</h3></div>${exposureTable(player.tto)}<div class="subsection-head exposure-heading"><h3>Previous Games in the Series</h3></div>${exposureTable(player.seriesExposure || [])}</div>`;
}

function tabsForRole(role) {
  return role === "hitting" ? [["snapshot","Snapshot"],["spray","Spray Chart"],["swing","Swing Decisions"],["matchups","Matchups"],["games","Game Logs"],["history","History"]] : role === "pitching" ? [["snapshot","Snapshot"],["games","Game Logs"],["tto","Times Through Order"],["history","History"]] : [];
}

function playerTabs(role) {
  const tabs = tabsForRole(role);
  const has2026 = state.datasets["2026"].players.some(player => player.key === state.player);
  const has2025 = state.datasets["2025"].players.some(player => player.key === state.player);
  return `<div class="player-nav no-print"><label class="period-picker">Stats period<select data-player-period><option value="2026" ${state.period === "2026" ? "selected" : ""} ${has2026 ? "" : "disabled"}>2026</option><option value="2025" ${state.period === "2025" ? "selected" : ""} ${has2025 ? "" : "disabled"}>2025</option><option value="2025-2026" ${state.period === "2025-2026" ? "selected" : ""}>2025–26</option></select></label>${tabs.length ? `<div class="player-tabs" role="tablist" aria-label="Player sections">${tabs.map(([key,label]) => `<button class="player-tab" type="button" data-tab="${key}" role="tab" aria-selected="${state.tab === key}">${label}</button>`).join("")}</div>` : ""}</div>`;
}

function setPlayerPeriod(period) {
  const priorTab = state.tab; const priorRole = state.playerRole;
  state.period = period; state.data = state.datasets[period];
  const player = playerByKey(state.player);
  if (!player) return;
  const priorRoleAvailable = priorRole === "hitting" ? player?.hitting : priorRole === "pitching" ? player?.pitching : false;
  state.playerRole = priorRoleAvailable ? priorRole : player?.hitting ? "hitting" : player?.pitching ? "pitching" : "profile";
  state.tab = tabsForRole(state.playerRole).some(([key]) => key === priorTab) ? priorTab : "snapshot";
  renderRoster(selectedTeam()); renderPlayer(player);
}

function renderPlayer(player) {
  const role = state.playerRole;
  if (role === "profile") { $("player-report").innerHTML = `<div class="player-view">${identity(player,selectedTeam())}${playerTabs(role)}${empty(`No ${state.data.meta.periodLabel} hitting or pitching data is available.`)}</div>`; $("player-report").querySelectorAll("[data-team-overview]").forEach(button => button.addEventListener("click", () => showTeamOverview())); $("player-report").querySelector("[data-player-period]").addEventListener("change", event => setPlayerPeriod(event.target.value)); return; }
  const panels = role === "hitting" ? `${hitterSnapshot(player)}${sprayPanel(player)}${swingPanel(player)}${matchupsPanel(player)}${gameLogsPanel(player,role)}${seasonHistoryPanel()}` : `${pitcherSnapshot(player)}${gameLogsPanel(player,role)}${ttoPanel(player)}${seasonHistoryPanel()}`;
  $("player-report").innerHTML = `<div class="player-view">${identity(player,selectedTeam())}${roleToggle(player)}${playerTabs(role)}${panels}</div>`;
  activateTab();
  $("player-report").querySelectorAll("[data-team-overview]").forEach(button => button.addEventListener("click", () => showTeamOverview()));
  $("player-report").querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => { state.tab = button.dataset.tab; activateTab(); }));
  $("player-report").querySelector("[data-player-period]").addEventListener("change", event => setPlayerPeriod(event.target.value));
  $("player-report").querySelectorAll("[data-player-role]").forEach(button => button.addEventListener("click", () => { state.playerRole = button.dataset.playerRole; state.tab = "snapshot"; renderPlayer(player); }));
  bindMatchupSearch($("player-report"));
}

function activateTab() {
  $("player-report").querySelectorAll("[data-tab]").forEach(button => button.setAttribute("aria-selected", String(button.dataset.tab === state.tab)));
  $("player-report").querySelectorAll("[data-panel]").forEach(panel => panel.classList.toggle("active", panel.dataset.panel === state.tab));
}

function selectPlayer(key, updateHash = true) {
  let player = playerByKey(key);
  if (!player) {
    const availablePeriod = ["2026", "2025-2026", "2025"].find(period => state.datasets[period]?.players.some(item => item.key === key));
    if (!availablePeriod) return;
    state.period = availablePeriod; state.data = state.datasets[availablePeriod]; player = playerByKey(key);
  }
  const team = state.data.teams.find(item => item.key === player.team) || state.data.teams[0];
  state.team = team.key; state.player = key; state.playerRole = player.hitting ? "hitting" : player.pitching ? "pitching" : "profile"; state.tab = "snapshot";
  showView("report"); setTheme(team); renderTeamHero(team); renderRoster(team);
  $("team-overview").hidden = true; $("player-report").hidden = false; renderRoster(team); renderPlayer(player);
  document.title = `${player.name} · Softball Savant`; if (updateHash) setHash();
  const headerOffset = document.querySelector(".site-header")?.offsetHeight || 0;
  const reportTop = $("player-report").getBoundingClientRect().top + window.scrollY - headerOffset;
  window.scrollTo({ top: Math.max(0, reportTop), behavior: updateHash ? "smooth" : "instant" });
}

function bindPlayerLinks(container) { container.querySelectorAll("[data-player]").forEach(button => button.addEventListener("click", () => selectPlayer(button.dataset.player))); }

function bindSortableTables(container) {
  container.querySelectorAll(".sortable-table").forEach(table => table.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => {
    const th = button.parentElement; const index = th.cellIndex; const body = table.tBodies[0];
    const direction = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
    table.querySelectorAll("th").forEach(item => item.removeAttribute("aria-sort")); th.setAttribute("aria-sort", direction);
    const rows = Array.from(body.rows);
    rows.sort((a,b) => {
      const av = a.cells[index].dataset.sortValue ?? a.cells[index].textContent.trim(); const bv = b.cells[index].dataset.sortValue ?? b.cells[index].textContent.trim();
      const an = Number(av); const bn = Number(bv); const comparison = Number.isFinite(an) && Number.isFinite(bn) ? an - bn : av.localeCompare(bv);
      return direction === "ascending" ? comparison : -comparison;
    });
    rows.forEach(row => body.appendChild(row));
  })));
}

function renderTeam() {
  const team = selectedTeam(); renderTeamHero(team); $("opponent-select").value = team.key; renderRoster(team); renderTeamOverview(team);
  $("team-overview").hidden = Boolean(state.player); $("player-report").hidden = !state.player; if (state.player) renderPlayer(playerByKey(state.player));
  document.title = `${team.name} · Softball Savant`;
}

function bindStaticEvents() {
  $("back-button")?.addEventListener("click", showLanding);
  $("opponent-select").addEventListener("change", event => selectTeam(event.target.value));
  $("player-search").addEventListener("input", event => { state.query = event.target.value; renderRoster(selectedTeam()); });
  document.querySelectorAll(".role-filters [data-role]").forEach(button => button.addEventListener("click", () => { state.rosterRole = button.dataset.role; document.querySelectorAll(".role-filters [data-role]").forEach(item => item.setAttribute("aria-pressed", String(item === button))); renderRoster(selectedTeam()); }));
  $("global-player-search").addEventListener("input", renderGlobalSearch);
  $("global-player-search").addEventListener("focus", renderGlobalSearch);
  $("directory-search").addEventListener("input", renderDirectory);
  $("directory-team").addEventListener("change", renderDirectory);
  $("directory-status").addEventListener("change", renderDirectory);
  $("leaderboard-group").addEventListener("change", event => { state.leaderboardGroup = event.target.value; state.leaderboardSort = defaultLeaderboardSort(); state.leaderboardDirection = "desc"; renderLeaderboard(); });
  $("leaderboard-season").addEventListener("change", event => { state.leaderboardSeason = event.target.value; populateLeaderboardTeams(); renderLeaderboard(); });
  $("leaderboard-team").addEventListener("change", renderLeaderboard);
  $("leaderboard-search").addEventListener("input", renderLeaderboard);
  $("leaderboard-minimum").addEventListener("input", renderLeaderboard);
  $("leaderboard-role").querySelectorAll("[data-role]").forEach(button => button.addEventListener("click", () => { state.leaderboardRole = button.dataset.role; state.leaderboardGroup = "war"; state.leaderboardSort = defaultLeaderboardSort(); state.leaderboardDirection = "desc"; $("leaderboard-minimum").value = ""; $("leaderboard-minimum").placeholder = state.leaderboardRole === "pitching" ? "Min IP" : "Min PA"; renderLeaderboardGroups(); renderLeaderboard(); }));
  $("league-content")?.addEventListener("change", event => {
    if (event.target.matches("[data-league-period]")) {
      state.leaguePeriod = event.target.value;
      renderLeague();
    }
  });
  $("nav-toggle").addEventListener("click", () => { const expanded = $("nav-toggle").getAttribute("aria-expanded") === "true"; $("nav-toggle").setAttribute("aria-expanded", String(!expanded)); document.querySelector(".primary-nav").classList.toggle("open", !expanded); });
  window.addEventListener("hashchange", hydrateRoute);
  document.addEventListener("click", event => { if (!event.target.closest(".global-search")) $("global-search-results").hidden = true; });
}

function showView(view) {
  state.view = view;
  document.querySelectorAll(".page-view").forEach(section => { section.hidden = section.id !== `${view}-view` && !(view === "report" && section.id === "report"); });
  const activeNav = view === "report" ? "teams" : view;
  document.querySelectorAll("[data-nav]").forEach(link => link.setAttribute("aria-current", String(link.dataset.nav === activeNav ? "page" : "false")));
  if ($("global-search-results")) $("global-search-results").hidden = true;
  document.querySelector(".primary-nav").classList.remove("open"); $("nav-toggle").setAttribute("aria-expanded", "false");
  window.scrollTo({top:0,behavior:"instant"});
}

function teamLogo(teamName) {
  const normalized = String(teamName || "").toLowerCase();
  return state.datasets["2026"].teams.find(team => normalized.endsWith(team.short.toLowerCase()))?.logo || "";
}

function homeTeamLogos(row) {
  return `<span class="home-team-icons" title="${h((row.teams || []).join(" · "))}">${(row.teams || []).map(team => {
    const logo = teamLogo(team);
    return logo ? `<img src="${h(logo)}" alt="${h(team.replace("AUSL ",""))}">` : `<span>${h(team.replace("AUSL ",""))}</span>`;
  }).join("")}</span>`;
}

function renderHome() {
  const data = state.datasets["2026"];
  const standings = [...data.teams].sort((a,b) => b.record.wins / b.games - a.record.wins / a.games);
  $("home-standings").innerHTML = `<div class="table-scroll"><table class="savant-table home-standings-table"><thead><tr><th>#</th><th>Team</th><th>W</th><th>L</th><th>Pct</th><th>RS</th><th>RA</th><th>Run Diff</th><th>xW-L</th></tr></thead><tbody>${standings.map((team,index) => `<tr><td>${index+1}</td><td><a class="team-table-link" href="#/teams/${team.key}"><img src="${h(team.logo)}" alt=""><span>${h(team.short)}</span></a></td><td>${team.record.wins}</td><td>${team.record.losses}</td><td>${fixed(team.record.wins / team.games,3)}</td><td>${team.summary.runs}</td><td>${team.summary.runsAllowed}</td><td>${signed(team.summary.runs-team.summary.runsAllowed,0)}</td><td>${pythRecord(team)}</td></tr>`).join("")}</tbody></table></div>`;
  const rows = state.site.leaderboards["2026"];
  const positionLeaders = [...rows].filter(row => n(row.PA) > 0).sort((a,b) => n(b.position_war) - n(a.position_war)).slice(0, 10);
  const pitcherLeaders = [...rows].filter(row => n(row.IP) > 0).sort((a,b) => n(b.pitcher_war) - n(a.pitcher_war)).slice(0, 10);
  const leaderTable = (title, leaders, key) => `<section class="home-leader-table"><h3>${title}</h3><div class="table-scroll"><table class="savant-table home-leaders-table"><thead><tr><th>#</th><th>Player</th><th>Team</th><th>WAR</th></tr></thead><tbody>${leaders.map((row,index) => `<tr><td>${index+1}</td><td class="leaderboard-player"><a href="#/players/${row.player_key}">${h(row.player)}</a></td><td>${homeTeamLogos(row)}</td><td class="primary-metric">${signed(row[key])}</td></tr>`).join("")}</tbody></table></div></section>`;
  $("home-leaders").innerHTML = `<div class="home-leader-grid">${leaderTable("Position Player WAR", positionLeaders, "position_war")}${leaderTable("Pitcher WAR", pitcherLeaders, "pitcher_war")}</div>`;
}

function renderGlobalSearch() {
  const query = $("global-player-search").value.trim().toLowerCase();
  const results = query ? state.site.directory.filter(player => `${player.name} ${teamLabel(player.team)} ${(player.positions || []).join(" ")}`.toLowerCase().includes(query)).slice(0,8) : state.site.directory.filter(player => player.currentRoster).slice(0,6);
  $("global-search-results").innerHTML = results.length ? results.map(player => `<a href="#/players/${player.key}">${player.headshot ? `<img src="${h(player.headshot)}" alt="">` : `<span class="search-avatar"></span>`}<span><strong>${h(player.name)}</strong><small>${h(teamLabel(player.team))} · ${player.seasons.join(" & ")}</small></span></a>`).join("") : `<div class="no-search-results">No players found.</div>`;
  $("global-search-results").hidden = false;
}

function renderDirectory() {
  const query = $("directory-search").value.trim().toLowerCase(); const team = $("directory-team").value; const status = $("directory-status").value;
  const players = state.site.directory.filter(player => (!query || `${player.name} ${teamLabel(player.team)} ${(player.positions || []).join(" ")}`.toLowerCase().includes(query)) && (!team || player.team === team) && (status === "all" || (status === "current") === player.currentRoster));
  $("player-directory").innerHTML = players.length ? players.map(player => `<a class="directory-player" href="#/players/${player.key}">${player.headshot ? `<img src="${h(player.headshot)}" alt="">` : `<span class="avatar-fallback">${h(player.name.split(" ").map(part => part[0]).join("").slice(0,2))}</span>`}<span><strong>${h(player.name)}</strong><small>${h(teamLabel(player.team))} · ${player.seasons.join(" & ")}${player.currentRoster ? "" : " · past roster"}</small></span></a>`).join("") : empty("No players match these filters.");
}

const LEADERBOARD_GROUPS = {
  position: [
    ["war", "WAR", [["player","Player","text"],["teams","Team","teams"],["position_war","WAR","signed"],["offensive_war","Off WAR","signed"],["defensive_war","Def WAR","signed"],["PA","PA","int"],["wOBA","wOBA","rate"],["wRAA","wRAA Runs","signed"],["baserunning_component_runs","BsR Runs","signed"],["range_runs","Range Runs","signed"],["arm_runs","Arm Runs","signed"]]],
    ["hitting", "Hitting", [["player","Player","text"],["teams","Team","teams"],["PA","PA","int"],["H","H","int"],["HR","HR","int"],["BB","BB","int"],["SO","SO","int"],["wOBA","wOBA","rate"],["wRAA","wRAA Runs","signed"],["hitting_runs","Hit Runs","signed"],["batting_runs","Bat Runs","signed"],["batting_war","Bat WAR","signed"],["league_adjustment_runs","Lg Adj Runs","signed"],["position_replacement_runs","Repl Runs","signed"],["positional_adjustment_runs","Pos Adj Runs","signed"],["position_war","WAR","signed"]]],
    ["running", "Baserunning", [["player","Player","text"],["teams","Team","teams"],["PA","PA","int"],["advancement_opportunities","Adv Opp","int"],["runner_advancement_runs","Runner Adv Runs","signed"],["batter_advancement_runs","Batter Adv Runs","signed"],["non_steal_advancement_runs","Non-SB Adv Runs","signed"],["sb_cs_runs","SB/CS Runs","signed"],["double_play_opportunities","DP Opp","int"],["double_play_avoidance_runs","DP Runs","signed"],["baserunning_runs","Raw BsR Runs","signed"],["baserunning_component_runs","BsR Runs","signed"],["baserunning_war","BsR WAR","signed"]]],
    ["fielding", "Fielding", [["player","Player","text"],["teams","Team","teams"],["PA","PA","int"],["range_runs","Range Runs","signed"],["throwing_runs","Throwing Runs","signed"],["arm_runs","Arm Runs","signed"],["arm_opportunities","Arm Opp","int"],["defense_runs","Def Runs","signed"],["defense_war","Def WAR","signed"],["defensive_war","Total Def WAR","signed"],["quality_flags","Flags","flags"],["catcher_steal_attempts","C Att","int"],["catcher_caught_stealing","C CS","int"],["catcher_cs_rate","C CS%","pct"],["catcher_throwing_runs","C Throw Runs","signed"]]],
  ],
  pitching: [
    ["war", "WAR", [["player","Pitcher","text"],["teams","Team","teams"],["IP","IP","one"],["pitcher_war","WAR","signed"],["pitching_war","Pitch WAR","signed"],["pitcher_defense_war","Def WAR","signed"],["pitching_runs_above_average","RAA Runs","signed"],["RA7","RA7","two"],["ERA","ERA","two"],["FIP","FIP","two"],["ERA_minus_FIP","ERA − FIP","signed"]]],
    ["pitching", "Pitching", [["player","Pitcher","text"],["teams","Team","teams"],["IP","IP","one"],["ERA","ERA","two"],["RA7","RA7","two"],["FIP","FIP","two"],["ERA_minus_FIP","ERA − FIP","signed"],["opponent_expected_RA7","Opp Exp RA7","two"],["ra7_pitching_runs_above_average","RA7 RAA Runs","signed"],["pitching_runs_above_average","Pitch RAA Runs","signed"],["pitching_war","Pitch WAR","signed"],["FIP_BF","BF","int"]]],
    ["defense", "Pitcher Defense", [["player","Pitcher","text"],["teams","Team","teams"],["IP","IP","one"],["pitcher_range_runs","Pitcher Range Runs","signed"],["pitcher_arm_runs","Pitcher Arm Runs","signed"],["pitcher_defense_runs","Def Runs","signed"],["pitcher_defense_war","Def WAR","signed"],["pitcher_war","WAR","signed"]]],
  ]
};

function leaderboardValue(row, key) { return key === "teams" ? row.teams.join(" · ") : row[key]; }
function leaderboardDisplay(row, key, format) { const value = leaderboardValue(row,key); if (format === "teams") return `<span class="team-list-cell">${row.teams.map(team => `${teamLogo(team) ? `<img src="${h(teamLogo(team))}" alt="">` : ""}<span>${h(team.replace("AUSL ",""))}</span>`).join(" · ")}</span>`; if (format === "rate") return rate(value); if (format === "pct") return pct(value); if (format === "signed") return signed(value); if (format === "one") return fixed(value,1); if (format === "two") return fixed(value,2); if (format === "flags") return Array.isArray(value) && value.length ? h(value.join(", ")) : "—"; return h(value); }
function leaderboardGroup() { return LEADERBOARD_GROUPS[state.leaderboardRole].find(([key]) => key === state.leaderboardGroup) || LEADERBOARD_GROUPS[state.leaderboardRole][0]; }
function defaultLeaderboardSort() { return state.leaderboardRole === "pitching" ? "pitcher_war" : "position_war"; }
function renderLeaderboardGroups() {
  const groups = LEADERBOARD_GROUPS[state.leaderboardRole];
  $("leaderboard-group").innerHTML = groups.map(([key, label]) => `<option value="${key}" ${state.leaderboardGroup === key ? "selected" : ""}>${h(label)}</option>`).join("");
}

function populateLeaderboardTeams() {
  const names = [...new Set(state.site.leaderboards[state.leaderboardSeason].flatMap(row => row.teams || []))].sort();
  $("leaderboard-team").innerHTML = `<option value="">All teams</option>${names.map(name => `<option>${h(name)}</option>`).join("")}`;
}

function renderLeaderboard() {
  const role = state.leaderboardRole; const columns = leaderboardGroup()[2]; const query = $("leaderboard-search").value.trim().toLowerCase(); const team = $("leaderboard-team").value; const minimum = Math.max(0,n($("leaderboard-minimum").value)); const threshold = role === "pitching" ? "IP" : "PA";
  if (!columns.some(([key]) => key === state.leaderboardSort)) state.leaderboardSort = defaultLeaderboardSort();
  renderLeaderboardGroups();
  $("leaderboard-role").querySelectorAll("[data-role]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.role === role)));
  const rows = state.site.leaderboards[state.leaderboardSeason].filter(row => n(row[threshold]) > 0 && n(row[threshold]) >= minimum && (!team || row.teams.includes(team)) && (!query || `${row.player} ${(row.teams || []).join(" ")}`.toLowerCase().includes(query))).sort((a,b) => { const av=leaderboardValue(a,state.leaderboardSort), bv=leaderboardValue(b,state.leaderboardSort); const comparison = typeof av === "string" ? av.localeCompare(bv) : n(av)-n(bv); return state.leaderboardDirection === "asc" ? comparison : -comparison; });
  $("leaderboard-head").innerHTML = `<tr><th>#</th>${columns.map(([key,label]) => `<th><button type="button" data-lb-sort="${key}" aria-sort="${state.leaderboardSort === key ? state.leaderboardDirection : "none"}">${label}${state.leaderboardSort === key ? state.leaderboardDirection === "asc" ? " ↑" : " ↓" : ""}</button></th>`).join("")}</tr>`;
  $("leaderboard-body").innerHTML = rows.map((row,index) => `<tr><td>${index+1}</td>${columns.map(([key,,format]) => `<td class="${key === "player" ? "leaderboard-player" : key.includes("war") ? "primary-metric" : ""}">${key === "player" ? `<a href="#/players/${row.player_key}">${h(row.player)}</a>` : leaderboardDisplay(row,key,format)}</td>`).join("")}</tr>`).join("");
  $("leaderboard-meta").textContent = `${rows.length} players · ${state.leaderboardSeason} season`;
  $("leaderboard-head").querySelectorAll("[data-lb-sort]").forEach(button => button.addEventListener("click", () => { const key=button.dataset.lbSort; if (state.leaderboardSort === key) state.leaderboardDirection = state.leaderboardDirection === "asc" ? "desc" : "asc"; else { state.leaderboardSort=key; state.leaderboardDirection = ["player","teams"].includes(key) ? "asc" : "desc"; } renderLeaderboard(); }));
}

function exposureTable(title, rows, firstLabel) {
  return `<section class="league-card"><div class="section-heading"><h2>${title}</h2></div><div class="table-scroll"><table class="savant-table"><thead><tr><th>${firstLabel}</th><th>PA</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th><th>K%</th><th>BB%</th><th>wOBA</th><th>RV/PA</th></tr></thead><tbody>${rows.map(row => `<tr><td>${h(row.encounter)}</td><td>${row.PA || "—"}</td><td>${rate(row.AVG)}</td><td>${rate(row.OBP)}</td><td>${rate(row.SLG)}</td><td>${rate(row.OPS)}</td><td>${pct(row.K_pct)}</td><td>${pct(row.BB_pct)}</td><td>${rate(row.wOBA)}</td><td>${fixed(row.RV_per_PA,3)}</td></tr>`).join("")}</tbody></table></div></section>`;
}

function periodLabel(period) {
  return period === "combined" || period === "2025-2026" ? "2025–26" : period;
}

function battingLine(players) {
  const hitters = players.filter(player => player.hitting);
  const totals = hitters.reduce((acc, player) => {
    const s = player.hitting;
    acc.PA += n(s.PA); acc.AB += n(s.AB); acc.H += n(s.H); acc.HR += n(s.HR); acc.BB += n(s.BB); acc.SO += n(s.K ?? s.SO); acc.HBP += n(s.HBP); acc.TB += n(s.SLG) * n(s.AB);
    return acc;
  }, {PA:0, AB:0, H:0, HR:0, BB:0, SO:0, HBP:0, TB:0});
  totals.BA = totals.AB ? totals.H / totals.AB : null;
  totals.OBP = totals.AB + totals.BB + totals.HBP ? (totals.H + totals.BB + totals.HBP) / (totals.AB + totals.BB + totals.HBP) : null;
  totals.SLG = totals.AB ? totals.TB / totals.AB : null;
  totals.OPS = totals.OBP != null && totals.SLG != null ? totals.OBP + totals.SLG : null;
  totals.K_pct = totals.PA ? totals.SO / totals.PA : null;
  totals.BB_pct = totals.PA ? totals.BB / totals.PA : null;
  return totals;
}

function pitchingLine(players) {
  const pitchers = players.filter(player => player.pitching);
  const totals = pitchers.reduce((acc, player) => {
    const s = player.pitching;
    acc.App += n(s.App); acc.IP += n(s.IP); acc.H += n(s.H); acc.BB += n(s.BB); acc.SO += n(s.SO); acc.Pitches += n(s.Pitches); acc.Strikes += n(s.Strikes); acc.ER += n(s.ERA) * n(s.IP) / 7;
    return acc;
  }, {App:0, IP:0, H:0, BB:0, SO:0, Pitches:0, Strikes:0, ER:0});
  totals.ERA = totals.IP ? totals.ER * 7 / totals.IP : null;
  totals.WHIP = totals.IP ? (totals.H + totals.BB) / totals.IP : null;
  totals.SO7 = totals.IP ? totals.SO * 7 / totals.IP : null;
  totals.BB7 = totals.IP ? totals.BB * 7 / totals.IP : null;
  totals.S_pct = totals.Pitches ? totals.Strikes / totals.Pitches : null;
  return totals;
}

function teamStatRows(data) {
  return data.teams.map(team => {
    const players = team.roster.map(key => data.players.find(player => player.key === key)).filter(Boolean);
    return { team, batting: battingLine(players), pitching: pitchingLine(players) };
  });
}

function leagueBattingTable(data) {
  const players = data.players;
  const batting = battingLine(players);
  return `<section class="league-card"><div class="section-heading"><h2>League Batting</h2></div><div class="table-scroll"><table class="savant-table"><thead><tr><th>PA</th><th>AB</th><th>H</th><th>HR</th><th>BB</th><th>SO</th><th>BA</th><th>OBP</th><th>SLG</th><th>OPS</th><th>K%</th><th>BB%</th></tr></thead><tbody><tr><td>${batting.PA}</td><td>${batting.AB}</td><td>${batting.H}</td><td>${batting.HR}</td><td>${batting.BB}</td><td>${batting.SO}</td><td>${rate(batting.BA)}</td><td>${rate(batting.OBP)}</td><td>${rate(batting.SLG)}</td><td>${rate(batting.OPS)}</td><td>${pct(batting.K_pct)}</td><td>${pct(batting.BB_pct)}</td></tr></tbody></table></div></section>`;
}

function leaguePitchingTable(data) {
  const players = data.players;
  const pitching = pitchingLine(players);
  return `<section class="league-card"><div class="section-heading"><h2>League Pitching</h2></div><div class="table-scroll"><table class="savant-table"><thead><tr><th>App</th><th>IP</th><th>ERA</th><th>WHIP</th><th>H</th><th>BB</th><th>SO</th><th>SO/7</th><th>BB/7</th><th>S%</th></tr></thead><tbody><tr><td>${pitching.App}</td><td>${fixed(pitching.IP,1)}</td><td>${fixed(pitching.ERA)}</td><td>${fixed(pitching.WHIP)}</td><td>${pitching.H}</td><td>${pitching.BB}</td><td>${pitching.SO}</td><td>${fixed(pitching.SO7)}</td><td>${fixed(pitching.BB7)}</td><td>${pct(pitching.S_pct)}</td></tr></tbody></table></div></section>`;
}

function teamBattingTable(rows) {
  return `<section class="league-card"><div class="section-heading"><h2>Team Batting</h2></div><div class="table-scroll"><table class="savant-table"><thead><tr><th>Team</th><th>PA</th><th>AB</th><th>H</th><th>HR</th><th>BB</th><th>SO</th><th>BA</th><th>OBP</th><th>SLG</th><th>OPS</th><th>K%</th><th>BB%</th></tr></thead><tbody>${rows.sort((a,b) => n(b.batting.OPS)-n(a.batting.OPS)).map(({team, batting}) => `<tr><td><a class="team-table-link" href="#/teams/${team.key}"><img src="${h(team.logo)}" alt="">${h(team.short)}</a></td><td>${batting.PA}</td><td>${batting.AB}</td><td>${batting.H}</td><td>${batting.HR}</td><td>${batting.BB}</td><td>${batting.SO}</td><td>${rate(batting.BA)}</td><td>${rate(batting.OBP)}</td><td>${rate(batting.SLG)}</td><td>${rate(batting.OPS)}</td><td>${pct(batting.K_pct)}</td><td>${pct(batting.BB_pct)}</td></tr>`).join("")}</tbody></table></div></section>`;
}

function teamPitchingTable(rows) {
  return `<section class="league-card"><div class="section-heading"><h2>Team Pitching</h2></div><div class="table-scroll"><table class="savant-table"><thead><tr><th>Team</th><th>App</th><th>IP</th><th>ERA</th><th>WHIP</th><th>H</th><th>BB</th><th>SO</th><th>SO/7</th><th>BB/7</th><th>S%</th></tr></thead><tbody>${rows.sort((a,b) => n(a.pitching.ERA)-n(b.pitching.ERA)).map(({team, pitching}) => `<tr><td><a class="team-table-link" href="#/teams/${team.key}"><img src="${h(team.logo)}" alt="">${h(team.short)}</a></td><td>${pitching.App}</td><td>${fixed(pitching.IP,1)}</td><td>${fixed(pitching.ERA)}</td><td>${fixed(pitching.WHIP)}</td><td>${pitching.H}</td><td>${pitching.BB}</td><td>${pitching.SO}</td><td>${fixed(pitching.SO7)}</td><td>${fixed(pitching.BB7)}</td><td>${pct(pitching.S_pct)}</td></tr>`).join("")}</tbody></table></div></section>`;
}

function renderLeague() {
  const period = state.site.periods[state.leaguePeriod] ? state.leaguePeriod : "combined";
  state.leaguePeriod = period;
  const teamData = state.site.periods["2026"]; const data = state.site.periods[period]; const tto = state.site.tto.league[period] || {same_game: [], prior_series: []};
  const periods = ["combined", "2026", "2025"].filter(key => state.site.periods[key]);
  const controls = `<div class="league-toolbar"><label>Season<select data-league-period>${periods.map(key => `<option value="${key}" ${period === key ? "selected" : ""}>${periodLabel(key)}</option>`).join("")}</select></label></div>`;
  const rows = teamStatRows(teamData);
  $("league-content").innerHTML = `${teamBattingTable([...rows])}${teamPitchingTable([...rows])}${controls}${leagueBattingTable(data)}${leaguePitchingTable(data)}<div class="league-grid">${exposureTable("Times Through the Order",tto.same_game,"Meeting")}${exposureTable("Series Familiarity",tto.prior_series,"Prior Meetings")}</div>`;
}

function hydrateRoute() {
  if (!state.site) return;
  const parts = location.hash.replace(/^#\/?/,"").split("/").filter(Boolean); const root = parts[0] || "home"; const key = parts[1];
  if (root === "players" && key) { state.period = state.datasets["2026"].players.some(player => player.key === key) ? "2026" : "2025-2026"; state.data = state.datasets[state.period]; selectPlayer(key,false); return; }
  if (root === "teams" && key) { selectTeam(key,false); return; }
  state.team = null; state.player = null;
  if (root === "players") { showView("players"); renderDirectory(); document.title="Players · Softball Savant"; }
  else if (root === "leaderboards") { showView("leaderboards"); renderLeaderboard(); document.title="Leaderboards · Softball Savant"; }
  else if (root === "league") { showView("league"); renderLeague(); document.title="League Stats · Softball Savant"; }
  else if (root === "teams") { showView("teams"); renderLanding(); document.title="Teams · Softball Savant"; }
  else { showView("home"); renderHome(); document.title="Softball Savant · AUSL Analytics"; }
}

async function start() {
  try {
    let lastError = null;
    for (const url of DATA_URLS) {
      try {
        const response = await fetch(url,{cache:"no-store"});
        if (!response.ok) throw new Error(`${url} returned ${response.status}`);
        state.site = await response.json();
        break;
      } catch (error) {
        lastError = error;
      }
    }
    if (!state.site) throw lastError || new Error("No data URL configured");
    state.datasets = {"2026":state.site.periods["2026"],"2025":state.site.periods["2025"],"2025-2026":state.site.periods.combined}; state.data = state.datasets["2026"]; if ($("data-stamp")) $("data-stamp").textContent = `2026 · ${state.data.meta.games} games`;
    $("opponent-select").innerHTML = state.data.teams.map(team => `<option value="${team.key}">${h(team.name)}</option>`).join("");
    const teams = state.data.teams.map(team => `<option value="${team.key}">${h(team.short)}</option>`).join(""); $("directory-team").innerHTML += teams; renderLeaderboardGroups(); populateLeaderboardTeams();
    bindStaticEvents(); hydrateRoute(); $("loading").hidden = true;
  } catch (error) { $("loading").innerHTML = `<div><strong>Softball Savant data could not be loaded.</strong><br><small>${h(error.message)}</small></div>`; }
}

start();

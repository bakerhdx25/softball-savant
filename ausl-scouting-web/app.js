const state = { datasets: {}, data: null, period: "2026", pdfPeriod: "2026", team: null, player: null, rosterRole: "all", playerRole: "hitting", query: "", tab: "snapshot" };
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
  $("team-grid").innerHTML = state.data.teams.map(teamCard).join("");
  $("team-grid").querySelectorAll("[data-team]").forEach(button => button.addEventListener("click", () => selectTeam(button.dataset.team)));
}

function setTheme(team) {
  document.documentElement.style.setProperty("--team", team.color);
  document.documentElement.style.setProperty("--team-ink", team.ink);
}

function setHash() {
  const params = new URLSearchParams();
  if (state.team) params.set("team", state.team);
  if (state.player) params.set("player", state.player);
  history.replaceState(null, "", `#${params.toString()}`);
}

function selectTeam(key, updateHash = true) {
  state.period = "2026"; state.data = state.datasets["2026"];
  const team = state.data.teams.find(item => item.key === key) || state.data.teams[0];
  state.team = team.key; state.player = null; state.query = ""; state.rosterRole = "all"; state.tab = "snapshot";
  $("player-search").value = "";
  document.querySelectorAll("[data-role]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.role === "all")));
  $("landing").hidden = true; $("report").hidden = false; setTheme(team); renderTeam();
  if (updateHash) setHash();
  window.scrollTo({ top: 0, behavior: "instant" });
}

function showLanding() {
  state.team = null; state.player = null; $("landing").hidden = false; $("report").hidden = true;
  history.replaceState(null, "", location.pathname); document.title = "AUSL Team Scout"; window.scrollTo({ top: 0, behavior: "instant" });
}

function showTeamOverview(updateHash = true) {
  state.player = null; state.tab = "snapshot";
  $("team-overview").hidden = false; $("player-report").hidden = true;
  renderRoster(selectedTeam()); renderTeamOverview(selectedTeam());
  document.title = `${selectedTeam().name} · AUSL Team Scout`;
  if (updateHash) setHash();
  window.scrollTo({ top: $("team-hero").offsetTop, behavior: "smooth" });
}

function renderTeamHero(team) {
  const record = `${team.record.wins}-${team.record.losses}${team.record.ties ? `-${team.record.ties}` : ""}`;
  const pdfTeam = state.datasets[state.pdfPeriod].teams.find(item => item.key === team.key);
  $("team-hero").innerHTML = `<div class="team-hero-copy"><p class="eyebrow">2026 team report · ${team.code}</p><h1>${h(team.name)}</h1><p>${record} · ${team.games} games</p><div class="report-download no-print"><label>PDF report data<select data-pdf-period><option value="2026" ${state.pdfPeriod === "2026" ? "selected" : ""}>2026</option><option value="2025-2026" ${state.pdfPeriod === "2025-2026" ? "selected" : ""}>2025–26</option></select></label><a class="hero-download" href="${h(pdfTeam.pdf)}" download>Download Scouting Report</a></div></div><img class="team-logo" src="${h(team.logo)}" alt="${h(team.short)} logo">`;
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
  const record = `${team.record.wins}-${team.record.losses}${team.record.ties ? `-${team.record.ties}` : ""}`;
  $("team-overview").innerHTML = `<div class="overview"><div class="section-heading"><h2>Team Overview</h2></div>
    <div class="rank-grid">${rankCard("Record", record, team.rankings.record)}${rankCard("Runs/Game", fixed(team.summary.runsPerGame, 2), team.rankings.runsPerGame)}${rankCard("ERA", fixed(team.summary.ERA), team.rankings.ERA)}${rankCard("OPS", rate(team.summary.OPS), team.rankings.OPS)}</div>
    <div class="player-period-bar no-print"><label class="period-picker overview-period">Player stats period<select data-overview-period><option value="2026" ${state.period === "2026" ? "selected" : ""}>2026</option><option value="2025" ${state.period === "2025" ? "selected" : ""}>2025</option><option value="2025-2026" ${state.period === "2025-2026" ? "selected" : ""}>2025–26</option></select></label></div>
    <section class="subsection report-section"><div class="subsection-head"><h3>Hitting</h3></div>${hittingTable(hitters)}</section>
    <section class="subsection report-section"><div class="subsection-head"><h3>Pitching</h3></div>${pitchingTable(pitchers)}</section>
    <section class="subsection report-section"><div class="subsection-head"><h3>Fielding</h3></div>${fieldingTable(roster)}</section>
    ${sprayOverview(team)}
  </div>`;
  $("team-overview").querySelector("[data-overview-period]").addEventListener("change", event => setOverviewPeriod(event.target.value));
  bindPlayerLinks($("team-overview")); bindSortableTables($("team-overview"));
}

function setOverviewPeriod(period) {
  if (!state.datasets[period]) return;
  state.period = period; state.data = state.datasets[period];
  renderRoster(selectedTeam()); renderTeamOverview(selectedTeam());
}

function identity(player, team) {
  return `<header class="player-identity"><div><button class="team-overview-link no-print" type="button" data-team-overview>← Team Overview</button><h2>${player.jersey ? `<small>#${h(player.jersey)}</small>` : ""}${h(player.name)}</h2>${player.batsThrows ? `<p>B/T ${h(player.batsThrows)}</p>` : ""}</div>${player.headshot ? `<img class="player-headshot" src="${h(player.headshot)}" alt="${h(player.name)} headshot">` : ""}</header>`;
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

function hitterSnapshot(player) {
  const a = player.advancedHitting || {};
  return `<div class="tab-panel active" data-panel="snapshot"><div class="snapshot-layout"><section class="detail-card"><h3>Stats</h3>${originalHittingGrid(player)}</section><section class="detail-card"><h3>Advanced Stats</h3><div class="metric-grid compact">${metric("wOBA",rate(a.wOBA))}${metric("wRAA",signed(a.wRAA,1))}${metric("Offensive WAR",signed(a.offensive_war))}${metric("Defensive WAR",signed(a.defensive_war))}${metric("Range Runs",signed(a.range_runs,1))}${metric("Arm Runs",signed(a.throwing_runs,1))}${metric("WAR",signed(a.position_war))}</div></section></div>${baserunningGrid(player)}<section class="detail-card subsection"><h3>League Percentiles</h3>${percentilePanel(player,"hitting")}</section></div>`;
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

function ttoPanel(player) {
  if (!player.tto.length) return `<div class="tab-panel" data-panel="tto">${empty("No times-through-the-order data is available.")}</div>`;
  const exposureTable = rows => `<div class="table-scroll"><table><thead><tr><th>Meeting</th><th>PA</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th><th>K%</th><th>BB%</th><th>wOBA</th></tr></thead><tbody>${rows.map(row => `<tr><td>${h(row.encounter)}</td><td>${row.PA}</td><td>${rate(row.AVG)}</td><td>${rate(row.OBP)}</td><td>${rate(row.SLG)}</td><td>${rate(row.OPS)}</td><td>${pct(row.K_pct)}</td><td>${pct(row.BB_pct)}</td><td>${rate(row.wOBA)}</td></tr>`).join("")}</tbody></table></div>`;
  return `<div class="tab-panel" data-panel="tto"><div class="subsection-head"><h3>Times Through the Order</h3></div>${exposureTable(player.tto)}<div class="subsection-head exposure-heading"><h3>Previous Games in the Series</h3></div>${exposureTable(player.seriesExposure || [])}</div>`;
}

function tabsForRole(role) {
  return role === "hitting" ? [["snapshot","Snapshot"],["spray","Spray Chart"],["swing","Swing Decisions"],["games","Game Logs"]] : role === "pitching" ? [["snapshot","Snapshot"],["games","Game Logs"],["tto","Times Through Order"]] : [];
}

function playerTabs(role) {
  const tabs = tabsForRole(role);
  return `<div class="player-nav no-print"><button class="team-overview-button" type="button" data-team-overview>← Team Overview</button><label class="period-picker">Stats period<select data-player-period><option value="2026" ${state.period === "2026" ? "selected" : ""}>2026</option><option value="2025" ${state.period === "2025" ? "selected" : ""}>2025</option><option value="2025-2026" ${state.period === "2025-2026" ? "selected" : ""}>2025–26</option></select></label>${tabs.length ? `<div class="player-tabs" role="tablist" aria-label="Player sections">${tabs.map(([key,label]) => `<button class="player-tab" type="button" data-tab="${key}" role="tab" aria-selected="${state.tab === key}">${label}</button>`).join("")}</div>` : ""}</div>`;
}

function setPlayerPeriod(period) {
  const priorTab = state.tab; const priorRole = state.playerRole;
  state.period = period; state.data = state.datasets[period];
  const player = playerByKey(state.player);
  const priorRoleAvailable = priorRole === "hitting" ? player?.hitting : priorRole === "pitching" ? player?.pitching : false;
  state.playerRole = priorRoleAvailable ? priorRole : player?.hitting ? "hitting" : player?.pitching ? "pitching" : "profile";
  state.tab = tabsForRole(state.playerRole).some(([key]) => key === priorTab) ? priorTab : "snapshot";
  renderRoster(selectedTeam()); renderPlayer(player);
}

function renderPlayer(player) {
  const role = state.playerRole;
  if (role === "profile") { $("player-report").innerHTML = `<div class="player-view">${identity(player,selectedTeam())}${playerTabs(role)}${empty(`No ${state.data.meta.periodLabel} hitting or pitching data is available.`)}</div>`; $("player-report").querySelectorAll("[data-team-overview]").forEach(button => button.addEventListener("click", () => showTeamOverview())); $("player-report").querySelector("[data-player-period]").addEventListener("change", event => setPlayerPeriod(event.target.value)); return; }
  const panels = role === "hitting" ? `${hitterSnapshot(player)}${sprayPanel(player)}${swingPanel(player)}${gameLogsPanel(player,role)}` : `${pitcherSnapshot(player)}${gameLogsPanel(player,role)}${ttoPanel(player)}`;
  $("player-report").innerHTML = `<div class="player-view">${identity(player,selectedTeam())}${roleToggle(player)}${playerTabs(role)}${panels}</div>`;
  activateTab();
  $("player-report").querySelectorAll("[data-team-overview]").forEach(button => button.addEventListener("click", () => showTeamOverview()));
  $("player-report").querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => { state.tab = button.dataset.tab; activateTab(); }));
  $("player-report").querySelector("[data-player-period]").addEventListener("change", event => setPlayerPeriod(event.target.value));
  $("player-report").querySelectorAll("[data-player-role]").forEach(button => button.addEventListener("click", () => { state.playerRole = button.dataset.playerRole; state.tab = "snapshot"; renderPlayer(player); }));
}

function activateTab() {
  $("player-report").querySelectorAll("[data-tab]").forEach(button => button.setAttribute("aria-selected", String(button.dataset.tab === state.tab)));
  $("player-report").querySelectorAll("[data-panel]").forEach(panel => panel.classList.toggle("active", panel.dataset.panel === state.tab));
}

function selectPlayer(key, updateHash = true) {
  const team = selectedTeam(); if (!team.roster.includes(key)) return;
  const player = playerByKey(key); state.player = key; state.playerRole = player.hitting ? "hitting" : player.pitching ? "pitching" : "profile"; state.tab = "snapshot";
  $("team-overview").hidden = true; $("player-report").hidden = false; renderRoster(team); renderPlayer(player);
  document.title = `${player.name} · ${team.short} · AUSL Team Scout`; if (updateHash) setHash();
  $("player-report").scrollIntoView({ behavior: "smooth", block: "start" });
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
  document.title = `${team.name} · AUSL Team Scout`;
}

function bindStaticEvents() {
  $("back-button").addEventListener("click", showLanding);
  $("opponent-select").addEventListener("change", event => selectTeam(event.target.value));
  $("player-search").addEventListener("input", event => { state.query = event.target.value; renderRoster(selectedTeam()); });
  document.querySelectorAll("[data-role]").forEach(button => button.addEventListener("click", () => { state.rosterRole = button.dataset.role; document.querySelectorAll("[data-role]").forEach(item => item.setAttribute("aria-pressed", String(item === button))); renderRoster(selectedTeam()); }));
}

function hydrateRoute() {
  const params = new URLSearchParams(location.hash.slice(1)); const team = params.get("team"); const player = params.get("player");
  if (team && state.data.teams.some(item => item.key === team)) { selectTeam(team,false); if (player && selectedTeam().roster.includes(player)) selectPlayer(player,false); }
}

async function start() {
  try {
    const entries = [["2026","data/scouting-data.json"],["2025","data/scouting-data-2025.json"],["2025-2026","data/scouting-data-2025-2026.json"]];
    const payloads = await Promise.all(entries.map(async ([key,url]) => { const response = await fetch(url,{cache:"no-store"}); if (!response.ok) throw new Error(`Data request failed (${response.status})`); return [key,await response.json()]; }));
    state.datasets = Object.fromEntries(payloads); state.data = state.datasets["2026"]; $("data-stamp").textContent = `2026 · ${state.data.meta.games} games`;
    $("opponent-select").innerHTML = state.data.teams.map(team => `<option value="${team.key}">${h(team.name)}</option>`).join("");
    renderLanding(); bindStaticEvents(); hydrateRoute(); $("loading").hidden = true;
  } catch (error) { $("loading").innerHTML = `<div><strong>Scouting data could not be loaded.</strong><br><small>${h(error.message)}</small></div>`; }
}

start();

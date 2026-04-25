/**
 * Tournament detail view — shows run metadata, per-agent stats,
 * head-to-head matrix, list of matches with replay links.
 */

import { api, MatchResult } from "../api";
import { installHeaderNav } from "../components/header-nav";
import { navigate } from "../router";
import { escapeHtml } from "../utils/escape";

let pollInterval: number | null = null;

interface AgentStats {
  agent_id: string;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  crashes: number;
  total_turns: number;
  total_duration: number;
  mu?: number;
  sigma?: number;
}

interface H2HCell {
  wins: number;
  losses: number;
  draws: number;
}

export async function renderTournamentDetail(
  root: HTMLElement,
  runId: string,
): Promise<void> {
  root.innerHTML = `
    <main class="dashboard">
      <section>
        <div class="section-head" style="margin-bottom: 16px;">
          <button id="back" class="scrape-btn cancel">← All tournaments</button>
          <button id="delete-tournament" class="scrape-btn cancel" style="margin-left: auto; color: var(--error); border-color: var(--error);">Delete tournament</button>
        </div>
        <h2>Tournament ${runId}</h2>
        <div id="td-body">
          <div class="loading">Loading…</div>
        </div>
      </section>
    </main>
  `;
  installHeaderNav(root, "tournaments");

  document.getElementById("back")!.addEventListener("click", () => {
    navigate({ view: "tournaments" });
  });

  document.getElementById("delete-tournament")!.addEventListener("click", async () => {
    if (!confirm(`Delete tournament ${runId} and all its replays?`)) return;
    try {
      await api.deleteRun(runId);
      navigate({ view: "tournaments" });
    } catch (e) {
      alert(`Delete failed: ${(e as Error).message}`);
    }
  });

  let details: any;
  try {
    details = await api.getRun(runId);
  } catch (e) {
    document.getElementById("td-body")!.innerHTML =
      `<div class="loading">Error: ${(e as Error).message}</div>`;
    return;
  }

  const run = details.run || {};
  const config = details.config || {};
  const results = details.results || { matches: [] };
  const trueskillSnap = details.trueskill || {};
  const matches: MatchResult[] = results.matches || [];

  // ----- Per-agent stats -----
  const stats = new Map<string, AgentStats>();
  const agents: string[] = config.agents || [];
  for (const a of agents) {
    stats.set(a, {
      agent_id: a,
      games: 0, wins: 0, losses: 0, draws: 0, crashes: 0,
      total_turns: 0, total_duration: 0,
    });
  }

  const h2h = new Map<string, Map<string, H2HCell>>();
  function h2hCell(a: string, b: string): H2HCell {
    if (!h2h.has(a)) h2h.set(a, new Map());
    const row = h2h.get(a)!;
    if (!row.has(b)) row.set(b, { wins: 0, losses: 0, draws: 0 });
    return row.get(b)!;
  }

  let failedMatches = 0;
  for (const m of matches) {
    for (const aid of m.agent_ids) {
      if (!stats.has(aid)) {
        stats.set(aid, {
          agent_id: aid,
          games: 0, wins: 0, losses: 0, draws: 0, crashes: 0,
          total_turns: 0, total_duration: 0,
        });
      }
      const s = stats.get(aid)!;
      s.games += 1;
      s.total_turns += m.turns || 0;
      s.total_duration += m.duration_s || 0;
      if (m.winner === aid) s.wins += 1;
      else if (m.winner === null || m.winner === undefined) s.draws += 1;
      else s.losses += 1;
      // "crashes" column is for agent malfunctions (crashed / timeout /
      // invalid_action), NOT for engine-declared draws. `status="draw"` is
      // a clean match outcome — previously it inflated both this counter
      // and `failedMatches`, making peaceful games look like failures.
      if (m.status && m.status !== "ok" && m.status !== "draw") s.crashes += 1;
    }
    if (m.status && m.status !== "ok" && m.status !== "draw") failedMatches += 1;
    if (m.agent_ids.length === 2) {
      const [a, b] = m.agent_ids;
      if (m.winner === a) {
        h2hCell(a, b).wins += 1;
        h2hCell(b, a).losses += 1;
      } else if (m.winner === b) {
        h2hCell(b, a).wins += 1;
        h2hCell(a, b).losses += 1;
      } else {
        h2hCell(a, b).draws += 1;
        h2hCell(b, a).draws += 1;
      }
    }
  }

  // Merge TrueSkill snapshot — file shape: { "2p": { agent_id: { mu, sigma, games_played } }, ... }
  const format = (config.format || run.format || "2p") as "2p" | "4p";
  const skillTable = (trueskillSnap && trueskillSnap[format]) || {};
  for (const [aid, s] of stats) {
    const ts = skillTable[aid];
    if (ts) { s.mu = ts.mu; s.sigma = ts.sigma; }
  }

  // Sort agents by wins then mu
  const ranked = Array.from(stats.values()).sort((a, b) => {
    if (b.wins !== a.wins) return b.wins - a.wins;
    return (b.mu ?? 0) - (a.mu ?? 0);
  });

  const totalTurns = matches.reduce((sum, m) => sum + (m.turns || 0), 0);
  const totalDuration = matches.reduce((sum, m) => sum + (m.duration_s || 0), 0);
  const avgTurns = matches.length ? totalTurns / matches.length : 0;
  const avgDuration = matches.length ? totalDuration / matches.length : 0;

  // ----- Render -----
  const body = document.getElementById("td-body")!;
  body.innerHTML = `
    <div class="td-meta">
      <div class="td-meta-item"><span class="td-label">Status</span><span class="status-${run.status}">${run.status || "?"}</span></div>
      <div class="td-meta-item"><span class="td-label">Mode</span><span>${config.mode || run.mode || "?"}</span></div>
      <div class="td-meta-item"><span class="td-label">Format</span><span>${format}</span></div>
      <div class="td-meta-item"><span class="td-label">Games/pair</span><span>${config.games_per_pair ?? "?"}</span></div>
      <div class="td-meta-item"><span class="td-label">Seed</span><span>${config.seed_base ?? "?"}</span></div>
      <div class="td-meta-item"><span class="td-label">Agents</span><span>${agents.length}</span></div>
      <div class="td-meta-item"><span class="td-label">Matches</span><span>${matches.length}</span></div>
      <div class="td-meta-item"><span class="td-label">Failed</span><span>${failedMatches}</span></div>
      <div class="td-meta-item"><span class="td-label">Avg turns</span><span>${avgTurns.toFixed(0)}</span></div>
      <div class="td-meta-item"><span class="td-label">Avg duration</span><span>${avgDuration.toFixed(2)}s</span></div>
      <div class="td-meta-item"><span class="td-label">Total time</span><span>${totalDuration.toFixed(1)}s</span></div>
      <div class="td-meta-item"><span class="td-label">Started</span><span>${formatDate(run.started_at)}</span></div>
    </div>

    <h2 style="margin-top: 28px;">Standings</h2>
    <div class="td-standings">
      <table class="ratings td-standings-table">
        <thead>
          <tr>
            <th>#</th><th>Agent</th><th>Games</th><th>W</th><th>L</th><th>D</th><th>Win %</th><th>μ</th><th>σ</th><th>Crashes</th>
          </tr>
        </thead>
        <tbody>
          ${ranked.map((s, i) => renderStandingRow(i + 1, s)).join("")}
        </tbody>
      </table>
    </div>

    ${agents.length >= 2 && agents.length <= 12
      ? `<h2 style="margin-top: 28px;">Head-to-head</h2>${renderH2HMatrix(agents, h2h)}`
      : ``}

    <h2 style="margin-top: 28px;">Matches (${matches.length})</h2>
    <div class="td-match-list">
      ${matches.map((m) => renderMatchRow(m, runId)).join("")}
    </div>
  `;

  body.querySelectorAll<HTMLElement>(".td-match-row").forEach((row) => {
    row.addEventListener("click", () => {
      const matchId = row.dataset.matchId;
      if (!matchId) return;
      // Route through Quick Match so the user keeps the sidebar (Match /
      // Planet / Fleet cards + live score). The bare #/replay/... view is
      // chromeless and loses that context. Mirrors the replays-list handoff.
      sessionStorage.setItem(
        "ow-pending-replay",
        JSON.stringify({ kind: "local", runId, matchId, ts: Date.now() }),
      );
      navigate({ view: "quick-match" });
    });
  });

  // Poll while tournament is live so stats fill in without F5. Self-gc:
  // clear when the view is unmounted or the run reaches a terminal state.
  if (pollInterval !== null) window.clearInterval(pollInterval);
  pollInterval = window.setInterval(async () => {
    if (!document.getElementById("td-body")) {
      if (pollInterval !== null) window.clearInterval(pollInterval);
      pollInterval = null;
      return;
    }
    if (document.hidden) return;
    try {
      const fresh = await api.getRunProgress(runId);
      if (fresh.status !== "running") {
        if (pollInterval !== null) window.clearInterval(pollInterval);
        pollInterval = null;
        // One last full reload to capture final standings.
        if (run.status === "running") void renderTournamentDetail(root, runId);
        return;
      }
      // Tournament still live — pull full data (standings + matches).
      void renderTournamentDetail(root, runId);
    } catch {
      // Transient network error — try again next tick.
    }
  }, 3000);
}

function renderStandingRow(rank: number, s: AgentStats): string {
  const winPct = s.games > 0 ? ((s.wins / s.games) * 100).toFixed(0) : "—";
  const mu = s.mu !== undefined ? s.mu.toFixed(0) : "—";
  const sigma = s.sigma !== undefined ? s.sigma.toFixed(0) : "—";
  return `
    <tr>
      <td>${rank}</td>
      <td class="agent-id">${escapeHtml(s.agent_id)}</td>
      <td>${s.games}</td>
      <td class="td-wins">${s.wins}</td>
      <td class="td-losses">${s.losses}</td>
      <td>${s.draws}</td>
      <td>${winPct}${s.games > 0 ? "%" : ""}</td>
      <td>${mu}</td>
      <td>${sigma}</td>
      <td>${s.crashes || ""}</td>
    </tr>
  `;
}

function renderH2HMatrix(
  agents: string[],
  h2h: Map<string, Map<string, H2HCell>>,
): string {
  // Short labels for header
  const short = (id: string) => {
    const parts = id.split("/");
    return parts[parts.length - 1].slice(0, 12);
  };
  const rows = agents.map((a) => {
    const cells = agents.map((b) => {
      if (a === b) return `<td class="td-h2h-self">—</td>`;
      const c = h2h.get(a)?.get(b);
      if (!c || c.wins + c.losses + c.draws === 0) {
        return `<td class="td-h2h-empty">·</td>`;
      }
      const total = c.wins + c.losses + c.draws;
      const winPct = c.wins / total;
      const shade = winPct > 0.5
        ? `background: rgba(94, 237, 159, ${0.1 + (winPct - 0.5) * 0.6})`
        : `background: rgba(255, 138, 138, ${0.1 + (0.5 - winPct) * 0.6})`;
      return `<td class="td-h2h" style="${shade}"><span class="td-h2h-main">${c.wins}–${c.losses}</span>${c.draws > 0 ? `<span class="td-h2h-draw">${c.draws}d</span>` : ""}</td>`;
    });
    return `<tr><th class="td-h2h-row-head">${escapeHtml(short(a))}</th>${cells.join("")}</tr>`;
  });
  const header = `<tr><th></th>${agents.map((a) => `<th class="td-h2h-col-head">${escapeHtml(short(a))}</th>`).join("")}</tr>`;
  return `<div class="td-h2h-wrap"><table class="td-h2h-table">${header}${rows.join("")}</table></div>`;
}

function renderMatchRow(m: MatchResult, _runId: string): string {
  const winner = m.winner ? escapeHtml(m.winner) : "draw";
  const safeMatchId = escapeHtml(m.match_id);
  return `
    <div class="td-match-row" data-match-id="${safeMatchId}">
      <span class="td-match-id">${safeMatchId}</span>
      <span class="td-match-agents">${m.agent_ids.map(escapeHtml).join(" vs ")}</span>
      <span class="td-match-winner">${winner}</span>
      <span class="td-match-meta">${m.turns}t · ${(m.duration_s || 0).toFixed(1)}s</span>
      <span class="td-match-status status-${m.status === "ok" ? "completed" : "aborted"}">${escapeHtml(m.status)}</span>
    </div>
  `;
}

function formatDate(iso: string | undefined): string {
  if (!iso) return "?";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

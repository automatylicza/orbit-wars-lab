import { api, Rating } from "../api";
import { navigate } from "../router";

export type RatingsFormat = "2p" | "4p" | "all";

export async function mountRatingsTable(
  el: HTMLElement,
  format: RatingsFormat = "2p",
): Promise<void> {
  if (format === "all") {
    await renderCombined(el);
    return;
  }
  await renderSingle(el, format);
}

async function renderSingle(
  el: HTMLElement,
  format: "2p" | "4p",
): Promise<void> {
  const ratings = await api.getRatings(format);
  el.innerHTML = `
    <table class="ratings">
      <thead>
        <tr>
          <th>#</th><th>Agent</th><th>μ</th><th>σ</th><th>N</th>
        </tr>
      </thead>
      <tbody>
        ${ratings
          .map(
            (r: Rating) => `
          <tr data-agent-id="${r.agent_id}">
            <td>${r.rank}</td>
            <td class="agent-id">${r.agent_id}</td>
            <td>${r.mu.toFixed(0)}</td>
            <td>${r.sigma.toFixed(0)}</td>
            <td>${r.games_played}</td>
          </tr>
        `,
          )
          .join("")}
      </tbody>
    </table>
  `;
  wireRowClicks(el);
}

async function renderCombined(el: HTMLElement): Promise<void> {
  const [r2p, r4p] = await Promise.all([
    api.getRatings("2p"),
    api.getRatings("4p"),
  ]);

  interface Row {
    agentId: string;
    mu2p?: number;
    n2p?: number;
    rank2p?: number;
    mu4p?: number;
    n4p?: number;
    rank4p?: number;
    avgRank: number;
  }

  const map = new Map<string, Row>();
  const ensure = (aid: string): Row => {
    let r = map.get(aid);
    if (!r) {
      r = { agentId: aid, avgRank: 0 };
      map.set(aid, r);
    }
    return r;
  };

  r2p.forEach((r) => {
    const row = ensure(r.agent_id);
    row.mu2p = r.mu;
    row.n2p = r.games_played;
    row.rank2p = r.rank;
  });
  r4p.forEach((r) => {
    const row = ensure(r.agent_id);
    row.mu4p = r.mu;
    row.n4p = r.games_played;
    row.rank4p = r.rank;
  });

  const rows = Array.from(map.values()).map((r) => {
    const ranks = [r.rank2p, r.rank4p].filter(
      (x): x is number => x !== undefined,
    );
    r.avgRank = ranks.length > 0 ? ranks.reduce((s, v) => s + v, 0) / ranks.length : Infinity;
    return r;
  });
  rows.sort((a, b) => a.avgRank - b.avgRank);

  const fmt = (v: number | undefined) => (v === undefined ? "—" : v.toFixed(0));
  const fmtAvg = (v: number) =>
    Number.isFinite(v) ? (Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1)) : "—";

  el.innerHTML = `
    <table class="ratings ratings-combined">
      <thead>
        <tr>
          <th rowspan="2">#</th>
          <th rowspan="2">Agent</th>
          <th colspan="2" class="group-2p">2p</th>
          <th colspan="2" class="group-4p">4p</th>
          <th rowspan="2" title="Średnia pozycji z obu formatów (niższa = lepiej)">avg rank</th>
        </tr>
        <tr>
          <th class="group-2p">μ</th>
          <th class="group-2p">N</th>
          <th class="group-4p">μ</th>
          <th class="group-4p">N</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (r, i) => `
          <tr data-agent-id="${r.agentId}">
            <td>${i + 1}</td>
            <td class="agent-id">${r.agentId}</td>
            <td>${fmt(r.mu2p)}</td>
            <td>${r.n2p ?? "—"}</td>
            <td>${fmt(r.mu4p)}</td>
            <td>${r.n4p ?? "—"}</td>
            <td>${fmtAvg(r.avgRank)}</td>
          </tr>
        `,
          )
          .join("")}
      </tbody>
    </table>
  `;
  wireRowClicks(el);
}

function wireRowClicks(el: HTMLElement): void {
  el.querySelectorAll<HTMLTableRowElement>("tbody tr").forEach((row) => {
    row.addEventListener("click", () => {
      const id = row.getAttribute("data-agent-id");
      if (id) navigate({ view: "agent", agentId: id });
    });
  });
}

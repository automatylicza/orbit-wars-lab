/**
 * Tournaments view — create a new tournament + list historical ones.
 * Create panel: multi-select agents (bucket filter + search), config
 * (games_per_pair, mode, format), Start button.
 */

import { api, AgentInfo, RunSummary } from "../api";
import { installHeaderNav } from "../components/header-nav";
import { navigate } from "../router";

let pollInterval: number | null = null;

export async function renderTournaments(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <main class="dashboard">
      <section>
        <div class="section-head">
          <h2>Create Tournament</h2>
        </div>
        <div id="create-panel" class="scrape-panel">
          <div class="create-grid">
            <div class="create-agents">
              <div class="create-agents-head">
                <input id="create-search" class="picker-search" placeholder="search agents…">
                <div class="picker-tags">
                  <button class="picker-pill on" data-bucket="all">all</button>
                  <button class="picker-pill" data-bucket="baselines">baselines</button>
                  <button class="picker-pill" data-bucket="external">external</button>
                  <button class="picker-pill" data-bucket="mine">mine</button>
                </div>
                <div class="create-count"><span id="create-count-num">0</span> selected</div>
              </div>
              <ul id="create-agent-list" class="create-agent-list"></ul>
            </div>
            <div class="create-config">
              <label>
                <span>Shape</span>
                <div class="seg-group" id="cfg-shape">
                  <button class="config-pill on" data-v="round-robin">round-robin</button>
                  <button class="config-pill" data-v="gauntlet">gauntlet</button>
                </div>
              </label>
              <label id="cfg-challenger-wrap" hidden>
                <span>Challenger</span>
                <select id="cfg-challenger" style="min-width: 200px;"></select>
              </label>
              <label>
                <span>Games per pair</span>
                <select id="cfg-games">
                  <option value="1">1</option>
                  <option value="3" selected>3</option>
                  <option value="5">5</option>
                  <option value="10">10</option>
                </select>
              </label>
              <label>
                <span>Mode</span>
                <div class="seg-group" id="cfg-mode">
                  <button class="config-pill on" data-v="fast">fast</button>
                  <button class="config-pill" data-v="faithful">faithful</button>
                </div>
              </label>
              <label>
                <span>Format</span>
                <div class="seg-group" id="cfg-format">
                  <button class="config-pill on" data-v="2p">2p</button>
                  <button class="config-pill" data-v="4p">4p</button>
                </div>
              </label>
              <label>
                <span>Seed</span>
                <input id="cfg-seed" type="number" value="42" style="width: 100px;">
              </label>
              <div id="cfg-total-matches" class="cfg-total-matches"></div>
              <div class="create-actions">
                <div id="create-status" class="scrape-status" hidden></div>
                <button class="scrape-btn go" id="create-start">Start tournament</button>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section>
        <h2>Recent tournaments</h2>
        <div id="runs-list"></div>
      </section>
    </main>
  `;
  installHeaderNav(root, "tournaments");

  // =========================================================
  // Agent selection state
  // =========================================================
  const selected = new Set<string>();
  let agents: AgentInfo[] = [];
  let bucketFilter: "all" | "baselines" | "external" | "mine" = "all";
  let searchTerm = "";

  async function loadAgents() {
    agents = await api.listAgents();
    renderAgentList();
  }

  function renderAgentList() {
    const listEl = document.getElementById("create-agent-list")!;
    const filtered = agents.filter((a) => {
      if (a.disabled) return false;
      if (bucketFilter !== "all" && a.bucket !== bucketFilter) return false;
      if (searchTerm) {
        const t = searchTerm.toLowerCase();
        if (!a.id.toLowerCase().includes(t) && !a.name.toLowerCase().includes(t))
          return false;
      }
      return true;
    });
    if (filtered.length === 0) {
      listEl.innerHTML = `<li class="picker-empty">No agents match this filter.</li>`;
    } else {
      listEl.innerHTML = filtered
        .map(
          (a) => `
          <li class="create-agent ${selected.has(a.id) ? "picked" : ""}" data-id="${a.id}">
            <span class="create-check">${selected.has(a.id) ? "✓" : ""}</span>
            <span class="agent-name">${a.name}</span>
            <span class="agent-bucket">${a.bucket}</span>
          </li>
        `,
        )
        .join("");
    }
    listEl.querySelectorAll<HTMLElement>(".create-agent").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.id!;
        if (selected.has(id)) selected.delete(id);
        else selected.add(id);
        updateCount();
        renderAgentList();
      });
    });
  }

  function updateCount() {
    document.getElementById("create-count-num")!.textContent = String(selected.size);
    refreshChallengerDropdown();
    updateTotalMatches();
  }

  document.getElementById("create-search")!.addEventListener("input", (e) => {
    searchTerm = (e.target as HTMLInputElement).value;
    renderAgentList();
  });

  root.querySelectorAll<HTMLButtonElement>("[data-bucket]").forEach((btn) => {
    btn.addEventListener("click", () => {
      bucketFilter = btn.dataset.bucket as typeof bucketFilter;
      root.querySelectorAll<HTMLButtonElement>("[data-bucket]").forEach((b) =>
        b.classList.toggle("on", b === btn),
      );
      renderAgentList();
    });
  });

  // Config seg-groups
  function wireSegGroup(groupId: string): () => string {
    const group = document.getElementById(groupId)!;
    group.querySelectorAll<HTMLButtonElement>(".config-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        group.querySelectorAll<HTMLButtonElement>(".config-pill").forEach((b) =>
          b.classList.toggle("on", b === btn),
        );
      });
    });
    return () =>
      group.querySelector<HTMLButtonElement>(".config-pill.on")?.dataset.v ?? "";
  }
  const getMode = wireSegGroup("cfg-mode");
  const getFormat = wireSegGroup("cfg-format");
  const getShape = wireSegGroup("cfg-shape");

  const challengerWrap = document.getElementById("cfg-challenger-wrap")!;
  const challengerSel = document.getElementById("cfg-challenger") as HTMLSelectElement;
  const totalMatchesEl = document.getElementById("cfg-total-matches")!;

  function getGames(): number {
    return parseInt((document.getElementById("cfg-games") as HTMLSelectElement).value, 10);
  }

  function refreshChallengerDropdown() {
    const picked = Array.from(selected);
    const prev = challengerSel.value;
    if (picked.length === 0) {
      challengerSel.innerHTML = `<option value="">(pick agents first)</option>`;
      return;
    }
    const options = picked.map((id) => {
      const a = agents.find((x) => x.id === id);
      const label = a ? `${a.name} (${id})` : id;
      return `<option value="${id}">${label}</option>`;
    }).join("");
    challengerSel.innerHTML = options;
    if (picked.includes(prev)) challengerSel.value = prev;
  }

  function updateTotalMatches() {
    const shape = getShape();
    const format = getFormat();
    const n = selected.size;
    const K = getGames();
    let pairs = 0;
    let note = "";
    if (shape === "gauntlet") {
      const opponents = Math.max(0, n - 1); // minus challenger
      if (format === "2p") {
        pairs = opponents;
      } else {
        // C(opponents, 3): challenger + 3 opponents per match
        if (opponents >= 3) {
          pairs = (opponents * (opponents - 1) * (opponents - 2)) / 6;
        }
      }
      if (n < 2) note = "select ≥2 agents + choose challenger";
    } else {
      if (format === "2p") {
        pairs = n < 2 ? 0 : (n * (n - 1)) / 2;
      } else {
        pairs = n < 4 ? 0 : (n * (n - 1) * (n - 2) * (n - 3)) / 24;
        if (n < 4) note = "4p needs ≥4 agents";
      }
    }
    const total = pairs * K;
    if (note) {
      totalMatchesEl.textContent = note;
    } else {
      totalMatchesEl.textContent = `${pairs} pair${pairs === 1 ? "" : "s"} × ${K} = ${total} games`;
    }
  }

  function onShapeChange() {
    const shape = getShape();
    challengerWrap.hidden = shape !== "gauntlet";
    if (shape === "gauntlet") refreshChallengerDropdown();
    updateTotalMatches();
  }

  // Wire shape pill clicks to show/hide challenger + recompute totals.
  document.getElementById("cfg-shape")!
    .querySelectorAll<HTMLButtonElement>(".config-pill")
    .forEach((btn) => btn.addEventListener("click", () => {
      // wireSegGroup already handled the .on toggle; we just react after.
      setTimeout(onShapeChange, 0);
    }));
  document.getElementById("cfg-format")!
    .querySelectorAll<HTMLButtonElement>(".config-pill")
    .forEach((btn) => btn.addEventListener("click", () => setTimeout(updateTotalMatches, 0)));
  document.getElementById("cfg-games")!
    .addEventListener("change", updateTotalMatches);

  // Start tournament
  document.getElementById("create-start")!.addEventListener("click", async () => {
    const statusEl = document.getElementById("create-status")!;
    const shape = getShape();
    if (selected.size < 2) {
      statusEl.hidden = false;
      statusEl.textContent = "Select at least 2 agents.";
      return;
    }
    let challengerId: string | null = null;
    if (shape === "gauntlet") {
      challengerId = challengerSel.value || null;
      if (!challengerId || !selected.has(challengerId)) {
        statusEl.hidden = false;
        statusEl.textContent = "Gauntlet: pick a challenger from the dropdown.";
        return;
      }
    }
    const games = parseInt(
      (document.getElementById("cfg-games") as HTMLSelectElement).value,
      10,
    );
    const mode = getMode();
    const format = getFormat();
    const seed = parseInt(
      (document.getElementById("cfg-seed") as HTMLInputElement).value,
      10,
    );
    statusEl.hidden = false;
    statusEl.textContent = "Starting…";
    try {
      const resp = await api.startTournament({
        agents: Array.from(selected),
        games_per_pair: games,
        mode,
        format,
        parallel: 1,
        seed_base: isNaN(seed) ? 42 : seed,
        is_quick_match: false,
        shape: shape as "round-robin" | "gauntlet",
        challenger_id: challengerId,
      });
      statusEl.textContent = `Running: ${resp.run_id}`;
      setTimeout(() => {
        statusEl.hidden = true;
      }, 1200);
      await loadRuns();
    } catch (e: any) {
      const err = e?.message || "unknown error";
      if (e?.status === 409) {
        statusEl.textContent = "Another tournament is already running.";
      } else {
        statusEl.textContent = `Error: ${err}`;
      }
    }
  });

  // =========================================================
  // Runs list
  // =========================================================
  const listEl = document.getElementById("runs-list")!;

  async function loadRuns() {
    const runs = await api.listRuns({ excludeQuickMatch: true });
    if (runs.length === 0) {
      listEl.innerHTML = `<div class="loading">No tournaments yet. Click "New tournament" above.</div>`;
      return;
    }
    listEl.innerHTML = `
      <ul class="runs">
        ${runs
          .map(
            (r: RunSummary) => `
          <li data-run-id="${r.id}">
            <span class="run-id">${r.id}</span>
            <span class="run-meta">${r.mode} · ${r.format} · ${r.matches_done}/${r.total_matches}</span>
            <span class="run-status status-${r.status}">${r.status}</span>
            <button class="replay-delete" data-run-id="${r.id}" title="Delete tournament">×</button>
          </li>
        `,
          )
          .join("")}
      </ul>
    `;
    listEl.querySelectorAll<HTMLLIElement>("li").forEach((li) => {
      li.addEventListener("click", (ev) => {
        if ((ev.target as HTMLElement).closest(".replay-delete")) return;
        const runId = li.getAttribute("data-run-id");
        if (!runId) return;
        navigate({ view: "tournament-detail", runId });
      });
    });
    listEl.querySelectorAll<HTMLButtonElement>(".replay-delete").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const runId = btn.dataset.runId!;
        if (!confirm(`Delete tournament ${runId} and all its replays?`)) return;
        try {
          await api.deleteRun(runId);
          await loadRuns();
        } catch (e) {
          alert(`Delete failed: ${(e as Error).message}`);
        }
      });
    });
  }

  await loadAgents();
  await loadRuns();
  onShapeChange(); // initial: hide challenger + compute totals

  if (pollInterval !== null) window.clearInterval(pollInterval);
  pollInterval = window.setInterval(() => {
    if (document.hidden) return;
    void loadRuns();
  }, 5000);
}

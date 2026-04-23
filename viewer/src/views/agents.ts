/**
 * Agents view — browse all agents in the zoo (baselines / external / mine),
 * filter, search, click for details, delete from UI.
 */

import { api, AgentInfo } from "../api";
import { installHeaderNav } from "../components/header-nav";
import { navigate } from "../router";

let pollInterval: number | null = null;

export async function renderAgents(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <main class="dashboard">
      <section>
        <div class="section-head">
          <h2>Agents</h2>
          <span class="td-label" id="agents-count" style="margin-left: auto;"></span>
        </div>
        <div class="replays-toolbar">
          <div class="source-pills">
            <button class="source-pill on" data-bucket="all">All</button>
            <button class="source-pill" data-bucket="baselines">Baselines</button>
            <button class="source-pill" data-bucket="external">External</button>
            <button class="source-pill" data-bucket="mine">Mine</button>
          </div>
          <input id="agents-search" class="picker-search" placeholder="search…" style="flex: 1; max-width: 300px;">
        </div>
        <div id="agents-list" class="replays-list"></div>
      </section>
    </main>
  `;
  installHeaderNav(root, "agents");

  let bucketFilter: "all" | "baselines" | "external" | "mine" = "all";
  let searchTerm = "";

  async function loadList() {
    const listEl = document.getElementById("agents-list")!;
    listEl.innerHTML = `<div class="loading">Loading…</div>`;
    try {
      const agents = await api.listAgents();
      renderList(agents);
    } catch (e) {
      listEl.innerHTML = `<div class="loading">Error: ${(e as Error).message}</div>`;
    }
  }

  function renderList(agents: AgentInfo[]) {
    const listEl = document.getElementById("agents-list")!;
    const filtered = agents.filter((a) => {
      if (bucketFilter !== "all" && a.bucket !== bucketFilter) return false;
      if (searchTerm) {
        const t = searchTerm.toLowerCase();
        if (!a.id.toLowerCase().includes(t) && !a.name.toLowerCase().includes(t))
          return false;
      }
      return true;
    });
    document.getElementById("agents-count")!.textContent =
      `${filtered.length} / ${agents.length}`;
    if (filtered.length === 0) {
      listEl.innerHTML = `<div class="loading">No agents match this filter.</div>`;
      return;
    }
    listEl.innerHTML = filtered
      .map((a) => {
        const tags = (a.tags || []).slice(0, 4).join(" · ");
        const desc = a.description ? a.description.slice(0, 160) : "";
        const errBadge = a.last_error
          ? `<span class="replay-source" style="color: var(--error); background: rgba(255,138,138,0.08);">error</span>`
          : "";
        const disabledBadge = a.disabled
          ? `<span class="replay-source" style="color: var(--warning); background: rgba(255,184,74,0.08);">disabled</span>`
          : "";
        return `
          <div class="replay-item" data-id="${a.id}">
            <div class="replay-meta-row">
              <span class="replay-source ${a.bucket}">${a.bucket}</span>
              ${errBadge}${disabledBadge}
              <span class="replay-title">${a.name}</span>
              <span class="replay-winner">${a.author ? "by <strong>" + a.author + "</strong>" : ""}</span>
            </div>
            <div class="replay-meta-sub">
              ${a.id}${tags ? " · " + tags : ""}${desc ? " · " + desc : ""}
            </div>
            <button class="replay-delete" data-id="${a.id}" title="Delete agent">×</button>
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll<HTMLElement>(".replay-item").forEach((row) => {
      row.addEventListener("click", (ev) => {
        if ((ev.target as HTMLElement).closest(".replay-delete")) return;
        const id = row.dataset.id!;
        navigate({ view: "agent", agentId: id });
      });
    });
    listEl.querySelectorAll<HTMLButtonElement>(".replay-delete").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = btn.dataset.id!;
        if (!confirm(`Delete agent "${id}"?\n\nRemoves the folder from disk. Ratings + replay history kept.`)) return;
        try {
          await api.deleteAgent(id);
          await loadList();
        } catch (e) {
          alert(`Delete failed: ${(e as Error).message}`);
        }
      });
    });
  }

  root.querySelectorAll<HTMLButtonElement>("[data-bucket]").forEach((btn) => {
    btn.addEventListener("click", () => {
      bucketFilter = btn.dataset.bucket as typeof bucketFilter;
      root.querySelectorAll<HTMLButtonElement>("[data-bucket]").forEach((b) =>
        b.classList.toggle("on", b === btn),
      );
      void loadList();
    });
  });

  (document.getElementById("agents-search") as HTMLInputElement).addEventListener(
    "input",
    (e) => {
      searchTerm = (e.target as HTMLInputElement).value;
      void loadList();
    },
  );

  await loadList();

  if (pollInterval !== null) window.clearInterval(pollInterval);
  pollInterval = window.setInterval(() => {
    if (document.hidden) return;
    void loadList();
  }, 10000);
}

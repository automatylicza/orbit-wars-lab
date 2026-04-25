/**
 * Replays view — unified list of local tournament matches + Kaggle-scraped
 * episodes, with a "Pobierz z Kaggle" dialog to fetch more episodes for a
 * given submission_id.
 */

import { installHeaderNav } from "../components/header-nav";
import { navigate } from "../router";
import { api } from "../api";
import { escapeHtml } from "../utils/escape";

interface LocalReplay {
  source: "local";
  run_id: string;
  match_id: string;
  agent_ids: string[];
  winner: string | null;
  turns: number;
  duration_s: number;
  status: string;
  started_at?: string;
}

interface KaggleReplay {
  source: "kaggle";
  submission_id: number;
  episode_id: number;
  path: string;
  agents?: Array<{ name?: string; submissionId?: number }>;
  team_names?: string[];
  winner?: string | null;
  type?: string;
  endTime?: string;
}

type Replay = LocalReplay | KaggleReplay;

type Source = "all" | "local" | "kaggle";

let pollInterval: number | null = null;

export async function renderReplays(
  root: HTMLElement,
  subFilter?: string,
): Promise<void> {
  root.innerHTML = `
    <main class="dashboard replays-view">
      <section>
        <div class="replays-toolbar">
          <div class="source-pills">
            <button class="source-pill on" data-source="all">All</button>
            <button class="source-pill" data-source="local">Local</button>
            <button class="source-pill" data-source="kaggle">Kaggle LB</button>
          </div>
          <label class="replays-sort">
            Submission
            <select id="replays-sub-select">
              <option value="">All submissions</option>
            </select>
          </label>
          <label class="replays-sort">
            Sort
            <select id="replays-sort-select">
              <option value="newest" selected>Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="turns-desc">Turns: most first</option>
              <option value="turns-asc">Turns: least first</option>
            </select>
          </label>
        </div>
        <div id="scrape-panel" class="scrape-panel">
          <div class="scrape-row">
            <label>Kaggle replay URL
              <input type="text" id="scrape-url"
                     placeholder="https://www.kaggle.com/.../episodes/70123456?submissionId=51799179">
            </label>
            <div class="scrape-actions">
              <button class="scrape-btn go" id="scrape-go">Import</button>
            </div>
          </div>
          <div class="scrape-hint">
            Paste a Kaggle replay URL — either an episode page or a leaderboard link containing <code>?episodeId=&lt;id&gt;</code>.
            The <code>submissionId</code> in the URL flags which bot you care about; we fetch that single episode.
          </div>
          <div id="scrape-status" class="scrape-status" hidden></div>
        </div>
        <div id="replays-list" class="replays-list"></div>
      </section>
    </main>
  `;
  installHeaderNav(root, "replays");

  // Populate the submission filter dropdown from the user's Kaggle list.
  // Preserves URL handoff: `?sub=X` pre-selects and shows the filter chip.
  const subSelect = document.getElementById("replays-sub-select") as HTMLSelectElement;
  void (async () => {
    try {
      const subs = await api.listKaggleSubmissions();
      // Newest first — Kaggle returns ISO dates descending already.
      for (const s of subs) {
        const opt = document.createElement("option");
        opt.value = String(s.submission_id);
        const shortDesc = (s.description || "").slice(0, 50);
        opt.textContent = `${s.submission_id}${shortDesc ? " · " + shortDesc : ""}`;
        if (subFilter && opt.value === subFilter) opt.selected = true;
        subSelect.appendChild(opt);
      }
    } catch {
      // Kaggle auth not set — leave only "All submissions". User will route
      // through Settings eventually; no point surfacing the error here.
    }
  })();
  subSelect.addEventListener("change", () => {
    const v = subSelect.value;
    location.hash = v ? `#/replays?sub=${encodeURIComponent(v)}` : "#/replays";
  });

  if (subFilter) {
    // `subFilter` comes from `?sub=` in the URL — user-controlled. Coerce to
    // an integer string so `<img onerror=…>` can never survive; if it isn't a
    // clean integer, render the raw string HTML-escaped instead.
    const digits = /^\d+$/.test(subFilter) ? subFilter : escapeHtml(subFilter);
    const chip = document.createElement("div");
    chip.className = "filter-chip";
    chip.innerHTML = `Filtered by submission <strong>${digits}</strong> <button class="filter-chip-x" title="Clear filter">✕</button>`;
    root.querySelector<HTMLElement>(".replays-toolbar")!.prepend(chip);
    chip.querySelector<HTMLButtonElement>(".filter-chip-x")!.addEventListener(
      "click",
      () => {
        location.hash = "#/replays";
      },
    );
  }

  // Persist pill + sort across navigation within tab.
  const FILTER_KEY = "ow-replays-filter";
  type ReplaysFilter = { source: Source; sort: "newest" | "oldest" | "turns-desc" | "turns-asc" };
  const restored: ReplaysFilter = (() => {
    try {
      const raw = sessionStorage.getItem(FILTER_KEY);
      if (!raw) return { source: "all", sort: "newest" };
      const p = JSON.parse(raw);
      return {
        source: (["all", "local", "kaggle"] as const).includes(p.source) ? p.source : "all",
        sort: (["newest", "oldest", "turns-desc", "turns-asc"] as const).includes(p.sort) ? p.sort : "newest",
      };
    } catch {
      return { source: "all", sort: "newest" };
    }
  })();

  let currentSource: Source = restored.source;
  let currentSort: "newest" | "oldest" | "turns-desc" | "turns-asc" = restored.sort;

  // Apply restored state to toolbar controls.
  root.querySelectorAll<HTMLButtonElement>("[data-source]").forEach((b) =>
    b.classList.toggle("on", b.dataset.source === currentSource),
  );
  (document.getElementById("replays-sort-select") as HTMLSelectElement).value = currentSort;

  function saveFilter(): void {
    try { sessionStorage.setItem(FILTER_KEY, JSON.stringify({ source: currentSource, sort: currentSort })); } catch { /* quota */ }
  }

  // Game-time: when the match was actually played.
  // Kaggle episodes carry ISO `endTime`; local tournaments carry `started_at`.
  // Fall back to file mtime (`ts`, seconds) if neither is present.
  function playedAtMs(r: Replay): number {
    if (r.source === "kaggle" && r.endTime) {
      const t = Date.parse(r.endTime);
      if (!isNaN(t)) return t;
    }
    if (r.source === "local" && r.started_at) {
      const t = Date.parse(r.started_at);
      if (!isNaN(t)) return t;
    }
    const ts = (r as any).ts;
    return typeof ts === "number" ? ts * 1000 : 0;
  }

  function formatRelative(ms: number): string {
    if (!ms) return "";
    const diff = Math.max(0, Date.now() - ms);
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s temu`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m} min temu`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h temu`;
    const d = Math.floor(h / 24);
    if (d < 14) return `${d}d temu`;
    const w = Math.floor(d / 7);
    if (w < 8) return `${w} tyg. temu`;
    const mo = Math.floor(d / 30);
    return `${mo} mies. temu`;
  }

  function sortItems(items: Replay[]): Replay[] {
    const copy = items.slice();
    if (currentSort === "newest" || currentSort === "oldest") {
      const sign = currentSort === "newest" ? -1 : 1;
      copy.sort((a, b) => sign * (playedAtMs(a) - playedAtMs(b)));
    } else {
      const sign = currentSort === "turns-desc" ? -1 : 1;
      copy.sort((a, b) => {
        const ta = a.source === "local" ? a.turns : 0;
        const tb = b.source === "local" ? b.turns : 0;
        return sign * (ta - tb);
      });
    }
    return copy;
  }

  async function loadList() {
    const listEl = document.getElementById("replays-list")!;
    listEl.innerHTML = `<div class="loading">Loading…</div>`;
    try {
      const r = await fetch(`/api/replays?source=${currentSource}`);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      let items: Replay[] = await r.json();
      if (subFilter) {
        const sub = Number(subFilter);
        items = items.filter(
          (i) => i.source === "kaggle" && i.submission_id === sub,
        );
      }
      renderList(sortItems(items));
    } catch (e) {
      listEl.innerHTML = `<div class="loading">Error: ${(e as Error).message}</div>`;
    }
  }

  function renderList(items: Replay[]) {
    const listEl = document.getElementById("replays-list")!;
    if (items.length === 0) {
      listEl.innerHTML = `<div class="loading">No replays yet. Play a match in Quick Match or import from Kaggle.</div>`;
      return;
    }
    listEl.innerHTML = items
      .map((r, idx) => {
        const playedMs = playedAtMs(r);
        const relative = formatRelative(playedMs);
        const absolute = playedMs
          ? new Date(playedMs).toISOString().replace("T", " ").slice(0, 16) + " UTC"
          : "";
        const timeCell = relative
          ? `<span class="replay-time" title="${absolute}">${relative}</span>`
          : "";
        if (r.source === "local") {
          const agents = r.agent_ids.map(escapeHtml).join(" vs ");
          const winner = r.winner ? escapeHtml(r.winner) : "draw";
          return `
            <div class="replay-item" data-idx="${idx}" data-kind="local"
                 data-run-id="${escapeHtml(r.run_id)}" data-match-id="${escapeHtml(r.match_id)}">
              <div class="replay-meta-row">
                <span class="replay-source local">local</span>
                <span class="replay-title">${agents}</span>
                <span class="replay-winner">winner: <strong>${winner}</strong></span>
                ${timeCell}
              </div>
              <div class="replay-meta-sub">
                run ${escapeHtml(r.run_id)} · match ${escapeHtml(r.match_id)} · ${r.turns} turns · ${r.duration_s.toFixed(1)}s · ${escapeHtml(r.status)}
              </div>
              <button class="replay-delete" title="Delete replay">×</button>
            </div>
          `;
        } else {
          const names =
            r.team_names && r.team_names.length > 0
              ? r.team_names
              : (r.agents || []).map((a) => a.name).filter(Boolean) as string[];
          const agents = names.length > 0 ? names.map(escapeHtml).join(" vs ") : "?";
          const winner = r.winner
            ? `winner: <strong>${escapeHtml(r.winner)}</strong>`
            : (r.type ? escapeHtml(r.type) : "");
          return `
            <div class="replay-item" data-idx="${idx}" data-kind="kaggle"
                 data-submission-id="${r.submission_id}" data-episode-id="${r.episode_id}">
              <div class="replay-meta-row">
                <span class="replay-source kaggle">kaggle</span>
                <span class="replay-title">${agents}</span>
                <span class="replay-winner">${winner}</span>
                ${timeCell}
              </div>
              <div class="replay-meta-sub">
                submission ${r.submission_id} · episode ${r.episode_id}
              </div>
              <button class="replay-delete" title="Delete replay">×</button>
            </div>
          `;
        }
      })
      .join("");

    listEl.querySelectorAll<HTMLElement>(".replay-item").forEach((el) => {
      el.addEventListener("click", (ev) => {
        if ((ev.target as HTMLElement).closest(".replay-delete")) return;
        const kind = el.dataset.kind;
        // Route through Quick Match so the user keeps the stats sidebar.
        // Quick Match reads sessionStorage on init and triggers the load.
        const payload = kind === "local"
          ? { kind: "local", runId: el.dataset.runId!, matchId: el.dataset.matchId! }
          : {
              kind: "kaggle",
              submissionId: parseInt(el.dataset.submissionId!, 10),
              episodeId: parseInt(el.dataset.episodeId!, 10),
            };
        sessionStorage.setItem("ow-pending-replay", JSON.stringify(payload));
        navigate({ view: "quick-match" });
      });
    });

    listEl.querySelectorAll<HTMLButtonElement>(".replay-delete").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const item = btn.closest(".replay-item") as HTMLElement;
        if (!item) return;
        if (!confirm("Delete this replay?")) return;
        try {
          if (item.dataset.kind === "local") {
            await api.deleteLocalReplay(item.dataset.runId!, item.dataset.matchId!);
          } else {
            await api.deleteKaggleReplay(
              parseInt(item.dataset.submissionId!, 10),
              parseInt(item.dataset.episodeId!, 10),
            );
          }
          await loadList();
        } catch (e) {
          alert(`Delete failed: ${(e as Error).message}`);
        }
      });
    });
  }

  // Source pills
  root.querySelectorAll<HTMLButtonElement>("[data-source]").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentSource = btn.dataset.source as Source;
      saveFilter();
      root.querySelectorAll<HTMLButtonElement>("[data-source]").forEach((b) => {
        b.classList.toggle("on", b === btn);
      });
      void loadList();
    });
  });

  // Sort select
  (document.getElementById("replays-sort-select") as HTMLSelectElement)
    .addEventListener("change", (e) => {
      currentSort = (e.target as HTMLSelectElement).value as typeof currentSort;
      saveFilter();
      void loadList();
    });

  // Scrape go — single episode from URL
  document.getElementById("scrape-go")!.addEventListener("click", async () => {
    const urlInput = document.getElementById("scrape-url") as HTMLInputElement;
    const url = urlInput.value.trim();
    if (!url) {
      alert("Paste a Kaggle URL");
      return;
    }
    const statusEl = document.getElementById("scrape-status")!;
    statusEl.hidden = false;
    statusEl.textContent = "Fetching…";
    try {
      const r = await fetch("/api/replays/scrape-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || r.statusText);
      }
      const data = await r.json();
      statusEl.textContent = `Imported: episode ${data.episode_id} (submission ${data.submission_id || "?"})`;
      urlInput.value = "";
      await loadList();
    } catch (e) {
      statusEl.textContent = `Error: ${(e as Error).message}`;
    }
  });

  await loadList();

  // Soft refresh every 10 s while user is on page
  if (pollInterval !== null) window.clearInterval(pollInterval);
  pollInterval = window.setInterval(() => {
    if (document.hidden) return;
    void loadList();
  }, 10000);
}

/**
 * Embedded replay player — iframe over /#/replay/:runId/:matchId (local) or
 * /#/kreplay/:submissionId/:episodeId (Kaggle).
 *
 * States:
 * - idle:     compact list of recent replays — click to play one here
 * - progress: spinner + matches_done / total
 * - loaded:   iframe with replay
 * - error:    error message
 */

export interface EmbeddedReplayMatch {
  runId: string;
  matchId: string;
}

export interface EmbeddedReplayHandle {
  load(runId: string, matches: EmbeddedReplayMatch[]): void;
  loadGame(index: number): void;
  clear(): void;
  showError(msg: string): void;
  showProgress(matchesDone: number, total: number): void;
  playLocal(runId: string, matchId: string): void;
  playKaggle(submissionId: number, episodeId: number): void;
}

interface ReplayListEntryLocal {
  source: "local";
  run_id: string;
  match_id: string;
  agent_ids: string[];
  winner: string | null;
  turns: number;
  duration_s: number;
  status: string;
}
interface ReplayListEntryKaggle {
  source: "kaggle";
  submission_id: number;
  episode_id: number;
  team_names?: string[];
  agents?: Array<{ name?: string }>;
  winner?: string | null;
}
type ReplayListEntry = ReplayListEntryLocal | ReplayListEntryKaggle;

const IDLE_LIST_LIMIT = 100;

export function mountEmbeddedReplay(root: HTMLElement): EmbeddedReplayHandle {
  let currentMatches: EmbeddedReplayMatch[] = [];
  let currentGameIdx = 0;

  async function renderIdle() {
    root.innerHTML = `
      <div class="replay-idle-list">
        <div class="replay-idle-head">
          <span>Recent replays</span>
          <span class="replay-idle-hint">click any to watch here</span>
        </div>
        <div class="replay-idle-items" id="replay-idle-items">
          <div class="loading">Loading…</div>
        </div>
      </div>
    `;

    let items: ReplayListEntry[] = [];
    try {
      const r = await fetch("/api/replays?source=all");
      if (r.ok) items = await r.json();
    } catch {
      // network error — keep empty
    }

    const itemsEl = document.getElementById("replay-idle-items");
    if (!itemsEl) return; // unmounted

    if (items.length === 0) {
      itemsEl.innerHTML = `<div class="loading">No replays yet. Play a match or import one from Kaggle.</div>`;
      return;
    }

    itemsEl.innerHTML = items
      .slice(0, IDLE_LIST_LIMIT)
      .map((r, idx) => {
        if (r.source === "local") {
          const agents = r.agent_ids.join(" vs ");
          const winner = r.winner ?? "draw";
          return `
            <div class="replay-idle-item" data-idx="${idx}" data-kind="local"
                 data-run-id="${r.run_id}" data-match-id="${r.match_id}">
              <span class="replay-source local">local</span>
              <span class="replay-idle-title">${agents}</span>
              <span class="replay-idle-winner">${winner}</span>
              <span class="replay-idle-meta">${r.turns}t</span>
            </div>
          `;
        } else {
          const names =
            (r.team_names && r.team_names.length > 0
              ? r.team_names
              : (r.agents || []).map((a) => a.name).filter(Boolean) as string[]);
          const agents = names.length > 0 ? names.join(" vs ") : "?";
          return `
            <div class="replay-idle-item" data-idx="${idx}" data-kind="kaggle"
                 data-submission-id="${r.submission_id}" data-episode-id="${r.episode_id}">
              <span class="replay-source kaggle">kaggle</span>
              <span class="replay-idle-title">${agents}</span>
              <span class="replay-idle-winner">${r.winner ?? ""}</span>
              <span class="replay-idle-meta">ep ${r.episode_id}</span>
            </div>
          `;
        }
      })
      .join("");

    itemsEl.querySelectorAll<HTMLElement>(".replay-idle-item").forEach((el) => {
      el.addEventListener("click", () => {
        const kind = el.dataset.kind;
        let src: string;
        const detail: any = { kind };
        if (kind === "local") {
          src = `#/replay/${el.dataset.runId}/${el.dataset.matchId}`;
          detail.runId = el.dataset.runId;
          detail.matchId = el.dataset.matchId;
        } else {
          src = `#/kreplay/${el.dataset.submissionId}/${el.dataset.episodeId}`;
          detail.submissionId = Number(el.dataset.submissionId);
          detail.episodeId = Number(el.dataset.episodeId);
        }
        // Notify parent view (Quick Match) so it can switch sidebar mode.
        root.dispatchEvent(new CustomEvent("ow-replay-selected", {
          detail, bubbles: true,
        }));
        renderIframeWithSrc(src);
      });
    });
  }

  function renderError(msg: string) {
    root.innerHTML = `
      <div class="replay-error">
        <p>⚠ ${msg}</p>
      </div>
    `;
  }

  function renderProgress(matchesDone: number, total: number) {
    const pct = total > 0 ? Math.floor((matchesDone / total) * 100) : 0;
    root.innerHTML = `
      <div class="replay-progress">
        <div class="spinner"></div>
        <p>Running match ${matchesDone + 1} / ${total}</p>
        <div class="progress-bar">
          <div class="progress-bar-fill" style="width: ${pct}%"></div>
        </div>
      </div>
    `;
  }

  function renderGameSelector() {
    if (currentMatches.length <= 1) return "";
    return `
      <div class="replay-game-selector">
        ${currentMatches
          .map(
            (_, i) =>
              `<button class="game-btn ${i === currentGameIdx ? "on" : ""}" data-idx="${i}">Game ${i + 1}</button>`,
          )
          .join("")}
      </div>
    `;
  }

  function renderIframe() {
    const match = currentMatches[currentGameIdx];
    if (!match) {
      renderError("No replay available for this game.");
      return;
    }
    const src = `#/replay/${match.runId}/${match.matchId}`;
    root.innerHTML = `
      ${renderGameSelector()}
      <iframe
        class="replay-iframe"
        src="${src}"
        title="Replay ${match.matchId}"
      ></iframe>
    `;

    root.querySelectorAll<HTMLButtonElement>(".game-btn").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.dataset.idx!, 10);
        currentGameIdx = idx;
        renderIframe();
      });
    });
  }

  function renderIframeWithSrc(src: string) {
    root.innerHTML = `
      <div class="replay-back-bar">
        <button class="back-to-idle" id="back-to-idle">← Back to list</button>
      </div>
      <iframe class="replay-iframe" src="${src}" title="Replay"></iframe>
    `;
    document.getElementById("back-to-idle")!.addEventListener("click", () => {
      currentMatches = [];
      void renderIdle();
    });
  }

  void renderIdle();

  return {
    load(runId: string, matches: EmbeddedReplayMatch[]) {
      currentMatches = matches.map((m) => ({
        runId: m.runId || runId,
        matchId: m.matchId,
      }));
      currentGameIdx = 0;
      renderIframe();
    },
    loadGame(index: number) {
      if (index < 0 || index >= currentMatches.length) return;
      currentGameIdx = index;
      renderIframe();
    },
    clear() {
      currentMatches = [];
      currentGameIdx = 0;
      void renderIdle();
    },
    showError(msg: string) {
      renderError(msg);
    },
    showProgress(matchesDone: number, total: number) {
      renderProgress(matchesDone, total);
    },
    playLocal(runId: string, matchId: string) {
      root.dispatchEvent(new CustomEvent("ow-replay-selected", {
        detail: { kind: "local", runId, matchId },
        bubbles: true,
      }));
      renderIframeWithSrc(`#/replay/${runId}/${matchId}`);
    },
    playKaggle(submissionId: number, episodeId: number) {
      root.dispatchEvent(new CustomEvent("ow-replay-selected", {
        detail: { kind: "kaggle", submissionId, episodeId },
        bubbles: true,
      }));
      renderIframeWithSrc(`#/kreplay/${submissionId}/${episodeId}`);
    },
  };
}

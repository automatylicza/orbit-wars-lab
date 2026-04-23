/**
 * Quick Match view — split-screen launcher dla matchy 1v1.
 *
 * Lewa kolumna: agent-picker + match-config-bar + Play button.
 * Prawa kolumna: embedded-replay (idle → progress → done).
 *
 * State machine:
 *   idle → running (POST /tournaments) → done (replay loaded) | error
 *   rematch z done → running → ...
 */

import { installHeaderNav } from "../components/header-nav";
import { mountAgentPicker, PickerSelection } from "../components/agent-picker";
import { mountMatchConfigBar, MatchConfig } from "../components/match-config-bar";
import { mountEmbeddedReplay, EmbeddedReplayHandle } from "../components/embedded-replay";
import { api } from "../api";

interface MatchStateIdle {
  kind: "idle";
}
interface MatchStateRunning {
  kind: "running";
  runId: string;
  totalMatches: number;
}
interface MatchStateDone {
  kind: "done";
  runId: string;
  matches: Array<{
    match_id: string;
    agent_ids: string[];
    winner: string | null;
    scores: number[];
    turns: number;
    duration_s: number;
    status: string;
  }>;
  replays: unknown[];
}
interface MatchStateError {
  kind: "error";
  msg: string;
}
type MatchState = MatchStateIdle | MatchStateRunning | MatchStateDone | MatchStateError;

const POLL_INTERVAL_MS = 500;
const POLL_MAX_CONSECUTIVE_FAILURES = 3;

export async function renderQuickMatch(root: HTMLElement): Promise<void> {
  root.innerHTML = `
    <div class="quick-match">
      <aside class="qm-left">
        <div class="qm-mode-tabs">
          <button class="qm-mode-tab on" data-mode="picker">Picker</button>
          <button class="qm-mode-tab" data-mode="view">View</button>
        </div>
        <div class="qm-pane qm-pane-picker">
          <div id="qm-picker"></div>
          <div id="qm-config"></div>
          <div id="qm-warning" class="qm-warning" hidden></div>
          <div id="qm-toast" class="qm-toast" hidden></div>
          <button id="qm-play" class="qm-play" disabled>Play</button>
        </div>
        <div class="qm-pane qm-pane-view" hidden>
          <details class="qm-acc" data-sec="match" open>
            <summary class="qm-acc-head"><span class="qm-acc-caret">▾</span>Match</summary>
            <div id="qm-view-match" class="qm-view-empty">No replay loaded yet.</div>
          </details>
          <details class="qm-acc" data-sec="planet">
            <summary class="qm-acc-head"><span class="qm-acc-caret">▾</span>Selected planet</summary>
            <div id="qm-view-planet" class="qm-view-empty">Click a planet on the map.</div>
          </details>
          <details class="qm-acc" data-sec="fleet">
            <summary class="qm-acc-head"><span class="qm-acc-caret">▾</span>Selected fleet</summary>
            <div id="qm-view-fleet" class="qm-view-empty">Click a fleet on the map.</div>
          </details>
          <details class="qm-acc" data-sec="display" open>
            <summary class="qm-acc-head"><span class="qm-acc-caret">▾</span>Display</summary>
            <div class="qm-display-pills">
              <button class="settings-pill" data-display="grid">grid</button>
              <button class="settings-pill" data-display="orbits">orbits</button>
              <button class="settings-pill" data-display="trajectories">fleet trajectories</button>
              <button class="settings-pill" data-display="canvas">light canvas</button>
            </div>
          </details>
        </div>
      </aside>
      <div class="qm-resize" id="qm-resize" title="Drag to resize">
        <button class="qm-collapse-btn" id="qm-collapse"
                title="Toggle panel (⌘B / Ctrl+B)">‹</button>
      </div>
      <section class="qm-right" id="qm-replay"></section>
    </div>
  `;
  installHeaderNav(root, "quick-match");

  // ----- Resizable + collapsible left panel -----
  const qmContainer = root.querySelector(".quick-match") as HTMLElement;
  const resizer = document.getElementById("qm-resize")!;
  const collapseBtn = document.getElementById("qm-collapse") as HTMLButtonElement;

  const DEFAULT_SIDEBAR_WIDTH = 360;
  const MIN_SIDEBAR_WIDTH = 200;
  const MAX_SIDEBAR_WIDTH = 500;
  const AUTO_COLLAPSE_BELOW = 800;

  // Sanity-clamp stale saved width so old drag sessions don't pin a tiny
  // sidebar across viewport changes.
  const savedRaw = localStorage.getItem("qm-left-width");
  let savedNum = savedRaw ? parseInt(savedRaw, 10) : NaN;
  if (!Number.isFinite(savedNum) || savedNum < MIN_SIDEBAR_WIDTH || savedNum > MAX_SIDEBAR_WIDTH) {
    savedNum = DEFAULT_SIDEBAR_WIDTH;
    localStorage.setItem("qm-left-width", `${savedNum}px`);
  }
  document.documentElement.style.setProperty("--qm-left-width", `${savedNum}px`);

  // Auto-collapse when the viewport is narrow; expand back when it grows.
  // Track whether the user explicitly overrode the auto decision so we
  // don't fight their choice.
  let userOverride = localStorage.getItem("qm-user-override") === "1";
  let isCollapsed = localStorage.getItem("qm-collapsed") === "1";
  if (!userOverride) {
    isCollapsed = window.innerWidth < AUTO_COLLAPSE_BELOW;
  }
  function applyCollapsed() {
    qmContainer.classList.toggle("qm-collapsed", isCollapsed);
    collapseBtn.textContent = isCollapsed ? "›" : "‹";
    localStorage.setItem("qm-collapsed", isCollapsed ? "1" : "0");
  }
  applyCollapsed();

  collapseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    isCollapsed = !isCollapsed;
    userOverride = true;
    localStorage.setItem("qm-user-override", "1");
    applyCollapsed();
  });

  // Keyboard shortcut: Cmd/Ctrl+B toggles the panel (VS Code / Claude Code idiom)
  function onKey(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      isCollapsed = !isCollapsed;
      userOverride = true;
      localStorage.setItem("qm-user-override", "1");
      applyCollapsed();
    }
  }
  window.addEventListener("keydown", onKey);

  // Re-evaluate auto-collapse on window resize (unless user took over).
  function onResize() {
    if (userOverride) return;
    const shouldCollapse = window.innerWidth < AUTO_COLLAPSE_BELOW;
    if (shouldCollapse !== isCollapsed) {
      isCollapsed = shouldCollapse;
      applyCollapsed();
    }
  }
  window.addEventListener("resize", onResize);

  // Double-click splitter → reset sidebar to default width + clear user override.
  resizer.addEventListener("dblclick", (e) => {
    if ((e.target as HTMLElement).closest(".qm-collapse-btn")) return;
    document.documentElement.style.setProperty("--qm-left-width", `${DEFAULT_SIDEBAR_WIDTH}px`);
    localStorage.setItem("qm-left-width", `${DEFAULT_SIDEBAR_WIDTH}px`);
    userOverride = false;
    localStorage.removeItem("qm-user-override");
    onResize();
  });

  let dragging = false;
  let dragMoved = false;
  resizer.addEventListener("mousedown", (e) => {
    if ((e.target as HTMLElement).closest(".qm-collapse-btn")) return;
    if (isCollapsed) return;
    dragging = true;
    dragMoved = false;
    resizer.classList.add("dragging");
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    dragMoved = true;
    const rect = qmContainer.getBoundingClientRect();
    const x = e.clientX - rect.left;
    // Clamp to [160, rect.width - 240]; no auto-collapse — use button/Cmd+B for that
    const w = Math.max(160, Math.min(rect.width - 240, x));
    document.documentElement.style.setProperty("--qm-left-width", `${w}px`);
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    resizer.classList.remove("dragging");
    if (dragMoved) {
      const w = getComputedStyle(document.documentElement)
        .getPropertyValue("--qm-left-width")
        .trim();
      if (w) localStorage.setItem("qm-left-width", w);
    }
  });

  const pickerEl = document.getElementById("qm-picker")!;
  const configEl = document.getElementById("qm-config")!;
  const warningEl = document.getElementById("qm-warning")!;
  const toastEl = document.getElementById("qm-toast")!;
  const playBtn = document.getElementById("qm-play") as HTMLButtonElement;
  let rightPanel = document.getElementById("qm-replay") as HTMLElement;

  // ----- Sidebar mode switcher (Picker ↔ View) -----
  const pickerPane = root.querySelector<HTMLElement>(".qm-pane-picker")!;
  const viewPane = root.querySelector<HTMLElement>(".qm-pane-view")!;
  const viewMatchEl = document.getElementById("qm-view-match")!;

  const PLAYER_COLORS = ["#5EA5FF", "#FF8A4C", "#5EED9F", "#C084FC"];

  function setSidebarMode(mode: "picker" | "view") {
    pickerPane.hidden = mode !== "picker";
    viewPane.hidden = mode !== "view";
    root.querySelectorAll<HTMLButtonElement>(".qm-mode-tab").forEach((b) => {
      b.classList.toggle("on", b.dataset.mode === mode);
    });
  }
  root.querySelectorAll<HTMLButtonElement>(".qm-mode-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      setSidebarMode(tab.dataset.mode as "picker" | "view");
    });
  });

  // Sidebar: render selected planet / fleet panels from localStorage.
  // The iframe renderer publishes ow-selected-data on every step change
  // (or click) — we pick it up via storage events + initial read.
  const viewPlanetEl = document.getElementById("qm-view-planet")!;
  const viewFleetEl = document.getElementById("qm-view-fleet")!;

  function resetPanel(el: HTMLElement, placeholder: string) {
    el.classList.add("qm-view-empty");
    el.textContent = placeholder;
  }

  function ownerLabel(owner: number): string {
    if (owner < 0) return "neutral";
    const color = PLAYER_COLORS[owner] ?? "#666";
    return `<span class="color-dot" style="background-color:${color}"></span>P${owner + 1}`;
  }

  function removeFromSelection(kind: "planet" | "fleet", id: number) {
    try {
      const raw = localStorage.getItem("ow-selection");
      const list = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(list)) return;
      const next = list.filter((e: any) => !(e.kind === kind && e.id === id));
      if (next.length === 0) localStorage.removeItem("ow-selection");
      else localStorage.setItem("ow-selection", JSON.stringify(next));
      // Trigger iframe re-render so it updates canvas + selected-data.
      // We can't call storage events directly within same document; instead
      // toggle ow-selection once more to fire. Easier: set ow-selection and
      // dispatch a custom 'ow-selection-ext' the iframe can listen for. But
      // storage events DO fire in the iframe (it's a different document).
      // So the simple write above is enough.
      renderSelectedPanel();
    } catch { /* stale */ }
  }

  function planetCard(d: any, removable: boolean): string {
    const inboundHtml = d.inbound.length === 0
      ? `<div class="qm-sel-muted">No fleets incoming.</div>`
      : `<ul class="qm-inbound">${
          d.inbound.map((f: any) =>
            `<li>
              <span class="color-dot" style="background-color:${PLAYER_COLORS[f.owner] ?? "#666"}"></span>
              <span class="qm-inbound-ships">${Math.floor(f.ships)}</span>
              <span class="qm-inbound-eta">ETA ${f.eta}t</span>
              <span class="qm-inbound-from">from #${f.fromPlanetId}</span>
            </li>`,
          ).join("")
        }</ul>`;
    const removeBtn = removable
      ? `<button class="qm-sel-remove" data-kind="planet" data-id="${d.id}" title="Remove from selection">×</button>`
      : "";
    return `
      <div class="qm-sel-card">
        ${removeBtn}
        <dl class="qm-sel-stats">
          <dt>id</dt><dd>#${d.id}${d.isComet ? " (comet)" : ""}</dd>
          <dt>owner</dt><dd>${ownerLabel(d.owner)}</dd>
          <dt>ships</dt><dd>${Math.floor(d.ships)}</dd>
          <dt>prod</dt><dd>+${d.production}/t</dd>
          <dt>pos</dt><dd>${d.x.toFixed(1)}, ${d.y.toFixed(1)}</dd>
          <dt>radius</dt><dd>${d.radius.toFixed(1)}</dd>
        </dl>
        <div class="qm-sel-section-label">Inbound fleets (${d.inbound.length})</div>
        ${inboundHtml}
      </div>
    `;
  }

  function fleetCard(d: any, removable: boolean): string {
    const target = d.target;
    const targetHtml = target
      ? `<dl class="qm-sel-stats">
          <dt>dest</dt><dd>#${target.planetId} (${ownerLabel(target.planetOwner)})</dd>
          <dt>eta</dt><dd><span class="qm-inbound-eta">${target.eta}t</span></dd>
          <dt>dist</dt><dd>${target.distance.toFixed(1)}u</dd>
        </dl>`
      : `<div class="qm-sel-muted">No planet on trajectory.</div>`;
    const removeBtn = removable
      ? `<button class="qm-sel-remove" data-kind="fleet" data-id="${d.id}" title="Remove from selection">×</button>`
      : "";
    return `
      <div class="qm-sel-card">
        ${removeBtn}
        <dl class="qm-sel-stats">
          <dt>id</dt><dd>#${d.id}</dd>
          <dt>owner</dt><dd>${ownerLabel(d.owner)}</dd>
          <dt>ships</dt><dd>${Math.floor(d.ships)}</dd>
          <dt>speed</dt><dd>${d.speed.toFixed(2)} u/t</dd>
          <dt>pos</dt><dd>${d.x.toFixed(1)}, ${d.y.toFixed(1)}</dd>
          <dt>from</dt><dd>#${d.fromPlanetId}</dd>
        </dl>
        <div class="qm-sel-section-label">Target</div>
        ${targetHtml}
      </div>
    `;
  }

  function wireRemoveButtons(el: HTMLElement) {
    el.querySelectorAll<HTMLButtonElement>(".qm-sel-remove").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const kind = btn.dataset.kind as "planet" | "fleet";
        const id = parseInt(btn.dataset.id!, 10);
        removeFromSelection(kind, id);
      });
    });
  }

  function renderSelectedPanel() {
    const raw = localStorage.getItem("ow-selected-data");
    if (!raw) {
      resetPanel(viewPlanetEl, "Click a planet on the map.");
      resetPanel(viewFleetEl, "Click a fleet on the map.");
      return;
    }
    try {
      const d = JSON.parse(raw);
      const planets: any[] = Array.isArray(d.planets) ? d.planets : [];
      const fleets: any[] = Array.isArray(d.fleets) ? d.fleets : [];

      if (planets.length === 0) {
        resetPanel(viewPlanetEl, "Click a planet on the map.");
      } else {
        viewPlanetEl.classList.remove("qm-view-empty");
        const header = planets.length > 1
          ? `<div class="qm-sel-count">${planets.length} selected</div>`
          : "";
        viewPlanetEl.innerHTML = header + planets.map((p) => planetCard(p, true)).join("");
        const planetAcc = root.querySelector<HTMLDetailsElement>('.qm-acc[data-sec="planet"]');
        if (planetAcc && !planetAcc.open) planetAcc.open = true;
        wireRemoveButtons(viewPlanetEl);
      }

      if (fleets.length === 0) {
        resetPanel(viewFleetEl, "Click a fleet on the map.");
      } else {
        viewFleetEl.classList.remove("qm-view-empty");
        const header = fleets.length > 1
          ? `<div class="qm-sel-count">${fleets.length} selected</div>`
          : "";
        viewFleetEl.innerHTML = header + fleets.map((f) => fleetCard(f, true)).join("");
        const fleetAcc = root.querySelector<HTMLDetailsElement>('.qm-acc[data-sec="fleet"]');
        if (fleetAcc && !fleetAcc.open) fleetAcc.open = true;
        wireRemoveButtons(viewFleetEl);
      }
    } catch { /* stale json */ }
  }

  renderSelectedPanel();
  window.addEventListener("storage", (e) => {
    if (e.key === "ow-selected-data" || e.key === null) renderSelectedPanel();
    if (e.key === "ow-live-match" || e.key === null) renderMatchPanel();
  });

  // Accordion: persist each section's open state in localStorage.
  // Key format: ow-acc-<section>.  Default: match + display open, planet/fleet
  // closed (they're empty until user clicks something).
  const ACC_DEFAULTS: Record<string, boolean> = {
    match: true, planet: false, fleet: false, display: true,
  };
  root.querySelectorAll<HTMLDetailsElement>(".qm-acc").forEach((d) => {
    const sec = d.dataset.sec!;
    const stored = localStorage.getItem(`ow-acc-${sec}`);
    d.open = stored === null ? ACC_DEFAULTS[sec] : stored === "1";
    d.addEventListener("toggle", () => {
      localStorage.setItem(`ow-acc-${sec}`, d.open ? "1" : "0");
    });
  });

  // Display-setting pills (sync with localStorage; iframe renderer listens
  // for 'storage' events and re-renders).
  function refreshDisplayPills() {
    const state: Record<string, boolean> = {
      grid: localStorage.getItem("ow-show-grid") !== "false",
      orbits: localStorage.getItem("ow-show-orbits") !== "false",
      trajectories: localStorage.getItem("ow-show-trajectories") === "true",
      canvas: localStorage.getItem("ow-canvas-theme") === "light",
    };
    root.querySelectorAll<HTMLButtonElement>(".qm-display-pills [data-display]")
      .forEach((btn) => {
        btn.classList.toggle("on", !!state[btn.dataset.display!]);
      });
  }
  refreshDisplayPills();
  root.querySelectorAll<HTMLButtonElement>(".qm-display-pills [data-display]")
    .forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.display!;
        if (key === "canvas") {
          const cur = localStorage.getItem("ow-canvas-theme") === "light";
          localStorage.setItem("ow-canvas-theme", cur ? "dark" : "light");
          refreshDisplayPills();
          return;
        }
        const lsKey = `ow-show-${key}`;
        const def = key !== "trajectories";  // grid/orbits default on, trajectories default off
        const current = localStorage.getItem(lsKey) === null
          ? def
          : localStorage.getItem(lsKey) === "true";
        localStorage.setItem(lsKey, (!current).toString());
        refreshDisplayPills();
      });
    });

  // Static match metadata (runId, duration, agent ids) — set once when a
  // replay is loaded. Live data (step, scores, winner) comes from
  // ow-live-match published each frame by the iframe renderer.
  let matchMeta: {
    runId: string;
    agentIds: string[];
    staticWinner: string | null;
    extra: string | null;
  } | null = null;

  function renderMatchPanel() {
    if (!matchMeta) {
      viewMatchEl.classList.add("qm-view-empty");
      viewMatchEl.textContent = "No replay loaded yet.";
      return;
    }
    viewMatchEl.classList.remove("qm-view-empty");

    let live: {
      step?: number;
      totalSteps?: number;
      scores?: number[];
      playerNames?: string[];
      isGameOver?: boolean;
      winnerIndices?: number[];
    } = {};
    try {
      const raw = localStorage.getItem("ow-live-match");
      if (raw) live = JSON.parse(raw);
    } catch { /* stale */ }

    const rows = matchMeta.agentIds.map((id, i) => {
      const color = PLAYER_COLORS[i] || "#888";
      const short = id.includes("/") ? id.split("/").pop()! : id;
      const shortTrim = short.length > 26 ? short.slice(0, 25) + "…" : short;
      const liveWinner =
        live.isGameOver && Array.isArray(live.winnerIndices) && live.winnerIndices.includes(i);
      const isWinner = liveWinner || (matchMeta!.staticWinner === id);
      const score = live.scores?.[i] ?? null;
      return `
        <div class="qm-view-player${isWinner ? " winner" : ""}" title="${id}">
          <span class="color-dot" style="background: ${color}"></span>
          <span class="qm-view-player-name">${shortTrim}</span>
          ${score !== null ? `<span class="qm-view-player-score">${score}</span>` : ""}
          ${isWinner ? `<span class="qm-view-player-crown">✓</span>` : ""}
        </div>
      `;
    });

    const stepLine =
      typeof live.step === "number" && typeof live.totalSteps === "number" && live.totalSteps > 0
        ? `<div class="qm-view-step">Turn <strong>${live.step}</strong> / ${live.totalSteps - 1}${live.isGameOver ? " · game over" : ""}</div>`
        : "";

    viewMatchEl.innerHTML = `
      <div class="qm-view-run">${matchMeta.runId}${matchMeta.extra ? ` · ${matchMeta.extra}` : ""}</div>
      ${stepLine}
      <div class="qm-view-players">${rows.join("")}</div>
    `;
  }

  // Back-compat helper — callers still treat this as "set meta and render".
  function renderMatchInfo(
    runId: string,
    agentIds: string[],
    winner: string | null,
    _scores: number[] | null,
    extra: string | null,
  ) {
    matchMeta = { runId, agentIds, staticWinner: winner, extra };
    renderMatchPanel();
  }

  let selection: PickerSelection = [null, null];
  let config: MatchConfig = {
    games: 1,
    mode: "fast",
    seed: "random",
    format: "2p",
  };
  let matchState: MatchState = { kind: "idle" };
  let pollTimer: number | null = null;
  let pollFailures = 0;
  let activeReplay: EmbeddedReplayHandle = mountEmbeddedReplay(rightPanel);

  // If user came here from /#/replays via sessionStorage handoff, load the
  // requested replay and switch to View tab. Read + clear in one pass.
  const pendingRaw = sessionStorage.getItem("ow-pending-replay");
  if (pendingRaw) {
    sessionStorage.removeItem("ow-pending-replay");
    try {
      const p = JSON.parse(pendingRaw);
      setSidebarMode("view");
      if (p.kind === "local" && p.runId && p.matchId) {
        activeReplay.playLocal(p.runId, p.matchId);
      } else if (p.kind === "kaggle" && p.submissionId && p.episodeId) {
        activeReplay.playKaggle(p.submissionId, p.episodeId);
      }
    } catch { /* stale json */ }
  }

  // Clicks inside the idle-list of embedded-replay bubble up as a
  // CustomEvent — switch sidebar to View + populate match info.
  rightPanel.addEventListener("ow-replay-selected", async (ev: Event) => {
    const detail = (ev as CustomEvent).detail;
    try {
      if (detail.kind === "local") {
        const run = await api.getRun(detail.runId);
        const m = run.results?.matches.find(
          (x: any) => x.match_id === detail.matchId,
        );
        if (m) {
          renderMatchInfo(
            detail.runId,
            m.agent_ids,
            m.winner,
            m.scores,
            `${m.turns}t · ${(m.duration_s || 0).toFixed(1)}s`,
          );
        }
      } else {
        // Kaggle replay: fetch meta from /api/replays to get agent names
        const r = await fetch(
          `/api/replays?source=kaggle`,
        ).then((r) => r.json());
        const hit = r.find(
          (x: any) =>
            x.submission_id === detail.submissionId &&
            x.episode_id === detail.episodeId,
        );
        const names =
          hit?.team_names ||
          (hit?.agents || []).map((a: any) => a.name).filter(Boolean);
        renderMatchInfo(
          `kaggle · ${detail.submissionId}`,
          names && names.length > 0 ? names : ["Player 1", "Player 2"],
          hit?.winner ?? null,
          null,
          `episode ${detail.episodeId}`,
        );
      }
    } catch {
      viewMatchEl.innerHTML = `<div class="qm-view-empty">Replay loaded.</div>`;
    }
    setSidebarMode("view");
  });

  const picker = await mountAgentPicker(
    pickerEl,
    (sel) => {
      selection = sel;
      updatePlayState();
    },
    2,
  );

  mountMatchConfigBar(configEl, (cfg) => {
    const formatChanged = cfg.format !== config.format;
    config = cfg;
    if (formatChanged) {
      picker.setNumSlots(cfg.format === "4p" ? 4 : 2);
    }
    updatePlayState();
  });

  function showToast(msg: string) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    setTimeout(() => {
      toastEl.hidden = true;
    }, 5000);
  }

  function updatePlayState() {
    const running = matchState.kind === "running";
    const allFilled = selection.every((s) => s !== null);

    warningEl.hidden = true;
    if (!allFilled) {
      playBtn.disabled = true;
    } else if (running) {
      playBtn.disabled = true;
    } else {
      playBtn.disabled = false;
    }
  }

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    pollFailures = 0;
  }

  function aggregateResults(matches: MatchStateDone["matches"]): {
    headline: string;
    meta: string;
  } {
    if (matches.length === 0) {
      return { headline: "No matches played", meta: "" };
    }
    const winCounts = new Map<string, number>();
    let totalTurns = 0;
    let totalDuration = 0;
    let crashedStatus: string | null = null;
    for (const m of matches) {
      if (m.winner) {
        winCounts.set(m.winner, (winCounts.get(m.winner) ?? 0) + 1);
      }
      totalTurns += m.turns;
      totalDuration += m.duration_s;
      if (m.status !== "ok") crashedStatus = m.status;
    }
    const sorted = Array.from(winCounts.entries()).sort((a, b) => b[1] - a[1]);
    const headline =
      sorted.length === 0
        ? "Draw"
        : matches.length === 1
          ? `${sorted[0][0]} wins`
          : `${sorted[0][0]} wins ${sorted[0][1]}–${sorted[1]?.[1] ?? 0}`;
    const avgTurns = Math.round(totalTurns / matches.length);
    const durStr = totalDuration.toFixed(1);
    const crashNote = crashedStatus ? ` · ⚠ ${crashedStatus}` : "";
    const meta = `${matches.length} game${matches.length > 1 ? "s" : ""} · ${avgTurns} turns avg · ${durStr} s${crashNote}`;
    return { headline, meta };
  }

  async function handleCompletion(runId: string) {
    try {
      const details = await api.getRun(runId);
      const matches = details.results?.matches ?? [];

      const doneMatches = matches.map((m: any) => ({
        match_id: m.match_id,
        agent_ids: m.agent_ids || [],
        winner: m.winner,
        scores: m.scores,
        turns: m.turns,
        duration_s: m.duration_s,
        status: m.status,
      }));
      matchState = {
        kind: "done",
        runId,
        matches: doneMatches,
        replays: [],
      };

      const agg = aggregateResults(doneMatches);
      rightPanel.innerHTML = `
        <div class="qm-result-card">
          <div class="qm-result-main">${agg.headline}</div>
          <div class="qm-result-meta">${agg.meta}</div>
        </div>
        <div id="qm-replay-inner"></div>
      `;
      const replayInner = document.getElementById("qm-replay-inner")!;
      activeReplay = mountEmbeddedReplay(replayInner);
      if (doneMatches.length > 0) {
        activeReplay.load(
          runId,
          doneMatches.map((m: any) => ({ runId, matchId: m.match_id })),
        );
        const first = doneMatches[0];
        renderMatchInfo(
          runId,
          first.agent_ids,
          first.winner,
          first.scores,
          `${first.turns}t · ${(first.duration_s || 0).toFixed(1)}s`,
        );
        setSidebarMode("view");
      } else {
        activeReplay.showError("No matches completed.");
      }

      await picker.refreshRatings();
    } catch (err) {
      matchState = {
        kind: "error",
        msg: `Failed to load results: ${(err as Error).message}`,
      };
      activeReplay.showError(matchState.msg);
    } finally {
      updatePlayState();
    }
  }

  playBtn.addEventListener("click", async () => {
    const agentsList = selection.filter((s): s is string => s !== null);
    if (agentsList.length !== (config.format === "4p" ? 4 : 2)) return;

    // Reset right panel to fresh replay wrapper
    rightPanel.innerHTML = "";
    activeReplay = mountEmbeddedReplay(rightPanel);

    const seedBase = config.seed === 42 ? 42 : Date.now() % 2 ** 31;
    const payload = {
      agents: agentsList,
      games_per_pair: config.games,
      mode: config.mode,
      format: config.format,
      seed_base: seedBase,
      is_quick_match: true,
    };

    try {
      const resp = await api.startTournament(payload);
      matchState = {
        kind: "running",
        runId: resp.run_id,
        totalMatches: config.games,
      };
      updatePlayState();
      activeReplay.showProgress(0, config.games);

      pollTimer = window.setInterval(async () => {
        try {
          const p = await api.getRunProgress(resp.run_id);
          pollFailures = 0;

          if (p.status === "running") {
            activeReplay.showProgress(p.matches_done, p.total_matches || config.games);
          } else if (p.status === "completed") {
            stopPolling();
            await handleCompletion(resp.run_id);
          } else {
            stopPolling();
            matchState = { kind: "error", msg: `Match ${p.status}` };
            activeReplay.showError(matchState.msg);
            updatePlayState();
          }
        } catch {
          pollFailures += 1;
          if (pollFailures >= POLL_MAX_CONSECUTIVE_FAILURES) {
            stopPolling();
            matchState = { kind: "error", msg: "Connection lost — please reload." };
            showToast(matchState.msg);
            updatePlayState();
          }
        }
      }, POLL_INTERVAL_MS) as unknown as number;
    } catch (err) {
      const status = (err as Error & { status?: number }).status ?? 0;
      if (status === 409) {
        showToast("Another tournament is already running. Wait for it to finish.");
      } else {
        showToast(`Failed to start match: ${(err as Error)?.message ?? "unknown error"}`);
      }
      matchState = { kind: "idle" };
      activeReplay.clear();
      updatePlayState();
    }
  });

  updatePlayState();
}

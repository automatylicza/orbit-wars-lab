import { api } from "../api";
import { navigate } from "../router";
import {
  createReplayVisualizer,
  ReplayAdapter,
} from "@kaggle-environments/core";
import { renderer } from "../renderer";
import { getOrbitWarsStepRenderTime } from "../timing";
import * as theme from "../theme";

export async function renderReplay(
  root: HTMLElement,
  runId: string,
  matchId: string,
): Promise<void> {
  const run = await api.getRun(runId);
  const match = run.results?.matches.find((m) => m.match_id === matchId);
  const replay = await api.getReplay(runId, matchId);

  const agentNames = match?.agent_ids.join(" vs ") ?? "?";
  const winner = match?.winner ?? "draw";

  // Hide the header (← Back, Match title, meta) when this view is rendered
  // inside an iframe (e.g. from Quick Match embedded replay) — the parent
  // already shows a result card and has its own navigation.
  const isEmbedded = window.self !== window.top;

  root.innerHTML = isEmbedded
    ? `<main id="canvas-mount"></main>`
    : `
      <header class="replay-header">
        <button id="back">← Back</button>
        <h1>Match ${matchId}</h1>
        <div class="meta">${agentNames} · winner: <strong>${winner}</strong> · turns: ${match?.turns ?? "?"}</div>
      </header>
      <main id="canvas-mount"></main>
    `;
  if (!isEmbedded) {
    document.getElementById("back")!.addEventListener("click", () => {
      navigate({ view: "quick-match" });
    });
  }

  const canvasMount = document.getElementById("canvas-mount")!;
  // Give it a unique id so Kaggle's HMR state tracking has a stable key.
  canvasMount.id = `canvas-mount-${runId}-${matchId}`;

  createReplayVisualizer(
    canvasMount,
    new ReplayAdapter({
      gameName: "orbit_wars",
      renderer: renderer as any,
      ui: "inline",
      getStepRenderTime: (step, replayMode, speedModifier) =>
        getOrbitWarsStepRenderTime(step, replayMode, speedModifier),
    }),
  );

  // Kaggle's Player.handleMessage (web/core/src/player/player.ts:106-165)
  // expects an ENVELOPED message: event.data.environment (or .replay).
  // Raw env.toJSON() payload at top level is silently ignored.
  // Wait a microtask for the message listener to attach before posting.
  // Engine's env.toJSON() doesn't populate info.TeamNames / info.Agents for
  // local matches — so the renderer would fall back to 'P1/P2'. Inject the
  // agent IDs from the match record before forwarding to the Kaggle player.
  if (match?.agent_ids && match.agent_ids.length > 0) {
    const r = replay as any;
    if (!r.info) r.info = {};
    if (!r.info.TeamNames || r.info.TeamNames.length === 0) {
      r.info.TeamNames = [...match.agent_ids];
    }
    if (!r.info.Agents || r.info.Agents.length === 0) {
      r.info.Agents = match.agent_ids.map((id) => ({ Name: id }));
    }
  }

  // Sync theme with Kaggle's React-rendered player.
  // Initial push via postMessage theming the first render. Subsequent
  // light↔dark flips reload the iframe — MUI ThemeProvider context
  // updates don't reliably flip PlaybackControls' inline styles on a
  // live tree, but a fresh page load always paints the correct colors.
  const pushTheme = () =>
    window.postMessage({ theme: theme.getResolvedTheme() }, "*");
  let lastResolved = theme.getResolvedTheme();
  document.addEventListener("ow-theme-changed", () => {
    const next = theme.getResolvedTheme();
    if (next !== lastResolved) {
      lastResolved = next;
      window.location.reload();
    }
  });

  await Promise.resolve();
  pushTheme();
  window.postMessage({ environment: replay }, "*");
}

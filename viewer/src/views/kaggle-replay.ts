/**
 * Kaggle replay viewer — standalone view for a Kaggle-scraped episode.
 * Analogous to views/replay.ts but fetches from /api/kaggle-replays/... and
 * accepts the raw Kaggle EpisodeService payload (which may wrap the replay).
 */

import { navigate } from "../router";
import {
  createReplayVisualizer,
  ReplayAdapter,
} from "@kaggle-environments/core";
import { renderer } from "../renderer";
import { getOrbitWarsStepRenderTime } from "../timing";
import * as theme from "../theme";

export async function renderKaggleReplay(
  root: HTMLElement,
  submissionId: string,
  episodeId: string,
): Promise<void> {
  let raw: any;
  try {
    const r = await fetch(`/api/kaggle-replays/${submissionId}/${episodeId}`);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    raw = await r.json();
  } catch (e) {
    root.innerHTML = `<div style="padding: 24px; color: #ff8a8a;">Error: ${(e as Error).message}</div>`;
    return;
  }

  // Kaggle EpisodeService may wrap replay: try common shapes to find env.toJSON()
  const replay = extractEnvPayload(raw);

  const isEmbedded = window.self !== window.top;

  root.innerHTML = isEmbedded
    ? `<main id="canvas-mount"></main>`
    : `
      <header class="replay-header">
        <button id="back">← Back</button>
        <h1>Kaggle episode ${episodeId}</h1>
        <div class="meta">submission <strong>${submissionId}</strong></div>
      </header>
      <main id="canvas-mount"></main>
    `;
  if (!isEmbedded) {
    document.getElementById("back")!.addEventListener("click", () => {
      navigate({ view: "replays" });
    });
  }

  const canvasMount = document.getElementById("canvas-mount")!;
  canvasMount.id = `canvas-mount-kaggle-${submissionId}-${episodeId}`;

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

  // Initial theme push sets first render. Live flips reload the iframe
  // because MUI ThemeProvider context changes don't always re-paint
  // PlaybackControls' inline styles on an existing tree.
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

/**
 * Kaggle's EpisodeService.GetEpisodeReplay can return in various shapes.
 * Most common (per refs/external-tools/episode-scraper):
 *   { replay: "<JSON string>" }         — replay is a stringified env.toJSON
 *   { replay: {...env fields...} }      — nested object
 *   {...env fields at top level...}     — direct payload
 * Normalize to env.toJSON() shape: { steps, info, configuration, ... }.
 */
function extractEnvPayload(raw: any): any {
  if (!raw) return raw;
  let candidate: any = raw;
  // Unwrap `replay` once
  if (typeof raw === "object" && "replay" in raw && raw.replay != null) {
    candidate = raw.replay;
  }
  // If stringified JSON, parse
  if (typeof candidate === "string") {
    try {
      candidate = JSON.parse(candidate);
    } catch {
      // leave as-is; renderer will fail gracefully
    }
  }
  return candidate;
}

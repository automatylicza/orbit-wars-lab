import type { RendererOptions } from '@kaggle-environments/core';
import { getStepData } from '@kaggle-environments/core';
import {
  getCanvasPalette,
  getPlayerColor,
  PLAYER_COLORS,
  TEXT_SIZES,
  trajectoryColor,
} from './renderer/palette';
import {
  Fleet,
  Planet,
  computeFleetTarget,
  computeInboundFleets,
  fleetSpeed,
  parseFleet,
  parsePlanet,
  readSelections,
  toggleSelection,
  writeSelections,
} from './renderer/selection';

// Game constants
const BOARD_SIZE = 100;
const CENTER = 50;
const SUN_RADIUS = 10;
// Engine rule: planets with orbital_radius + planet.radius >= 50 are static
// (won't rotate). Only orbiting ones get an orbit line.
const ROTATION_RADIUS_LIMIT = 50.0;


// --- Settings persistence. Fleet/production/text-size are fixed defaults.
//     User-controlled toggles (orbits + trajectories) persist in localStorage. ---
interface Settings {
  showFleetNumbers: boolean;
  showProductionDots: boolean;
  textSize: string;
  showOrbits: boolean;
  showTrajectories: boolean;
  showGrid: boolean;
}

function getSettings(_parent: HTMLElement): Settings {
  const ls = (k: string, fallback: boolean) => {
    const v = localStorage.getItem(k);
    if (v === null) return fallback;
    return v === 'true';
  };
  return {
    showFleetNumbers: true,
    showProductionDots: true,
    textSize: 'medium',
    showOrbits: ls('ow-show-orbits', true),
    showTrajectories: ls('ow-show-trajectories', false),
    showGrid: ls('ow-show-grid', true),
  };
}

// Track the most recent options so storage events from the parent window
// (Quick Match sidebar toggling display settings) can trigger a re-render.
let _lastOptions: RendererOptions | null = null;

if (typeof window !== 'undefined' && !(window as any).__owStorageBound) {
  (window as any).__owStorageBound = true;
  window.addEventListener('storage', (e) => {
    if (!_lastOptions) return;
    if (e.key && (
      e.key.startsWith('ow-show-') ||
      e.key === 'ow-canvas-theme' ||
      e.key === 'ow-selection'
    )) {
      try { renderer(_lastOptions); } catch { /* stale options */ }
    }
  });
}

export function renderer(options: RendererOptions) {
  _lastOptions = options;
  const { step, replay, parent, agents } = options;

  const stepData = getStepData(replay, step);
  if (!stepData || !(stepData as any)[0]?.observation) return;

  const settings = getSettings(parent);
  const palette = getCanvasPalette();
  const textScale = TEXT_SIZES[settings.textSize] || 1.0;

  const obs = (stepData as any)[0].observation;
  const planets: Planet[] = (obs.planets || []).map(parsePlanet);
  const fleets: Fleet[] = (obs.fleets || []).map(parseFleet);
  const cometPlanetIds = new Set<number>(obs.comet_planet_ids || []);
  // Detect player count — prefer explicit fields, fall back to max owner seen
  // in the first observation (engines don't always fill info.TeamNames).
  let numAgents =
    (replay as any).info?.TeamNames?.length ||
    (replay as any).info?.Agents?.length ||
    (agents?.length || 0);
  if (numAgents < 2) {
    let maxOwner = 1;
    for (const p of planets) if (p.owner > maxOwner) maxOwner = p.owner;
    for (const f of fleets) if (f.owner > maxOwner) maxOwner = f.owner;
    numAgents = maxOwner + 1;
  }

  // Previous step for diff detection
  let prevObs: any = null;
  if (step > 0) {
    const prevStep = getStepData(replay, step - 1);
    if (prevStep) prevObs = (prevStep as any)[0]?.observation;
  }

  // Build previous planet map for diff
  const prevPlanetMap = new Map<number, Planet>();
  if (prevObs?.planets) {
    for (const p of prevObs.planets) {
      const pp = parsePlanet(p);
      prevPlanetMap.set(pp.id, pp);
    }
  }

  // Detect game over
  const statuses = (stepData as any).map ? Array.from(stepData as any).map((s: any) => s?.status) : [];
  const isGameOver = statuses.some((s: string) => s === 'DONE');

  // Compute scores
  const playerScores: number[] = [];
  for (let i = 0; i < numAgents; i++) {
    let score = 0;
    for (const p of planets) {
      if (p.owner === i) score += Math.floor(p.ships);
    }
    for (const f of fleets) {
      if (f.owner === i) score += Math.floor(f.ships);
    }
    playerScores.push(score);
  }

  // Determine active players (those with planets or fleets)
  const activePlayers = new Set<number>();
  for (const p of planets) {
    if (p.owner >= 0) activePlayers.add(p.owner);
  }
  for (const f of fleets) {
    activePlayers.add(f.owner);
  }

  // In embedded mode (Quick Match iframe) the parent sidebar owns display
  // settings — no need for an in-renderer gear. Standalone replay pages
  // keep the inline settings row for convenience.
  const isEmbedded = window.self !== window.top;
  const settingsOpen =
    !isEmbedded && localStorage.getItem('ow-settings-open') === 'true';

  const gearAndRow = isEmbedded
    ? ''
    : `<button class="canvas-settings-btn${settingsOpen ? ' active' : ''}" title="Display settings" aria-label="Display settings">
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
            <circle cx="8" cy="8" r="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/>
            <path d="M8 1.5v1.7M8 12.8v1.7M14.5 8h-1.7M3.2 8H1.5M12.6 3.4l-1.2 1.2M4.6 11.4l-1.2 1.2M12.6 12.6l-1.2-1.2M4.6 4.6l-1.2-1.2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/>
          </svg>
        </button>`;
  const canvasLight = localStorage.getItem('ow-canvas-theme') === 'light';
  const settingsRowHtml = isEmbedded
    ? ''
    : `<div class="settings-row">
        <button class="settings-pill${settings.showGrid ? ' on' : ''}" data-toggle="grid">grid</button>
        <button class="settings-pill${settings.showOrbits ? ' on' : ''}" data-toggle="orbits">orbits</button>
        <button class="settings-pill${settings.showTrajectories ? ' on' : ''}" data-toggle="trajectories">trajectories</button>
        <button class="settings-pill${canvasLight ? ' on' : ''}" data-toggle="canvas">light canvas</button>
      </div>`;

  const headerHtml = isEmbedded
    ? ''
    : `<div class="header">
         <div class="header-players"></div>
         ${gearAndRow}
       </div>`;
  parent.innerHTML = `
    <div class="renderer-container${settingsOpen ? ' settings-open' : ''}">
      ${headerHtml}
      ${settingsRowHtml}
      <div class="canvas-wrapper">
        <canvas></canvas>
      </div>
    </div>
  `;

  const header = parent.querySelector('.header-players') as HTMLDivElement | null;
  const canvas = parent.querySelector('canvas') as HTMLCanvasElement;
  const canvasWrapper = canvas.parentElement as HTMLDivElement;
  if (!canvas || !replay) return;

  const rendererContainer = parent.querySelector<HTMLElement>('.renderer-container')!;
  const settingsBtn = parent.querySelector<HTMLButtonElement>('.canvas-settings-btn');
  if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
      const nextOpen = !rendererContainer.classList.contains('settings-open');
      localStorage.setItem('ow-settings-open', nextOpen.toString());
      renderer(options);
    });
    parent.querySelectorAll<HTMLButtonElement>('.settings-pill[data-toggle]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.toggle;
        if (key === 'canvas') {
          const cur = localStorage.getItem('ow-canvas-theme') === 'light';
          localStorage.setItem('ow-canvas-theme', cur ? 'dark' : 'light');
          renderer(options);
          return;
        }
        let current = false;
        if (key === 'orbits') current = settings.showOrbits;
        else if (key === 'trajectories') current = settings.showTrajectories;
        else if (key === 'grid') current = settings.showGrid;
        const next = !current;
        if (key === 'orbits') localStorage.setItem('ow-show-orbits', next.toString());
        else if (key === 'trajectories') localStorage.setItem('ow-show-trajectories', next.toString());
        else if (key === 'grid') localStorage.setItem('ow-show-grid', next.toString());
        renderer(options);
      });
    });
  }

  // Size canvas: always a square that fills the wrapper. DOM inspection
  // confirms Kaggle's playback bar sits as a SIBLING below the wrapper
  // (not inside it), so no extra bottom padding is needed — any reserved
  // margin was just unused empty space.
  const dpr = window.devicePixelRatio || 1;
  const wrapperRect = canvasWrapper.getBoundingClientRect();
  const cssSize = Math.max(
    100,
    Math.floor(Math.min(wrapperRect.width, wrapperRect.height)),
  );
  canvas.style.width = `${cssSize}px`;
  canvas.style.height = `${cssSize}px`;
  canvas.style.position = 'absolute';
  canvas.style.left = `${(wrapperRect.width - cssSize) / 2}px`;
  canvas.style.top = `${(wrapperRect.height - cssSize) / 2}px`;
  canvas.width = Math.round(cssSize * dpr);
  canvas.height = Math.round(cssSize * dpr);

  const c = canvas.getContext('2d');
  if (!c) return;
  c.scale(dpr, dpr);
  // Explicitly request high-quality resampling for any path/text we draw.
  // Canvas defaults vary by browser; forcing 'high' avoids soft edges on
  // text + circle strokes at non-integer scales.
  c.imageSmoothingEnabled = true;
  (c as any).imageSmoothingQuality = 'high';

  // All drawing uses CSS pixels; the DPR scaling handles sharpness
  const w = cssSize;
  const scale = w / BOARD_SIZE;

  // Clean up stale viewport state from the (reverted) zoom/pan experiment.
  // Harmless no-op if absent.
  localStorage.removeItem('ow-viewport');

  // Canvas click — hit-test planets + fleets. Multi-select: toggle on hit,
  // clear on miss. Selection persisted in localStorage so step changes
  // preserve it and the parent frame's sidebar picks it up via storage events.
  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const gx = (e.clientX - rect.left) / scale;
    const gy = (e.clientY - rect.top) / scale;
    let hitPlanet: Planet | null = null;
    // Check planets in reverse draw order (topmost first)
    for (let i = planets.length - 1; i >= 0; i--) {
      const p = planets[i];
      const ddx = gx - p.x;
      const ddy = gy - p.y;
      const hr = Math.max(p.radius + 0.5, 1.2);
      if (ddx * ddx + ddy * ddy <= hr * hr) { hitPlanet = p; break; }
    }
    let hitFleet: Fleet | null = null;
    if (!hitPlanet) {
      const fleetHitR = 1.8; // enlarged hit area vs chevron shape
      for (let i = fleets.length - 1; i >= 0; i--) {
        const f = fleets[i];
        const ddx = gx - f.x;
        const ddy = gy - f.y;
        if (ddx * ddx + ddy * ddy <= fleetHitR * fleetHitR) { hitFleet = f; break; }
      }
    }
    const prev = readSelections();
    if (hitPlanet) {
      writeSelections(toggleSelection(prev, { kind: "planet", id: hitPlanet.id }));
    } else if (hitFleet) {
      writeSelections(toggleSelection(prev, { kind: "fleet", id: hitFleet.id }));
    } else {
      // Empty-space click — clear all.
      writeSelections([]);
    }
    renderer(options);
  });

  // Publish selected entity's full stats to localStorage so the parent frame
  // (Quick Match sidebar) updates via 'storage' events. Auto-clears if the
  // selected planet no longer exists (e.g. conquered and now has a new
  // fake "same-id" entity? — rare; but guard anyway).
  const currentSelections = readSelections();
  const selectedPlanetsData: any[] = [];
  const selectedFleetsData: any[] = [];
  for (const entry of currentSelections) {
    if (entry.kind === "planet") {
      const sp = planets.find((p) => p.id === entry.id);
      if (!sp) continue;
      selectedPlanetsData.push({
        id: sp.id,
        owner: sp.owner,
        ships: sp.ships,
        production: sp.production,
        x: sp.x,
        y: sp.y,
        radius: sp.radius,
        isComet: cometPlanetIds.has(sp.id),
        inbound: computeInboundFleets(sp, fleets),
      });
    } else {
      const sf = fleets.find((f) => f.id === entry.id);
      if (!sf) continue;
      selectedFleetsData.push({
        id: sf.id,
        owner: sf.owner,
        ships: sf.ships,
        angle: sf.angle,
        x: sf.x,
        y: sf.y,
        fromPlanetId: sf.fromPlanetId,
        speed: fleetSpeed(sf.ships),
        target: computeFleetTarget(sf, planets),
      });
    }
  }
  if (selectedPlanetsData.length + selectedFleetsData.length > 0) {
    localStorage.setItem("ow-selected-data", JSON.stringify({
      planets: selectedPlanetsData,
      fleets: selectedFleetsData,
      step,
    }));
  } else {
    localStorage.removeItem("ow-selected-data");
  }

  // --- Header: player cards ---
  // Kaggle uses `Name` (capital), our local runs pass `name`. Also fall back
  // to replay.info.TeamNames if agents[] is missing (Kaggle replays sometimes
  // only set it there).
  const teamNames = (replay as any)?.info?.TeamNames as string[] | undefined;
  const playerNames: string[] = [];
  for (let i = 0; i < numAgents; i++) {
    const agent: any = agents?.[i];
    const name =
      agent?.name || agent?.Name || teamNames?.[i] || `P${i + 1}`;
    playerNames.push(name);
  }

  const headerParts: string[] = [];
  const shortName = (n: string, max = 20) => {
    // Drop bucket prefix like "baselines/" or "external/"
    const last = n.includes('/') ? n.split('/').pop()! : n;
    return last.length > max ? last.slice(0, max - 1) + '…' : last;
  };
  // When rendered inside the Quick Match iframe, the sidebar's Match
  // accordion shows players + live scores + step — no need for the
  // canvas-top header, so free up vertical room for a bigger play area.
  if (!isEmbedded && header) {
    for (let i = 0; i < numAgents; i++) {
      const isActive = activePlayers.has(i);
      const activeClass = isActive ? ' active' : '';
      const full = playerNames[i];
      const short = shortName(full);
      headerParts.push(
        `<span class="player-card${activeClass}" title="${full.replace(/"/g, '&quot;')}">` +
          `<span class="color-dot" style="background-color: ${PLAYER_COLORS[i]}"></span>` +
          `${short}` +
          `<span class="ship-count">${playerScores[i]}</span>` +
          `</span>`
      );
      if (i < numAgents - 1) {
        headerParts.push(`<span class="vs-sep">vs</span>`);
      }
    }
    header.innerHTML = headerParts.join('');
  } else if (isEmbedded) {
    // Publish live match state for the parent sidebar.
    const totalSteps = (replay as any)?.steps?.length ?? 0;
    // Sidebar winner flag: engine only declares a winner when a UNIQUE player
    // has a positive score. Ties (max shared) and all-zero end states produce
    // no winner — previously we marked every tied player with ✓ including
    // 0-0 dead-dead games.
    const winnerIndices: number[] = [];
    if (isGameOver) {
      const maxScore = Math.max(...playerScores);
      if (maxScore > 0) {
        const topIdx: number[] = [];
        for (let i = 0; i < numAgents; i++) {
          if (playerScores[i] === maxScore) topIdx.push(i);
        }
        if (topIdx.length === 1) winnerIndices.push(topIdx[0]);
      }
    }
    localStorage.setItem('ow-live-match', JSON.stringify({
      step,
      totalSteps,
      playerNames,
      scores: playerScores,
      activePlayers: Array.from(activePlayers),
      isGameOver,
      winnerIndices,
    }));
  }

  // --- Draw game board on canvas ---
  c.fillStyle = palette.bg;
  c.fillRect(0, 0, w, w);

  // Thin border around the play area
  c.strokeStyle = palette.boardBorder;
  c.lineWidth = 1;
  c.strokeRect(0.5, 0.5, w - 1, w - 1);

  // Grid overlay: minor lines every 1 unit, major every 10.
  if (settings.showGrid) {
    c.lineWidth = 0.5;
    c.strokeStyle = palette.gridMinor;
    c.beginPath();
    for (let i = 1; i < BOARD_SIZE; i++) {
      if (i % 10 === 0) continue;
      c.moveTo(i * scale + 0.5, 0);
      c.lineTo(i * scale + 0.5, w);
      c.moveTo(0, i * scale + 0.5);
      c.lineTo(w, i * scale + 0.5);
    }
    c.stroke();

    c.strokeStyle = palette.gridMajor;
    c.beginPath();
    for (let i = 10; i < BOARD_SIZE; i += 10) {
      c.moveTo(i * scale + 0.5, 0);
      c.lineTo(i * scale + 0.5, w);
      c.moveTo(0, i * scale + 0.5);
      c.lineTo(w, i * scale + 0.5);
    }
    c.stroke();
  }

  // Orbits — thin circles for rotating planets + comet paths (ellipses).
  if (settings.showOrbits) {
    const centerPx = CENTER * scale;
    const cometIdSet = cometPlanetIds;
    c.strokeStyle = palette.orbit;
    c.lineWidth = 0.5;
    const initialPlanets: any[] = (obs as any).initial_planets || [];
    for (const ip of initialPlanets) {
      const pid = ip[0];
      if (cometIdSet.has(pid)) continue;
      const dx = ip[2] - CENTER;
      const dy = ip[3] - CENTER;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r < 0.5) continue;
      const planetRadius = ip[4];
      if (r + planetRadius >= ROTATION_RADIUS_LIMIT) continue;
      c.beginPath();
      c.arc(centerPx, centerPx, r * scale, 0, Math.PI * 2);
      c.stroke();
    }
    if (obs.comets) {
      c.strokeStyle = palette.cometOrbit;
      c.lineWidth = 0.5;
      for (const group of obs.comets) {
        for (const path of group.paths) {
          if (!path || path.length < 2) continue;
          c.beginPath();
          for (let j = 0; j < path.length; j++) {
            const x = path[j][0] * scale;
            const y = path[j][1] * scale;
            if (j === 0) c.moveTo(x, y);
            else c.lineTo(x, y);
          }
          c.closePath();
          c.stroke();
        }
      }
    }
  }

  // Draw sun with glow
  const sunX = CENTER * scale;
  const sunY = CENTER * scale;
  const sunR = SUN_RADIUS * scale;

  const glow = c.createRadialGradient(sunX, sunY, sunR * 0.5, sunX, sunY, sunR * 2.5);
  glow.addColorStop(0, 'rgba(255, 200, 50, 0.6)');
  glow.addColorStop(0.5, 'rgba(255, 150, 20, 0.2)');
  glow.addColorStop(1, 'rgba(255, 100, 0, 0)');
  c.fillStyle = glow;
  c.fillRect(0, 0, w, w);

  // Sun body
  c.beginPath();
  c.arc(sunX, sunY, sunR, 0, Math.PI * 2);
  c.fillStyle = '#FFB800';
  c.fill();
  c.strokeStyle = '#FFD700';
  c.lineWidth = 1;
  c.stroke();

  // Draw comet trails
  if (obs.comets) {
    for (const group of obs.comets) {
      const idx = group.path_index;
      for (let i = 0; i < group.planet_ids.length; i++) {
        const path = group.paths[i];
        const tailLen = Math.min(idx + 1, path.length, 5);
        if (tailLen < 2) continue;
        for (let t = 1; t < tailLen; t++) {
          const pi = idx - t;
          if (pi < 0) break;
          const alpha = 0.4 * (1 - t / tailLen);
          c.beginPath();
          c.moveTo(path[pi + 1][0] * scale, path[pi + 1][1] * scale);
          c.lineTo(path[pi][0] * scale, path[pi][1] * scale);
          c.strokeStyle = trajectoryColor(palette, alpha);
          c.lineWidth = ((2.5 - (1.5 * t) / tailLen) * scale) / 5;
          c.lineCap = 'round';
          c.stroke();
        }
      }
    }
  }

  // Draw planets
  for (const planet of planets) {
    const px = planet.x * scale;
    const py = planet.y * scale;
    const pr = planet.radius * scale;
    const color = getPlayerColor(planet.owner);
    const isComet = cometPlanetIds.has(planet.id);

    // Check if ownership changed from previous step
    const prev = prevPlanetMap.get(planet.id);
    const ownerChanged = prev && prev.owner !== planet.owner;

    // Planet body
    c.beginPath();
    c.arc(px, py, pr, 0, Math.PI * 2);
    c.fillStyle = color;
    c.globalAlpha = planet.owner >= 0 ? 0.85 : 0.5;
    c.fill();
    c.globalAlpha = 1;

    // Border
    c.beginPath();
    c.arc(px, py, pr, 0, Math.PI * 2);
    c.strokeStyle = isComet ? '#88ccff' : '#555';
    c.lineWidth = isComet ? 2 : 1;
    c.stroke();

    // Ownership change highlight
    if (ownerChanged) {
      c.beginPath();
      c.arc(px, py, pr + 3, 0, Math.PI * 2);
      c.strokeStyle = color;
      c.lineWidth = 2;
      c.stroke();
    }

    // Production number — '+N' next to each planet. Prefer below, but flip
    // above when the label would fall off the canvas bottom.
    if (settings.showProductionDots && planet.production > 0) {
      const labelFont = Math.max(8, 1.35 * scale * textScale);
      c.font = `500 ${labelFont}px 'JetBrains Mono', ui-monospace, monospace`;
      c.fillStyle = palette.fleetText;
      c.textAlign = 'center';
      const below = py + pr + 3 + labelFont + 2 <= cssSize;
      if (below) {
        c.textBaseline = 'top';
        c.fillText(`+${planet.production}`, px, py + pr + 3);
      } else {
        c.textBaseline = 'bottom';
        c.fillText(`+${planet.production}`, px, py - pr - 3);
      }
    }
  }

  // Fleet trajectories — dashed forward line in the fleet's owner color.
  // Extends until it hits the sun / board edge (based on current geometry;
  // planets move, so we don't pretend to predict interception).
  if (settings.showTrajectories) {
    c.save();
    c.lineWidth = 1;
    c.setLineDash([4, 3]);
    for (const fleet of fleets) {
      const color = getPlayerColor(fleet.owner);
      const fx = fleet.x, fy = fleet.y;
      const dx = Math.cos(fleet.angle), dy = Math.sin(fleet.angle);
      // Ray-to-edge: max t such that fleet stays in board
      let tMax = BOARD_SIZE * 1.5;
      if (dx > 1e-9) tMax = Math.min(tMax, (BOARD_SIZE - fx) / dx);
      else if (dx < -1e-9) tMax = Math.min(tMax, -fx / dx);
      if (dy > 1e-9) tMax = Math.min(tMax, (BOARD_SIZE - fy) / dy);
      else if (dy < -1e-9) tMax = Math.min(tMax, -fy / dy);
      // Ray-to-sun: stop before hitting the sun
      const mx = CENTER - fx, my = CENTER - fy;
      const proj = mx * dx + my * dy;
      if (proj > 0) {
        const perp2 = (mx * mx + my * my) - proj * proj;
        if (perp2 < SUN_RADIUS * SUN_RADIUS) {
          const d = Math.sqrt(SUN_RADIUS * SUN_RADIUS - perp2);
          tMax = Math.min(tMax, proj - d);
        }
      }
      tMax = Math.max(0, tMax);
      const ex = fx + dx * tMax, ey = fy + dy * tMax;
      c.beginPath();
      c.moveTo(fx * scale, fy * scale);
      c.lineTo(ex * scale, ey * scale);
      c.strokeStyle = color;
      c.globalAlpha = 0.35;
      c.stroke();
    }
    c.restore();
  }

  // Draw fleets as chevrons
  for (const fleet of fleets) {
    const fx = fleet.x * scale;
    const fy = fleet.y * scale;
    const color = getPlayerColor(fleet.owner);
    const sz = (0.4 + (2.0 * Math.log(Math.max(1, fleet.ships))) / Math.log(1000)) * scale;

    c.save();
    c.translate(fx, fy);
    c.rotate(fleet.angle);

    // Standard chevron shape for all players
    c.beginPath();
    c.moveTo(sz, 0);
    c.lineTo(-sz, -sz * 0.6);
    c.lineTo(-sz * 0.3, 0);
    c.lineTo(-sz, sz * 0.6);
    c.closePath();
    c.fillStyle = color;
    c.globalAlpha = 0.85;
    c.fill();
    c.globalAlpha = 1;
    c.strokeStyle = '#222';
    c.lineWidth = 0.5;
    c.stroke();

    // Per-player marking lines for colorblind accessibility
    // P0: none, P1: 1 center line, P2: 2 lines (tip-to-wings), P3: 3 lines
    c.strokeStyle = palette.trajectoryGlow;
    c.lineWidth = sz * 0.15;
    c.lineCap = 'round';
    if (fleet.owner === 1 || fleet.owner === 3) {
      c.beginPath();
      c.moveTo(sz * 0.8, 0);
      c.lineTo(-sz * 0.2, 0);
      c.stroke();
    }
    if (fleet.owner === 2 || fleet.owner === 3) {
      c.beginPath();
      c.moveTo(sz * 0.6, -sz * 0.15);
      c.lineTo(-sz * 0.7, -sz * 0.45);
      c.stroke();
      c.beginPath();
      c.moveTo(sz * 0.6, sz * 0.15);
      c.lineTo(-sz * 0.7, sz * 0.45);
      c.stroke();
    }

    c.restore();
  }

  // Draw ship counts on planets
  const planetFontSize = Math.max(8, scale * 1.8 * textScale);
  const deltaFontSize = Math.max(6, scale * 1.2 * textScale);
  c.font = `bold ${planetFontSize}px Inter, sans-serif`;
  c.textAlign = 'center';
  c.textBaseline = 'middle';
  for (const planet of planets) {
    const px = planet.x * scale;
    const py = planet.y * scale;
    const shipText = Math.floor(planet.ships).toString();

    c.font = `bold ${planetFontSize}px Inter, sans-serif`;
    c.fillStyle = '#000000';
    c.fillText(shipText, px + 0.5, py + 0.5);
    c.fillStyle = '#ffffff';
    c.fillText(shipText, px, py);

    // Ship count delta (only when production display is on)
    if (settings.showProductionDots) {
      const prev = prevPlanetMap.get(planet.id);
      if (prev) {
        const delta = Math.floor(planet.ships) - Math.floor(prev.ships);
        if (delta !== 0) {
          const deltaText = delta > 0 ? `+${delta}` : `${delta}`;
          c.font = `bold ${deltaFontSize}px Inter, sans-serif`;
          c.fillStyle = delta > 0 ? '#009E73' : '#D55E00';
          c.fillText(deltaText, px, py - planet.radius * scale - deltaFontSize);
        }
      }
    }
  }

  // Fleet ship counts
  if (settings.showFleetNumbers) {
    const fleetFontSize = Math.max(6, scale * 1.2 * textScale);
    c.font = `${fleetFontSize}px Inter, sans-serif`;
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    for (const fleet of fleets) {
      const fx = fleet.x * scale;
      const fy = fleet.y * scale;
      const labelOffset = fleet.y >= 50 ? -scale * 2.5 : scale * 2.5;
      c.fillStyle = getPlayerColor(fleet.owner);
      c.fillText(Math.floor(fleet.ships).toString(), fx, fy + labelOffset);
    }
  }

  // Selection highlights — rings around every currently-selected entity.
  if (currentSelections.length > 0) {
    c.strokeStyle = palette.selection;
    c.lineWidth = 2;
    for (const entry of currentSelections) {
      if (entry.kind === "planet") {
        const sp = planets.find((p) => p.id === entry.id);
        if (sp) {
          c.beginPath();
          c.arc(sp.x * scale, sp.y * scale, (sp.radius + 0.9) * scale, 0, Math.PI * 2);
          c.stroke();
        }
      } else {
        const sf = fleets.find((f) => f.id === entry.id);
        if (sf) {
          c.beginPath();
          c.arc(sf.x * scale, sf.y * scale, 2.0 * scale, 0, Math.PI * 2);
          c.stroke();
        }
      }
    }
  }

  // Step indicator
  const stepFontSize = Math.max(8, scale * 1.5 * textScale);
  c.font = `${stepFontSize}px Inter, sans-serif`;
  c.textAlign = 'left';
  c.textBaseline = 'top';
  c.fillStyle = '#888';
  c.fillText(`Step ${step}`, 6, 6);

  // Game over overlay
  if (isGameOver) {
    const maxScore = Math.max(...playerScores);
    const winners = playerScores.reduce<number[]>((acc, s, i) => {
      if (s === maxScore) acc.push(i);
      return acc;
    }, []);
    const winnerText = winners.length > 1 ? 'Draw!' : `${playerNames[winners[0]]} wins!`;

    const overlay = document.createElement('div');
    overlay.className = 'game-over-overlay';
    overlay.innerHTML = `
      <div class="game-over-modal">
        <h2>Game Over</h2>
        <div class="result-text">${winnerText}</div>
        <div style="margin-top: 8px; font-size: 0.85rem; color: #888;">
          ${playerScores.map((s, i) => `${playerNames[i]}: ${s}`).join(' &mdash; ')}
        </div>
      </div>
    `;
    canvasWrapper.appendChild(overlay);
  }
}

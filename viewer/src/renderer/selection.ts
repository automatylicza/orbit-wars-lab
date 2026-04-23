/**
 * Multi-select state + geometry helpers for the Orbit Wars renderer.
 *
 * Selection is persisted in localStorage["ow-selection"] as a JSON array.
 * Fleet ETA / intercept helpers live here because they serve both the
 * click-hit-test (renderer) and the stats-publish path (selected-data).
 */

export interface Planet {
  id: number;
  owner: number;
  x: number;
  y: number;
  radius: number;
  ships: number;
  production: number;
}

export interface Fleet {
  id: number;
  owner: number;
  x: number;
  y: number;
  angle: number;
  fromPlanetId: number;
  ships: number;
}

export function parsePlanet(p: number[]): Planet {
  return { id: p[0], owner: p[1], x: p[2], y: p[3], radius: p[4], ships: p[5], production: p[6] };
}

export function parseFleet(f: number[]): Fleet {
  return { id: f[0], owner: f[1], x: f[2], y: f[3], angle: f[4], fromPlanetId: f[5], ships: f[6] };
}

/** Ship speed formula from refs/engine/orbit_wars.py:528.
 *  Max 6.0 u/turn, min 1.0, sublinear in fleet size. */
export function fleetSpeed(ships: number, maxSpeed = 6.0): number {
  if (ships <= 1) return 1.0;
  const s = 1.0 + (maxSpeed - 1.0) * Math.pow(Math.log(ships) / Math.log(1000), 1.5);
  return Math.min(s, maxSpeed);
}

export interface InboundFleet {
  owner: number;
  ships: number;
  eta: number;
  speed: number;
  fromPlanetId: number;
  distance: number;
}

/** Linear-extrapolation intercept check. Ignores planet rotation —
 *  good enough for UI ETA display; not accurate for game AI. */
export function computeInboundFleets(target: Planet, fleets: Fleet[]): InboundFleet[] {
  const out: InboundFleet[] = [];
  for (const f of fleets) {
    const dx = target.x - f.x;
    const dy = target.y - f.y;
    const cos = Math.cos(f.angle);
    const sin = Math.sin(f.angle);
    const proj = dx * cos + dy * sin;
    if (proj <= 0) continue;
    const perp = Math.abs(dx * sin - dy * cos);
    if (perp > target.radius + 1.5) continue;
    const speed = fleetSpeed(f.ships);
    const distToEdge = Math.max(0, proj - target.radius);
    out.push({
      owner: f.owner,
      ships: f.ships,
      eta: Math.max(1, Math.ceil(distToEdge / speed)),
      speed,
      fromPlanetId: f.fromPlanetId,
      distance: proj,
    });
  }
  return out.sort((a, b) => a.eta - b.eta);
}

export interface FleetTarget {
  planetId: number;
  planetOwner: number;
  eta: number;
  speed: number;
  distance: number;
}

/** Most likely destination for a fleet: smallest positive projected
 *  distance among planets whose perpendicular offset is within
 *  radius + buffer. Returns null if the fleet isn't headed toward any
 *  planet (e.g. mid-course before a tangent). */
export function computeFleetTarget(fleet: Fleet, planets: Planet[]): FleetTarget | null {
  const cos = Math.cos(fleet.angle);
  const sin = Math.sin(fleet.angle);
  const speed = fleetSpeed(fleet.ships);
  let best: FleetTarget | null = null;
  for (const p of planets) {
    const dx = p.x - fleet.x;
    const dy = p.y - fleet.y;
    const proj = dx * cos + dy * sin;
    if (proj <= 0) continue;
    const perp = Math.abs(dx * sin - dy * cos);
    if (perp > p.radius + 1.5) continue;
    const distToEdge = Math.max(0, proj - p.radius);
    if (!best || distToEdge < best.distance) {
      best = {
        planetId: p.id,
        planetOwner: p.owner,
        eta: Math.max(1, Math.ceil(distToEdge / speed)),
        speed,
        distance: distToEdge,
      };
    }
  }
  return best;
}

// ============================================================
// Selection state (persisted in localStorage)
// ============================================================

export type SelectionEntry =
  | { kind: "planet"; id: number }
  | { kind: "fleet"; id: number };

const STORAGE_KEY = "ow-selection";

export function readSelections(): SelectionEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const v = JSON.parse(raw);
    if (Array.isArray(v)) {
      return v.filter(
        (e) => e && (e.kind === "planet" || e.kind === "fleet") && typeof e.id === "number",
      );
    }
    // Legacy single-entry shape — migrate forward on read.
    if (v && (v.kind === "planet" || v.kind === "fleet") && typeof v.id === "number") {
      return [{ kind: v.kind, id: v.id }];
    }
  } catch { /* corrupt json — treat as empty */ }
  return [];
}

export function writeSelections(list: SelectionEntry[]): void {
  if (list.length === 0) localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

export function toggleSelection(
  list: SelectionEntry[],
  entry: SelectionEntry,
): SelectionEntry[] {
  const idx = list.findIndex((e) => e.kind === entry.kind && e.id === entry.id);
  if (idx >= 0) {
    const out = list.slice();
    out.splice(idx, 1);
    return out;
  }
  return [...list, entry];
}

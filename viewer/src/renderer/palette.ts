/**
 * Canvas palette + player colors for the Orbit Wars renderer.
 *
 * Dark palette matches the legacy look (black bg, cool-blue grid).
 * Light palette inverts — white bg with cool-blue low-alpha strokes.
 * Player colors (PLAYER_COLORS) stay constant across themes — saturated
 * enough to stay readable on both.
 */

export interface CanvasPalette {
  bg: string;
  gridMinor: string;
  gridMajor: string;
  boardBorder: string;
  orbit: string;
  cometOrbit: string;
  /** Trajectory alpha varies per-step; store r/g/b and build rgba at call site. */
  trajectoryRGB: [number, number, number];
  trajectoryGlow: string;
  fleetText: string;
  selection: string;
}

export const CANVAS_DARK: CanvasPalette = {
  bg: '#000000',
  gridMinor: 'rgba(100, 120, 180, 0.08)',
  gridMajor: 'rgba(120, 150, 220, 0.22)',
  boardBorder: 'rgba(140, 170, 220, 0.35)',
  orbit: 'rgba(140, 170, 220, 0.14)',
  cometOrbit: 'rgba(180, 220, 255, 0.16)',
  trajectoryRGB: [200, 220, 255],
  trajectoryGlow: 'rgba(255, 255, 255, 0.55)',
  fleetText: 'rgba(180, 190, 220, 0.75)',
  selection: 'rgba(138, 196, 255, 0.95)',
};

export const CANVAS_LIGHT: CanvasPalette = {
  bg: '#ffffff',
  gridMinor: 'rgba(80, 100, 140, 0.08)',
  gridMajor: 'rgba(80, 100, 140, 0.22)',
  boardBorder: 'rgba(80, 100, 140, 0.35)',
  orbit: 'rgba(80, 100, 140, 0.22)',
  cometOrbit: 'rgba(60, 90, 140, 0.28)',
  trajectoryRGB: [80, 100, 140],
  trajectoryGlow: 'rgba(40, 60, 100, 0.55)',
  fleetText: 'rgba(60, 70, 90, 0.85)',
  selection: 'rgba(37, 99, 235, 0.95)',
};

export function getCanvasPalette(): CanvasPalette {
  const v = localStorage.getItem('ow-canvas-theme');
  return v === 'light' ? CANVAS_LIGHT : CANVAS_DARK;
}

export function trajectoryColor(palette: CanvasPalette, alpha: number): string {
  const [r, g, b] = palette.trajectoryRGB;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * 4-player palette, tuned for visibility on both dark and light canvas
 * backgrounds. Avoid Wong yellow/orange clash — swapped yellow → purple
 * and brightened for dark bg.
 */
export const PLAYER_COLORS = ['#5EA5FF', '#FF8A4C', '#5EED9F', '#C084FC'];
export const NEUTRAL_COLOR = '#666666';

export function getPlayerColor(owner: number): string {
  if (owner < 0 || owner >= PLAYER_COLORS.length) return NEUTRAL_COLOR;
  return PLAYER_COLORS[owner];
}

/** Step/planet/fleet/delta font-size multipliers, keyed by the
 *  "text-size" display setting. */
export const TEXT_SIZES: Record<string, number> = {
  small: 0.7,
  medium: 1.0,
  large: 1.4,
};

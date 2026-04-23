import { ReplayData, RawStep } from '../types';
/**
 * Validates step bounds and returns step data if valid.
 * Returns null if step is out of bounds or data is invalid.
 *
 * This function is designed for raw (untransformed) replay data where each step
 * is an array of player entries with observations.
 *
 * @param replay - The replay data object (typically raw/untransformed)
 * @param step - The step index to validate
 * @returns The step data (array of player entries) or null if invalid
 *
 * @example
 * ```ts
 * const stepData = getStepData(replay, step);
 * if (!stepData) return; // Early exit if invalid
 * const { observation } = stepData[0];
 * ```
 */
export declare function getStepData<TObservation = Record<string, unknown>>(replay: ReplayData<RawStep<TObservation>[]> | ReplayData<unknown> | undefined, step: number): RawStep<TObservation> | null;
/**
 * Creates or retrieves a canvas element by ID.
 * Handles canvas creation, sizing, and positioning.
 *
 * @param parent - Parent element to append canvas to
 * @param id - Canvas element ID
 * @param options - Optional width/height overrides
 * @returns Tuple of [canvas, context]
 *
 * @example
 * ```ts
 * const [canvas, ctx] = getCanvas(parent, 'my-canvas', { width: 800, height: 600 });
 * ```
 */
export declare function getCanvas(parent: HTMLElement, id: string, options?: {
    width?: number;
    height?: number;
}): [HTMLCanvasElement, CanvasRenderingContext2D | null];

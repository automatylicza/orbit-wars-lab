import { BaseGameStep, ReplayMode } from '../types';
export declare const TIME_PER_CHUNK = 120;
export declare const generateEaseInOutDelayDistribution: (chunkCount: number) => number[];
export declare const generateEaseInDelayDistribution: (chunkCount: number) => number[];
/**
 * By default, have each token render with an even amount of time between them
 */
export declare const generateDefaultDelayDistribution: (chunkCount: number) => number[];
/**
 * Determine how long a turn is based on how long it takes to render each chunk.
 */
export declare function defaultGetStepRenderTime(gameStep: BaseGameStep, replayMode: ReplayMode, speedModifier: number, defaultDuration?: number): number;

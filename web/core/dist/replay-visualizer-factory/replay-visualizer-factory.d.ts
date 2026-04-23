import { GameAdapter } from '../adapter';
import { BaseGameStep, ReplayData } from '../types';
import { ReplayVisualizer } from '../player/player';
/**
 * A factory to create a new ReplayVisualizer, automatically handling
 * HMR state persistence and cleanup.
 */
export declare function createReplayVisualizer<TSteps extends BaseGameStep[] = BaseGameStep[]>(container: HTMLElement, adapter: GameAdapter<TSteps>, options?: {
    transformer?: (replay: ReplayData) => ReplayData;
}): ReplayVisualizer<TSteps>;

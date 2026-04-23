import { GameAdapter } from '../adapter';
import { BaseGameStep, ReplayData } from '../types';
/**
 * ReplayVisualizer is a thin shell that:
 * - Creates the container DOM element
 * - Mounts the adapter with initial data
 * - Forwards postMessage data to the adapter
 * - Handles HMR cleanup
 *
 * All UI (controls, playback, ReasoningLogs) is handled by EpisodePlayer
 * inside the adapter (ReplayAdapter).
 */
export declare class ReplayVisualizer<TSteps extends BaseGameStep[] = BaseGameStep[]> {
    private container;
    private adapter;
    private replay;
    private agents;
    private step;
    private mounted;
    private hmrState?;
    private transformer?;
    private viewer;
    constructor(container: HTMLElement, adapter: GameAdapter<TSteps>, options?: {
        hmrState?: any;
        transformer?: (replay: ReplayData) => ReplayData;
    });
    private loadData;
    private handleMessage;
    private setData;
    setAgents(agents: any[]): void;
    /**
     * Public method to clean up all side effects (listeners, loops)
     * when the instance is about to be destroyed.
     * This is called by the factory during an HMR update.
     */
    cleanup(): void;
}

import { ReplayData, ReplayMode } from '../../types';
export interface PlayerState {
    step: number;
    playing: boolean;
    speed: number;
    replayMode: ReplayMode;
}
export interface ParentData {
    replay?: ReplayData;
    agents?: any[];
    parentHandlesUi: boolean;
}
export interface PlayerActions {
    play: () => void;
    pause: () => void;
    toggle: () => void;
    setStep: (step: number) => void;
    setSpeed: (speed: number) => void;
    setReplayMode: (mode: ReplayMode) => void;
    stepForward: () => void;
    stepBackward: () => void;
    restart: () => void;
    /**
     * Set playing state directly without starting/stopping playback scheduling.
     * Use this for renderers that manage their own playback (e.g., audio-driven).
     * For normal play/pause, use play() and pause() instead.
     */
    setPlayingState: (playing: boolean) => void;
    /**
     * Set the step without affecting playback state.
     * Use this for programmatic step changes (e.g., audio-driven advancement)
     * where you want to change the step but keep playing.
     */
    setStepOnly: (step: number) => void;
}
export interface UsePlayerControllerOptions {
    totalSteps: number;
    getStepDuration: (step: number, mode: ReplayMode, speed: number) => number;
    initial?: Partial<PlayerState>;
    onChange?: (state: PlayerState, changed: keyof PlayerState) => void;
}
export declare function usePlayerController(options: UsePlayerControllerOptions): [PlayerState, PlayerActions, ParentData];

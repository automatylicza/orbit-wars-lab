import { BaseGameStep, InterestingEvent, ReplayData, ReplayMode } from '../types';
import * as React from 'react';
/**
 * UI mode for playback controls and ReasoningLogs.
 * - 'inline': Classic inline controls below the game (no ReasoningLogs)
 * - 'side-panel': Full experience with ReasoningLogs and controls in side panel
 * - 'none': No UI (for externally-driven playback)
 */
export type UiMode = 'inline' | 'side-panel' | 'none';
export interface EpisodePlayerProps<TSteps extends BaseGameStep[] = BaseGameStep[]> {
    /** The replay data to visualize */
    replay?: ReplayData<TSteps>;
    /** Agent data for display */
    agents?: any[];
    /** The game name (e.g., 'werewolf', 'open_spiel_chess') */
    gameName: string;
    /** The game renderer component */
    GameRenderer: React.ComponentType<GameRendererProps<TSteps>>;
    /**
     * UI mode for controls and ReasoningLogs:
     * - 'inline': Classic inline controls below the game (no ReasoningLogs)
     * - 'side-panel': Full experience with ReasoningLogs and controls in side panel
     * - 'none': No UI (for externally-driven playback)
     * @default 'side-panel'
     */
    ui?: UiMode;
    /** Layout mode for side-panel: 'side-by-side' puts logs to the right, 'stacked' puts logs below */
    layout?: 'side-by-side' | 'stacked';
    /** Initial step to start at */
    initialStep?: number;
    /** Initial playback speed */
    initialSpeed?: number;
    /** Initial replay mode */
    initialReplayMode?: ReplayMode;
    /** Callback when step changes */
    onStepChange?: (step: number) => void;
    /** Callback when playing state changes */
    onPlayingChange?: (playing: boolean) => void;
    /** Callback when speed changes */
    onSpeedChange?: (speed: number) => void;
    /** Container style */
    style?: React.CSSProperties;
    /** Container class name */
    className?: string;
    /**
     * If true, skip internal transformation (replay is already transformed).
     * Used by ReplayAdapter which handles transformation itself.
     */
    skipTransform?: boolean;
    /** Game-specific step label function for ReasoningLogs. Falls back to default if not provided. */
    getStepLabel?: (step: BaseGameStep) => string;
    /** Game-specific step description function for ReasoningLogs. Falls back to default if not provided. */
    getStepDescription?: (step: BaseGameStep) => string;
    /** Game-specific step render time function. Falls back to default if not provided. */
    getStepRenderTime?: (step: BaseGameStep, replayMode: ReplayMode, speedModifier: number) => number;
    /** Game-specific interesting events function. Falls back to default if not provided. */
    getInterestingEvents?: (steps: BaseGameStep[]) => InterestingEvent[];
    /** Game-specific token render distribution for streaming text. Falls back to default if not provided. */
    getTokenRenderDistribution?: (chunkCount: number) => number[];
    /** Whether to use a compact/dense layout for playback controls */
    dense?: boolean;
}
export interface GameRendererProps<TSteps extends BaseGameStep[] = BaseGameStep[]> {
    replay: ReplayData<TSteps>;
    step: number;
    agents: any[];
    /** Callback to set the current step */
    onSetStep?: (step: number) => void;
    /** Callback to set playing state (true = playing, false = paused) */
    onSetPlaying?: (playing: boolean) => void;
    /** Callback to register playback handlers (for renderers that need to intercept play/pause) */
    onRegisterPlaybackHandlers?: (handlers: {
        onPlay?: () => boolean | void;
        onPause?: () => void;
    }) => void;
    /** Callback to announce a message to screen readers via the aria-live region */
    onAnnounce?: (message: string) => void;
}
export declare function EpisodePlayer<TSteps extends BaseGameStep[] = BaseGameStep[]>({ replay: rawReplay, agents, gameName, GameRenderer, ui, initialStep, initialSpeed, initialReplayMode, onStepChange, onPlayingChange, onSpeedChange, style, className, skipTransform, getStepLabel, getStepDescription, getStepRenderTime: getStepRenderTimeProp, getInterestingEvents: getInterestingEventsProp, getTokenRenderDistribution, dense, }: EpisodePlayerProps<TSteps>): import("react/jsx-runtime").JSX.Element;

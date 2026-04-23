import { GameAdapter } from '../adapter';
import { BaseGameStep, InterestingEvent, ReplayData, ReplayMode } from '../types';
import { GameRendererProps, UiMode } from '../components/EpisodePlayer';
import * as React from 'react';
/** Transformer function type for processing replay data */
export type ReplayTransformer<TSteps = BaseGameStep[]> = (replay: ReplayData, gameName: string) => ReplayData<TSteps>;
/**
 * Playback control handlers that renderers can register to intercept playback actions.
 * These are called before the default behavior, allowing renderers to take over playback.
 */
export interface PlaybackHandlers {
    /**
     * Called when play is triggered.
     * Return `true` to indicate the handler took over playback (default playback is skipped).
     * Return `false` or `undefined` to allow default playback to proceed.
     */
    onPlay?: () => boolean | void;
    /**
     * Called when pause is triggered. The renderer can perform
     * additional cleanup (e.g., stopping audio). Default pause always runs after.
     */
    onPause?: () => void;
}
/**
 * Options passed to renderer functions.
 * This interface is used by LegacyRendererWrapper to call existing game renderers.
 */
export interface RendererOptions<TSteps = BaseGameStep[]> {
    /** Container element to render into */
    parent: HTMLElement;
    /** The full replay data (use replay.steps for step data) */
    replay: ReplayData<TSteps>;
    /** Agent metadata for legend rendering */
    agents: any[];
    /** Current step index */
    step: number;
    /** Jump to a specific step */
    setStep: (step: number) => void;
    /** Update the playing state (true = playing, false = paused) */
    setPlaying: (playing: boolean) => void;
    /**
     * Register handlers to intercept playback actions.
     * Renderers that need to control playback (e.g., for audio-driven playback)
     * can call this to register their handlers.
     */
    registerPlaybackHandlers: (handlers: PlaybackHandlers) => void;
}
/**
 * Props passed to a custom UI component when using `ui: CustomComponent`.
 * This allows full customization of playback controls and logs display.
 */
export interface PlaybackUiProps {
    /** Close/hide the UI panel */
    closePanel: () => void;
    /** Toggle or set playback state */
    onPlayChange: (playing?: boolean) => void;
    /** Set playback speed */
    onSpeedChange: (speed: number) => void;
    /** Jump to a specific step */
    onStepChange: (step: number) => void;
    /** Whether currently playing */
    playing: boolean;
    /** Current playback speed */
    speed: number;
    /** Total number of steps */
    totalSteps: number;
    /** Current step index */
    currentStep: number;
    /** The processed replay data */
    replay: ReplayData;
    /** Game name for display/timing */
    gameName: string;
}
/**
 * Renderer function signature.
 * This allows existing game renderers to work without modification.
 */
export type RendererFn<TSteps = BaseGameStep[]> = (options: RendererOptions<TSteps>, container?: HTMLElement) => void;
/**
 * Options for ReplayAdapter.
 * Provide EITHER `renderer` (legacy function) OR `GameRenderer` (React component).
 */
export interface ReplayAdapterOptions<TSteps extends BaseGameStep[] = BaseGameStep[]> {
    /** The game name for transformer/timing lookup */
    gameName: string;
    /**
     * DOM-based renderer function.
     * Use this to keep your game visualizer free of React code.
     * The adapter will wrap it internally.
     */
    renderer?: RendererFn<TSteps>;
    /**
     * React component that renders the game.
     * Use this if you want to write your renderer in React.
     */
    GameRenderer?: React.ComponentType<GameRendererProps<TSteps>>;
    /**
     * Custom transformer function to process replay data before rendering.
     * If not provided, uses the default `processEpisodeData` with gameName.
     *
     * This is useful for game-specific data transformations that will
     * eventually live in the game's own folder.
     *
     * @example
     * ```ts
     * transformer: (replay) => myGameTransformer(replay)
     * ```
     */
    transformer?: ReplayTransformer<TSteps>;
    /**
     * UI mode for playback controls and ReasoningLogs:
     * - 'inline': Classic inline controls below the game (no ReasoningLogs)
     * - 'side-panel': Full experience with ReasoningLogs and controls in side panel (default)
     * - 'none': No UI (for externally-driven playback)
     * - Custom React component: Provide your own UI component
     *
     * @default 'side-panel'
     */
    ui?: UiMode | React.ComponentType<PlaybackUiProps>;
    /** Layout mode: 'side-by-side' puts logs to the right, 'stacked' puts logs below */
    layout?: 'side-by-side' | 'stacked';
    /** Initial playback speed (default: 1) */
    initialSpeed?: number;
    /** Game-specific step label shown in ReasoningLogs. Falls back to default if not provided. */
    getStepLabel?: (step: BaseGameStep) => string;
    /** Game-specific step description shown in ReasoningLogs. Falls back to default if not provided. */
    getStepDescription?: (step: BaseGameStep) => string;
    /** Game-specific step render time for playback pacing. Falls back to default if not provided. */
    getStepRenderTime?: (step: BaseGameStep, replayMode: ReplayMode, speedModifier: number) => number;
    /** Game-specific interesting events shown on the playback slider. Falls back to default if not provided. */
    getInterestingEvents?: (steps: BaseGameStep[]) => InterestingEvent[];
    /** Game-specific token render distribution for streaming text in ReasoningLogs. Falls back to default if not provided. */
    getTokenRenderDistribution?: (chunkCount: number) => number[];
}
/**
 * ReplayAdapter is the unified adapter for game visualizers.
 *
 * It accepts EITHER a legacy renderer function OR a React component,
 * and provides configurable UI modes via the `ui` option.
 *
 * @example Full experience with side panel (default):
 * ```ts
 * new ReplayAdapter({
 *   gameName: 'chess',
 *   renderer: renderer,
 *   ui: 'side-panel', // default - shows ReasoningLogs and controls
 * })
 * ```
 *
 * @example Classic inline controls (no ReasoningLogs):
 * ```ts
 * new ReplayAdapter({
 *   gameName: 'chess',
 *   renderer: renderer,
 *   ui: 'inline',
 * })
 * ```
 *
 * @example No UI (externally-driven playback):
 * ```ts
 * new ReplayAdapter({
 *   gameName: 'chess',
 *   renderer: renderer,
 *   ui: 'none',
 * })
 * ```
 */
export declare class ReplayAdapter<TSteps extends BaseGameStep[] = BaseGameStep[]> implements GameAdapter<TSteps> {
    private root;
    private options;
    private rawReplay;
    private transformedReplay;
    private currentAgents;
    private wrappedRenderer;
    private currentTheme;
    private dense;
    private themeMessageHandler;
    constructor(options: ReplayAdapterOptions<TSteps>);
    /**
     * Apply the transformer to the replay data.
     * Uses custom transformer if provided, otherwise falls back to processEpisodeData.
     */
    private transformReplay;
    mount(container: HTMLElement, initialData?: ReplayData<TSteps>): void;
    render(_step: number, replay: ReplayData<TSteps>, agents: any[]): void;
    unmount(): void;
    /**
     * Render using EpisodePlayer which handles all UI modes.
     */
    private renderEpisodePlayer;
}

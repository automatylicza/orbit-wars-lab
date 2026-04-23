import { BaseGameStep, InterestingEvent, ReplayMode } from '../types';
import * as React from 'react';
export interface ReasoningLogsProps {
    closePanel: () => void;
    onPlayChange: (playing?: boolean) => void;
    onSpeedChange: (modifier: number) => void;
    onStepChange: (currentStep: number) => void;
    playing: boolean;
    replayMode: ReplayMode;
    setReplayMode: (streaming: ReplayMode) => void;
    speedModifier: number;
    totalSteps: number;
    steps: BaseGameStep[];
    currentStep: number;
    gameName: string;
    interestingEvents?: InterestingEvent[];
    /** Game-specific step label function. Falls back to default if not provided. */
    getStepLabel?: (step: BaseGameStep) => string;
    /** Game-specific step description function. Falls back to default if not provided. */
    getStepDescription?: (step: BaseGameStep) => string;
    /** Game-specific token render distribution for streaming text. Falls back to default if not provided. */
    getTokenRenderDistribution?: (chunkCount: number) => number[];
    /** Whether to use a compact/dense layout for playback controls */
    dense?: boolean;
}
export declare const ReasoningLogs: React.FC<ReasoningLogsProps>;

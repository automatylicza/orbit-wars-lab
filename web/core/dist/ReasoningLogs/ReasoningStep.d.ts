import { BaseGameStep, ReplayMode } from '../index';
import * as React from 'react';
export interface ReasoningStepProps {
    expandByDefault: boolean;
    isCurrentStep: boolean;
    showExpandButton?: boolean;
    step: BaseGameStep;
    stepNumber: number;
    replayMode: ReplayMode;
    scrollLogs: (forceScroll?: boolean) => void;
    playing: boolean;
    gameName: string;
    onStepChange: (step: number) => void;
    /** Game-specific step label function. Falls back to default if not provided. */
    getStepLabel?: (step: BaseGameStep) => string;
    /** Game-specific step description function. Falls back to default if not provided. */
    getStepDescription?: (step: BaseGameStep) => string;
    /** Game-specific token render distribution for streaming text. Falls back to default if not provided. */
    getTokenRenderDistribution?: (chunkCount: number) => number[];
}
export declare const ReasoningStep: React.FC<ReasoningStepProps>;

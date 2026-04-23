import * as React from 'react';
export interface PlaybackControlsProps {
    playing: boolean;
    currentStep: number;
    totalSteps: number;
    speedModifier: number;
    onPlayChange: (playing?: boolean) => void;
    onStepChange: (step: number) => void;
    onSpeedChange?: (speed: number) => void;
    className?: string;
    style?: React.CSSProperties;
}
export declare const PlaybackControls: React.FC<PlaybackControlsProps>;

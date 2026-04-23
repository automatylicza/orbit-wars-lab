import { BaseGameStep, InterestingEvent, ReplayData, ReplayMode } from '../types';
export declare const processEpisodeData: (environment: ReplayData, _gameName: string) => ReplayData<BaseGameStep[]>;
/**
 * A top level summary of the step. Usually the action taken
 * by the player whose turn it is.
 */
export declare const getGameStepLabel: (gameStep: BaseGameStep, _gameName: string) => string;
/**
 * More details on what happened during the step. Usually
 * the thoughts from the current player.
 */
export declare const getGameStepDescription: (gameStep: BaseGameStep, _gameName: string) => string;
export declare const getGameStepRenderTime: (gameStep: BaseGameStep, _gameName: string, replayMode: ReplayMode, speedModifier: number, defaultDuration?: number) => number;
export declare const getInterestingEvents: (_gameSteps: BaseGameStep[], _gameName: string) => InterestingEvent[];
export declare const getTokenRenderDistribution: (chunkCount: number, _gameName: string) => number[];

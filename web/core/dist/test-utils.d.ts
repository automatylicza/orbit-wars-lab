import { BaseGameStep, RawPlayerEntry, RawReplayData, ReplayData } from './types';
export declare const makeStep: (overrides?: Partial<BaseGameStep>) => BaseGameStep;
export declare const makeReplay: (overrides?: Partial<ReplayData>) => ReplayData;
export declare const makeEntry: (overrides?: Partial<RawPlayerEntry>) => RawPlayerEntry;
export declare const makeRawReplay: (overrides?: Partial<RawReplayData>) => RawReplayData;

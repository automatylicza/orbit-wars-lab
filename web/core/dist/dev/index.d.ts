import { ReplayData } from '../types';
interface HMRState {
    step?: number;
    playing?: boolean;
    speed?: number;
    replay?: ReplayData;
    agents?: any[];
}
declare global {
    interface Window {
        __hmrState?: HMRState;
    }
}
export {};

import { BaseGameStep, BaseGamePlayer } from '../types';
/**
 * Returns the player whose turn it is for the given step.
 * Returns undefined for system steps (no player has isTurn) so the UI shows "System".
 */
export declare function getPlayer(step: BaseGameStep): BaseGamePlayer | undefined;

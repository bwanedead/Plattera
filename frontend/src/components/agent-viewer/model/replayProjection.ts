/** Temporal replay projection — never substitute final or prior-turn state. */

export type ReplayProjectionStatus = 'loading' | 'available' | 'unavailable';

export type ReplayTurnProjection = {
  atTurn: number;
  maxTurn: number;
  status: ReplayProjectionStatus;
  turnSnapshot: Record<string, unknown> | null;
};

export function createReplayTurnProjection(
  atTurn: number,
  maxTurn: number,
  turnSnapshot: Record<string, unknown> | null,
  snapshotLoadStatus: ReplayProjectionStatus,
): ReplayTurnProjection {
  if (atTurn <= 0) {
    return { atTurn, maxTurn, status: 'unavailable', turnSnapshot: null };
  }
  if (maxTurn > 0 && atTurn >= maxTurn) {
    return { atTurn, maxTurn, status: 'available', turnSnapshot: null };
  }
  return {
    atTurn,
    maxTurn,
    status: snapshotLoadStatus,
    turnSnapshot: snapshotLoadStatus === 'available' ? turnSnapshot : null,
  };
}

export function replayProjectionIsReady(projection: ReplayTurnProjection): boolean {
  if (projection.atTurn <= 0) return true;
  if (projection.maxTurn > 0 && projection.atTurn >= projection.maxTurn) return true;
  return projection.status === 'available';
}

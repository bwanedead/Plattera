let bridgeRefCount = 0;

export function acquireClientLogBridgeRef(): void {
  bridgeRefCount += 1;
}

export function releaseClientLogBridgeRef(): void {
  bridgeRefCount = Math.max(0, bridgeRefCount - 1);
}

export function getClientLogBridgeRefCount(): number {
  return bridgeRefCount;
}

export function resetClientLogBridgeRefCountForTests(): void {
  bridgeRefCount = 0;
}

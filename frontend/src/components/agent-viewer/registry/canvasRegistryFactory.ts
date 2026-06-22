import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import {
  createCanvasRendererRegistry,
  type CanvasRendererRegistration,
  type CanvasRendererRegistry,
} from './canvasRendererRegistry';
import { defaultDomainAdapters } from './defaultDomainAdapters';
import { selectDomainAdapters } from './domainAdapters';

export function createCanvasRegistryForSnapshot(
  snapshot: AgentViewerSnapshot | null,
  baseRegistrations: CanvasRendererRegistration[] = [],
): CanvasRendererRegistry {
  const adapters = selectDomainAdapters(snapshot, defaultDomainAdapters);
  const domainCanvasRegs = adapters.flatMap((adapter) => adapter.canvasRegistrations || []);
  return createCanvasRendererRegistry([...domainCanvasRegs, ...baseRegistrations]);
}

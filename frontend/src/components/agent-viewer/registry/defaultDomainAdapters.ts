import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import type { AgentViewerDomainAdapter } from './domainAdapters';
import type { ViewerRendererRegistration } from './viewerRegistry';
import type { CanvasRendererRegistration } from './canvasRendererRegistry';
import { transcriptEditDomainAdapter } from '../renderers/domains/transcriptEdit/transcriptEditAdapter';

export type ExtendedDomainAdapter = AgentViewerDomainAdapter & {
  canvasRegistrations?: CanvasRendererRegistration[];
};

export const defaultDomainAdapters: ExtendedDomainAdapter[] = [transcriptEditDomainAdapter];

export function selectDomainAdapters(
  snapshot: AgentViewerSnapshot | null,
  adapters: ExtendedDomainAdapter[] = defaultDomainAdapters,
): ExtendedDomainAdapter[] {
  if (!snapshot) return [];
  return adapters
    .filter((adapter) => (adapter.matches ? adapter.matches(snapshot) : false))
    .sort((a, b) => (b.priority || 0) - (a.priority || 0));
}

export function inventoryRegistrationsForSnapshot(snapshot: AgentViewerSnapshot | null): ViewerRendererRegistration[] {
  return selectDomainAdapters(snapshot).flatMap((adapter) => adapter.registrations || []);
}

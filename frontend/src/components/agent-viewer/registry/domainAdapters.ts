import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import {
  createAgentViewerRegistry,
  type AgentViewerRegistry,
  type ViewerRendererRegistration,
} from './viewerRegistry';

export type AgentViewerDomainAdapter = {
  id: string;
  label: string;
  priority?: number;
  matches?: (snapshot: AgentViewerSnapshot) => boolean;
  registrations?: ViewerRendererRegistration[];
};

export function createRegistryForSnapshot(
  snapshot: AgentViewerSnapshot | null,
  adapters: AgentViewerDomainAdapter[] = [],
  baseRegistrations: ViewerRendererRegistration[] = [],
): AgentViewerRegistry {
  const activeAdapters = selectDomainAdapters(snapshot, adapters);
  const registrations = [
    ...activeAdapters.flatMap((adapter) => adapter.registrations || []),
    ...baseRegistrations,
  ];
  return createAgentViewerRegistry(registrations);
}

export function selectDomainAdapters(
  snapshot: AgentViewerSnapshot | null,
  adapters: AgentViewerDomainAdapter[],
): AgentViewerDomainAdapter[] {
  if (!snapshot) return [];
  return adapters
    .filter((adapter) => (adapter.matches ? adapter.matches(snapshot) : false))
    .sort((a, b) => (b.priority || 0) - (a.priority || 0));
}

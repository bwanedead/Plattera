import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import { transcriptEditDomainAdapter } from '../renderers/domains/transcriptEdit/transcriptEditAdapter';
import type { AgentViewerDomainAdapter } from './domainAdapters';
import type { CanvasRendererRegistration } from './canvasRendererRegistry';

export type ExtendedDomainAdapter = AgentViewerDomainAdapter & {
  canvasRegistrations?: CanvasRendererRegistration[];
};

export const defaultDomainAdapters: ExtendedDomainAdapter[] = [transcriptEditDomainAdapter];

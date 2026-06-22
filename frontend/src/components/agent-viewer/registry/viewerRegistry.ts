import { firstText } from '../model/modelUtils';

export type ViewerPrimitiveKind = 'artifact' | 'evidence' | 'work_item' | 'hitl_prompt' | 'action';

export type ViewerRegistryItem = {
  primitive: ViewerPrimitiveKind;
  id: string;
  kind?: string | null;
  title?: string | null;
  summary?: string | null;
  status?: string | null;
  ref?: string | null;
  payload?: Record<string, any>;
  raw: unknown;
};

export type ViewerInventoryPresentation = {
  title: string;
  subtitle?: string | null;
  badge?: string | null;
  status?: string | null;
  meta?: Record<string, any>;
};

export type ViewerRendererRegistration = {
  id: string;
  primitive: ViewerPrimitiveKind;
  priority?: number;
  matches?: (item: ViewerRegistryItem) => boolean;
  present?: (item: ViewerRegistryItem) => ViewerInventoryPresentation;
};

export type AgentViewerRegistry = {
  resolve: (item: ViewerRegistryItem) => ResolvedViewerRenderer;
  registrations: ViewerRendererRegistration[];
};

export type ResolvedViewerRenderer = {
  registration: ViewerRendererRegistration;
  presentation: ViewerInventoryPresentation;
};

export function createAgentViewerRegistry(registrations: ViewerRendererRegistration[] = []): AgentViewerRegistry {
  const all = [...registrations, ...fallbackRegistrations].sort((a, b) => (b.priority || 0) - (a.priority || 0));
  return {
    registrations: all,
    resolve: (item) => {
      const registration = all.find((candidate) => {
        if (candidate.primitive !== item.primitive) return false;
        return candidate.matches ? candidate.matches(item) : true;
      }) || fallbackFor(item.primitive);
      return {
        registration,
        presentation: registration.present ? registration.present(item) : fallbackPresentation(item),
      };
    },
  };
}

export const defaultAgentViewerRegistry = createAgentViewerRegistry();

const fallbackRegistrations: ViewerRendererRegistration[] = [
  {
    id: 'artifact:fallback',
    primitive: 'artifact',
    priority: -100,
    present: fallbackPresentation,
  },
  {
    id: 'evidence:fallback',
    primitive: 'evidence',
    priority: -100,
    present: fallbackPresentation,
  },
  {
    id: 'work_item:fallback',
    primitive: 'work_item',
    priority: -100,
    present: fallbackPresentation,
  },
  {
    id: 'hitl_prompt:fallback',
    primitive: 'hitl_prompt',
    priority: -100,
    present: fallbackPresentation,
  },
  {
    id: 'action:fallback',
    primitive: 'action',
    priority: -100,
    present: fallbackPresentation,
  },
];

function fallbackFor(primitive: ViewerPrimitiveKind): ViewerRendererRegistration {
  return fallbackRegistrations.find((registration) => registration.primitive === primitive) || fallbackRegistrations[0];
}

function fallbackPresentation(item: ViewerRegistryItem): ViewerInventoryPresentation {
  const title = firstText(item.title, item.summary, item.ref, item.id, item.kind, item.primitive);
  return {
    title,
    subtitle: firstText(item.summary, item.ref, item.kind) || null,
    badge: firstText(item.kind, item.primitive) || null,
    status: firstText(item.status) || null,
  };
}


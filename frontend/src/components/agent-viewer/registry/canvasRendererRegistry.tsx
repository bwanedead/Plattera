import React from 'react';
import type { ArtifactLoadResult } from '../model/artifactLoadResult';
import type { ViewerSelection } from '../selection/selectionTypes';
import { ImageArtifactRenderer } from '../renderers/generic/ImageArtifactRenderer';
import { JsonTreeView } from '../renderers/generic/JsonTreeView';
import { TextArtifactRenderer } from '../renderers/generic/TextArtifactRenderer';
import { UnknownKindRenderer } from '../renderers/generic/UnknownKindRenderer';
import { extractGenericText } from '../renderers/generic/textExtraction';

export type CanvasRenderContext = {
  selection: ViewerSelection;
  artifact: ArtifactLoadResult | null;
  loading: boolean;
};

export type CanvasRendererRegistration = {
  id: string;
  priority?: number;
  matches: (ctx: CanvasRenderContext) => boolean;
  render: (ctx: CanvasRenderContext) => React.ReactNode;
};

export type CanvasRendererRegistry = {
  resolve: (ctx: CanvasRenderContext) => CanvasRendererRegistration;
  render: (ctx: CanvasRenderContext) => React.ReactNode;
};

const genericCanvasRenderers: CanvasRendererRegistration[] = [
  {
    id: 'canvas:event',
    priority: 100,
    matches: ({ selection }) => selection.kind === 'event',
    render: ({ selection }) => (
      <div className="av-event-canvas">
        <div className="av-event-canvas-title">{selection.label}</div>
        <JsonTreeView value={selection.payload?.event ?? selection.payload ?? {}} maxDepth={6} />
      </div>
    ),
  },
  {
    id: 'canvas:work_item',
    priority: 90,
    matches: ({ selection }) => selection.kind === 'work_item',
    render: ({ selection }) => (
      <div className="av-work-item-canvas">
        <div className="av-event-canvas-title">{selection.label}</div>
        <JsonTreeView value={selection.payload?.raw ?? selection.payload ?? {}} maxDepth={6} />
      </div>
    ),
  },
  {
    id: 'canvas:inventory_raw',
    priority: 85,
    matches: ({ selection }) => ['hitl', 'action', 'evidence'].includes(selection.kind),
    render: ({ selection }) => (
      <div className="av-work-item-canvas">
        <div className="av-event-canvas-title">{selection.label}</div>
        <JsonTreeView value={selection.payload?.raw ?? selection.payload ?? {}} maxDepth={6} />
      </div>
    ),
  },
  {
    id: 'canvas:image',
    priority: 80,
    matches: ({ artifact }) => artifact?.kind === 'image',
    render: ({ artifact, selection }) =>
      artifact?.kind === 'image' ? (
        <ImageArtifactRenderer url={artifact.url} title={selection.label} meta={{ sourcePath: artifact.sourcePath }} />
      ) : null,
  },
  {
    id: 'canvas:json_text',
    priority: 70,
    matches: ({ artifact }) => {
      if (artifact?.kind !== 'json') return false;
      return Boolean(extractGenericText(artifact.json));
    },
    render: ({ artifact, selection }) => {
      if (artifact?.kind !== 'json') return null;
      const text = extractGenericText(artifact.json);
      return text ? <TextArtifactRenderer text={text} title={selection.label || artifact.ref} /> : null;
    },
  },
  {
    id: 'canvas:json',
    priority: 60,
    matches: ({ artifact }) => artifact?.kind === 'json',
    render: ({ artifact }) => (artifact?.kind === 'json' ? <JsonTreeView value={artifact.json} maxDepth={7} /> : null),
  },
  {
    id: 'canvas:unresolved',
    priority: -100,
    matches: () => true,
    render: ({ artifact, selection }) => (
      <UnknownKindRenderer
        title={selection.label}
        refId={selection.ref || selection.id}
        payload={selection.payload?.raw ?? selection.payload}
        reason={artifact?.kind === 'unresolved' ? artifact.reason : 'Artifact not loaded'}
      />
    ),
  },
];

export function createCanvasRendererRegistry(
  registrations: CanvasRendererRegistration[] = [],
): CanvasRendererRegistry {
  const all = [...registrations, ...genericCanvasRenderers].sort((a, b) => (b.priority || 0) - (a.priority || 0));
  return {
    resolve: (ctx) => all.find((registration) => registration.matches(ctx)) || genericCanvasRenderers.at(-1)!,
    render: (ctx) => {
      const registration = all.find((candidate) => candidate.matches(ctx)) || genericCanvasRenderers.at(-1)!;
      return registration.render(ctx);
    },
  };
}

export const defaultCanvasRendererRegistry = createCanvasRendererRegistry();

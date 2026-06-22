import React from 'react';
import { ImageArtifactRenderer } from '../renderers/generic/ImageArtifactRenderer';
import { JsonTreeView } from '../renderers/generic/JsonTreeView';
import { TextArtifactRenderer } from '../renderers/generic/TextArtifactRenderer';
import { UnknownKindRenderer } from '../renderers/generic/UnknownKindRenderer';
import type { ViewerSelection } from '../selection/selectionTypes';
import type { ReplayArtifactResult } from '../transport/replay/replayArtifactGateway';

type ArtifactCanvasProps = {
  selection: ViewerSelection | null;
  followLive: boolean;
  onResumeFollowLive: () => void;
  loadArtifact?: (ref: string) => Promise<ReplayArtifactResult>;
};

export function ArtifactCanvas({ selection, followLive, onResumeFollowLive, loadArtifact }: ArtifactCanvasProps) {
  const [artifactState, setArtifactState] = React.useState<ReplayArtifactResult | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!selection || !loadArtifact) {
      setArtifactState(null);
      return;
    }
    const ref = selection.ref || (selection.kind === 'artifact' ? selection.id : null);
    if (!ref) {
      setArtifactState(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    loadArtifact(ref)
      .then((result) => {
        if (!cancelled) setArtifactState(result);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadArtifact, selection]);

  return (
    <div className="av-artifact-canvas">
      <div className="av-canvas-toolbar">
        <div className="av-canvas-title">{selection?.label || 'Universal canvas'}</div>
        {!followLive ? (
          <button type="button" className="av-button av-button-ghost" onClick={onResumeFollowLive}>
            Return to live
          </button>
        ) : (
          <span className="av-follow-live">Following live attention</span>
        )}
      </div>

      <div className="av-canvas-body">
        {!selection ? <div className="av-empty-panel">Select a turn, artifact, or resolution item to inspect.</div> : null}
        {selection?.kind === 'event' ? <EventCanvas selection={selection} /> : null}
        {selection && (selection.kind === 'artifact' || selection.ref) ? (
          <ArtifactBody loading={loading} artifact={artifactState} selection={selection} />
        ) : null}
        {selection?.kind === 'work_item' ? <WorkItemCanvas selection={selection} /> : null}
      </div>
    </div>
  );
}

function EventCanvas({ selection }: { selection: ViewerSelection }) {
  const event = selection.payload?.event;
  return (
    <div className="av-event-canvas">
      <div className="av-event-canvas-title">{selection.label}</div>
      <JsonTreeView value={event ?? selection.payload ?? {}} maxDepth={6} />
    </div>
  );
}

function WorkItemCanvas({ selection }: { selection: ViewerSelection }) {
  return (
    <div className="av-work-item-canvas">
      <div className="av-event-canvas-title">{selection.label}</div>
      <JsonTreeView value={selection.payload?.raw ?? selection.payload ?? {}} maxDepth={6} />
    </div>
  );
}

function ArtifactBody({
  loading,
  artifact,
  selection,
}: {
  loading: boolean;
  artifact: ReplayArtifactResult | null;
  selection: ViewerSelection;
}) {
  if (loading) return <div className="av-empty-panel">Loading artifact…</div>;
  if (!artifact) {
    return (
      <UnknownKindRenderer
        title={selection.label}
        refId={selection.ref || selection.id}
        payload={selection.payload?.raw ?? selection.payload}
        reason="Artifact not loaded"
      />
    );
  }

  if (artifact.kind === 'image') {
    return <ImageArtifactRenderer url={artifact.url} title={selection.label} meta={{ sourcePath: artifact.sourcePath }} />;
  }

  if (artifact.kind === 'json') {
    const text = extractText(artifact.json);
    if (text) {
      return <TextArtifactRenderer text={text} title={selection.label || artifact.ref} />;
    }
    return <JsonTreeView value={artifact.json} maxDepth={7} />;
  }

  return <UnknownKindRenderer title={selection.label} refId={artifact.ref} reason={artifact.reason} />;
}

function extractText(value: unknown): string | null {
  if (typeof value === 'string') return value;
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  const candidates = ['text', 'transcript_text', 'content', 'body'];
  for (const key of candidates) {
    if (typeof record[key] === 'string' && record[key]) return record[key] as string;
  }
  const draft = record.draft_payload;
  if (draft && typeof draft === 'object') {
    const draftRecord = draft as Record<string, unknown>;
    if (typeof draftRecord.source_transcript_verbatim === 'string') {
      return draftRecord.source_transcript_verbatim;
    }
  }
  return null;
}

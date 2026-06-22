import React from 'react';
import type { ArtifactLoader } from '../model/artifactLoadResult';
import { defaultCanvasRendererRegistry } from '../registry/canvasRendererRegistry';
import type { ViewerSelection } from '../selection/selectionTypes';

type ArtifactCanvasProps = {
  selection: ViewerSelection | null;
  followLive: boolean;
  onResumeFollowLive: () => void;
  loadArtifact?: ArtifactLoader;
};

export function ArtifactCanvas({ selection, followLive, onResumeFollowLive, loadArtifact }: ArtifactCanvasProps) {
  const [artifactState, setArtifactState] = React.useState<Awaited<ReturnType<ArtifactLoader>> | null>(null);
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

  const rendered = selection
    ? defaultCanvasRendererRegistry.render({
        selection,
        artifact: artifactState,
        loading,
      })
    : null;

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
        {loading ? <div className="av-empty-panel">Loading artifact…</div> : rendered}
      </div>
    </div>
  );
}

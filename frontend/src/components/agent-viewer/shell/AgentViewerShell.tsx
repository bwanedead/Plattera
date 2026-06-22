import React from 'react';
import type { AgentViewerRunView } from '../hooks/useAgentViewerRun';
import { ActivityTimeline } from '../panels/ActivityTimeline';
import { ArtifactCanvas } from '../panels/ArtifactCanvas';
import { ReplayControls } from '../panels/ReplayControls';
import { ResolutionInspector } from '../panels/ResolutionInspector';
import { RunHeader } from '../panels/RunHeader';
import { useViewerSelection } from '../selection/useViewerSelection';

type AgentViewerShellProps = {
  run: AgentViewerRunView;
  onClose?: () => void;
};

export function AgentViewerShell({ run, onClose }: AgentViewerShellProps) {
  const { selection, followLive, select, selectLive, resumeFollowLive } = useViewerSelection();

  React.useEffect(() => {
    if (!followLive) return;
    const latest = run.orderedEvents[0];
    if (!latest) return;
    const turnIndex = latest.payload?.turn_index;
    selectLive({
      kind: 'event',
      id: typeof turnIndex === 'number' ? `turn-event-${turnIndex}` : `live-${latest.seq ?? 0}`,
      label: latest.status?.line1 || latest.event_type,
      payload: { event: latest, turn_index: turnIndex ?? null },
    });
  }, [followLive, run.orderedEvents, selectLive]);

  return (
    <div className="av-shell">
      <RunHeader
        snapshot={run.snapshot}
        mode={run.mode}
        connected={run.connected}
        loading={run.loading}
        error={run.error}
        onClose={onClose}
      />

      {run.mode === 'replay' && run.replay ? (
        <ReplayControls
          playback={run.replay.playback}
          onPlay={run.replay.play}
          onPause={run.replay.pause}
          onStepForward={run.replay.stepForward}
          onStepBackward={run.replay.stepBackward}
          onScrub={run.replay.scrubToTurn}
          onRestart={run.replay.restart}
        />
      ) : null}

      <div className="av-shell-grid">
        <section className="av-panel">
          <div className="av-panel-header">Activity</div>
          <div className="av-panel-body">
            <ActivityTimeline events={run.orderedEvents} selection={selection} onSelect={select} />
          </div>
        </section>

        <section className="av-panel">
          <div className="av-panel-header">Canvas</div>
          <div className="av-panel-body" style={{ padding: 0, display: 'flex', flexDirection: 'column' }}>
            <ArtifactCanvas
              selection={selection}
              followLive={followLive}
              onResumeFollowLive={resumeFollowLive}
              loadArtifact={run.loadArtifact}
            />
          </div>
        </section>

        <section className="av-panel">
          <div className="av-panel-header">State & Inventory</div>
          <div className="av-panel-body">
            <ResolutionInspector
              sections={run.snapshotView.inventorySections}
              selection={selection}
              onSelect={select}
            />
          </div>
        </section>
      </div>
    </div>
  );
}

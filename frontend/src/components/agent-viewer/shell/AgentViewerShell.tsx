import React from 'react';
import type { AgentViewerRunView } from '../hooks/useAgentViewerRun';
import { useAgentViewerActions } from '../hooks/useAgentViewerActions';
import { useAgentViewerInteraction } from '../hooks/useAgentViewerInteraction';
import { useAgentViewerShellState } from '../hooks/useAgentViewerShellState';
import { buildAttentionItems } from '../model/attentionModel';
import { buildObservabilityView } from '../model/observabilityModel';
import { workItemsToViews } from '../model/normalizeWorkItems';
import { buildOutcomeView, deriveRunPosture } from '../model/runPosture';
import { createCanvasRegistryForSnapshot } from '../registry/canvasRegistryFactory';
import { ActivityTimeline } from '../panels/ActivityTimeline';
import { ActionBar } from '../panels/ActionBar';
import { ArtifactCanvas } from '../panels/ArtifactCanvas';
import { AttentionStrip } from '../panels/AttentionStrip';
import { ChapterRail } from '../panels/ChapterRail';
import { InteractionTray } from '../panels/InteractionTray';
import { ObservabilityDrawer } from '../panels/ObservabilityDrawer';
import { OutcomePanel } from '../panels/OutcomePanel';
import { RawInspector } from '../panels/RawInspector';
import { ResolutionInspector } from '../panels/ResolutionInspector';
import { RunHeader } from '../panels/RunHeader';
import { WorkItemInspector } from '../panels/WorkItemInspector';
import { ReplayControls } from '../transport/replay/ReplayControls';

type AgentViewerShellProps = {
  run: AgentViewerRunView;
  onClose?: () => void;
};

export function AgentViewerShell({ run, onClose }: AgentViewerShellProps) {
  const shell = useAgentViewerShellState({ orderedEvents: run.orderedEvents });
  const {
    selection,
    followLive,
    select,
    resumeFollowLive,
    rawOpen,
    toggleRaw,
    observabilityOpen,
    toggleObservability,
  } = shell;

  const canvasRegistry = React.useMemo(
    () => createCanvasRegistryForSnapshot(run.snapshot),
    [run.snapshot],
  );

  const workItemViews = React.useMemo(
    () => workItemsToViews(run.snapshot?.work_items ?? []),
    [run.snapshot?.work_items],
  );

  const attentionItems = React.useMemo(
    () => buildAttentionItems(run.snapshot, run.orderedEvents),
    [run.orderedEvents, run.snapshot],
  );

  const outcome = React.useMemo(() => buildOutcomeView(run.snapshot), [run.snapshot]);

  const observability = React.useMemo(
    () =>
      buildObservabilityView(
        run.snapshot,
        run.orderedEvents,
        run.replay?.bundle ?? null,
        run.replay?.playback.currentTurn ?? null,
      ),
    [run.orderedEvents, run.replay?.bundle, run.replay?.playback.currentTurn, run.snapshot],
  );

  const interaction = useAgentViewerInteraction({
    mode: run.mode,
    isOpen: true,
    loopKind: run.loopKind,
    runId: run.runId,
    snapshot: run.snapshot,
    events: run.orderedEvents,
    selection,
  });

  const actionContext = React.useMemo(
    () => ({
      select,
      refreshSnapshot: run.refreshSnapshot,
      replay: run.replay
        ? {
            restart: run.replay.restart,
            scrubToTurn: run.replay.scrubToTurn,
          }
        : undefined,
    }),
    [run.refreshSnapshot, run.replay, select],
  );

  const viewerActions = useAgentViewerActions({
    snapshot: run.snapshot,
    context: actionContext,
  });

  const posture = React.useMemo(
    () =>
      deriveRunPosture({
        loading: run.loading,
        error: run.error,
        connected: run.connected,
        snapshot: run.snapshot,
        activeHitl: interaction.activePrompt,
      }),
    [interaction.activePrompt, run.connected, run.error, run.loading, run.snapshot],
  );

  const handleSelectChapter = React.useCallback(
    (chapter: { id: string; title: string; artifact_refs?: string[] }) => {
      const firstRef = chapter.artifact_refs?.[0];
      if (firstRef) {
        select({
          kind: 'artifact',
          id: firstRef,
          ref: firstRef,
          label: chapter.title,
        });
        return;
      }
      select({
        kind: 'raw',
        id: `chapter:${chapter.id}`,
        label: chapter.title,
        payload: { chapterId: chapter.id, chapter },
      });
    },
    [select],
  );

  return (
    <div className="av-shell">
      <RunHeader
        snapshot={run.snapshot}
        mode={run.mode}
        connected={run.connected}
        loading={run.loading}
        error={run.error}
        posture={posture}
        observabilityOpen={observabilityOpen}
        onToggleObservability={toggleObservability}
        onClose={onClose}
      />

      <ChapterRail
        chapters={run.snapshot?.chapters ?? []}
        activeChapterId={run.snapshot?.run.active_chapter_id ?? null}
        onSelectChapter={handleSelectChapter}
      />

      <ActionBar
        actions={viewerActions.actions}
        busyId={viewerActions.busyId}
        lastResult={viewerActions.lastResult}
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

      <AttentionStrip
        items={attentionItems}
        selection={selection}
        onSelectRef={(ref, label) =>
          select({
            kind: 'artifact',
            id: ref,
            ref,
            label,
          })
        }
      />

      <div className="av-shell-grid">
        <section className="av-panel">
          <div className="av-panel-header">Activity</div>
          <div className="av-panel-body">
            <ActivityTimeline events={run.orderedEvents} selection={selection} onSelect={select} />
          </div>
        </section>

        <section className="av-panel av-panel-canvas">
          <div className="av-panel-header">Canvas</div>
          <div className="av-panel-body av-panel-body-canvas">
            <ArtifactCanvas
              selection={selection}
              followLive={followLive}
              onResumeFollowLive={resumeFollowLive}
              loadArtifact={run.loadArtifact}
              canvasRegistry={canvasRegistry}
              rawOpen={rawOpen}
              onToggleRaw={toggleRaw}
            />
            <RawInspector selection={rawOpen ? selection : null} />
          </div>
        </section>

        <section className="av-panel">
          <div className="av-panel-header">Resolution & Inventory</div>
          <div className="av-panel-body">
            <WorkItemInspector items={workItemViews} selection={selection} onSelect={select} />
            <ResolutionInspector
              sections={run.snapshotView.inventorySections}
              selection={selection}
              onSelect={select}
            />
          </div>
        </section>
      </div>

      <OutcomePanel outcome={outcome} />

      <InteractionTray
        activePrompt={interaction.activePrompt}
        note={interaction.note}
        onNoteChange={interaction.setNote}
        busy={interaction.busy}
        error={interaction.error}
        receipt={interaction.receipt}
        pendingAcknowledgment={interaction.hasPendingSubmissionForActivePrompt}
        onSubmitChoice={(choice) => interaction.submitPromptAnswer(choice)}
        onSubmitSteering={interaction.submitSteeringMessage}
        selectionLabel={selection?.label || null}
      />

      <ObservabilityDrawer open={observabilityOpen} view={observability} onClose={toggleObservability} />
    </div>
  );
}

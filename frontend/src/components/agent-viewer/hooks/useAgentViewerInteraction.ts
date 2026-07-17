import React from 'react';
import {
  getAgentViewerFeedback,
  submitAgentViewerFeedback,
  type AgentViewerEvent,
  type AgentViewerFeedbackEntry,
  type AgentViewerLoopKind,
  type AgentViewerSnapshot,
} from '../../../services/agentViewerApi';
import {
  activeHitlPrompt,
  isSubmittedFeedbackEntry,
  resolvedPromptIdsFromEvents,
  resolvedPromptIdsFromFeedback,
} from '../model/normalizeHitl';
import type { NormalizedHitlPrompt } from '../model/viewTypes';
import type { ViewerSelection } from '../selection/selectionTypes';
import type { AgentViewerTransportMode } from './useAgentViewerRun';

type Params = {
  mode: AgentViewerTransportMode;
  isOpen: boolean;
  loopKind: AgentViewerLoopKind | null;
  runId: string | null;
  snapshot: AgentViewerSnapshot | null;
  events: AgentViewerEvent[];
  selection: ViewerSelection | null;
};

export function useAgentViewerInteraction({
  mode,
  isOpen,
  loopKind,
  runId,
  snapshot,
  events,
  selection,
}: Params) {
  const [entries, setEntries] = React.useState<AgentViewerFeedbackEntry[]>([]);
  const [note, setNote] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [receipt, setReceipt] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!isOpen || mode === 'replay' || !loopKind || !runId) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const feedback = await getAgentViewerFeedback(loopKind, runId);
        if (!cancelled) setEntries(Array.isArray(feedback.entries) ? feedback.entries : []);
      } catch {
        if (!cancelled) setEntries([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, loopKind, mode, runId]);

  const resolvedPromptIds = React.useMemo(() => {
    const fromEvents = resolvedPromptIdsFromEvents(events);
    const fromFeedback = resolvedPromptIdsFromFeedback(entries);
    return new Set([...fromEvents, ...fromFeedback]);
  }, [entries, events]);

  const pendingSubmissions = React.useMemo(() => {
    return entries.filter((entry) => isSubmittedFeedbackEntry(entry) && !resolvedPromptIdsFromFeedback([entry]).size);
  }, [entries]);

  const activePrompt = React.useMemo(
    () => activeHitlPrompt(snapshot, events, resolvedPromptIds),
    [events, resolvedPromptIds, snapshot],
  );

  const pendingPromptId = activePrompt?.promptId ?? null;
  const hasPendingSubmissionForActivePrompt = Boolean(
    pendingPromptId && pendingSubmissions.some((entry) => String(entry.prompt_id || '').trim() === pendingPromptId),
  );

  const submitPromptAnswer = React.useCallback(
    async (choice?: string | null) => {
      if (!loopKind || !runId || mode === 'replay') return;
      setBusy(true);
      setError(null);
      setReceipt(null);
      try {
        const response = await submitAgentViewerFeedback(loopKind, runId, {
          prompt_id: activePrompt?.promptId || null,
          choice: choice || null,
          note: note.trim() || null,
          metadata: {
            action: 'prompt_feedback',
            lifecycle: 'submitted',
            selection_kind: selection?.kind || null,
            selection_id: selection?.id || null,
            selection_ref: selection?.ref || null,
          },
        });
        setEntries((prev) => [response.entry, ...prev].slice(0, 40));
        setReceipt('Submitted. Pending transport and agent acknowledgment.');
        setNote('');
      } catch (submitError) {
        setError(submitError instanceof Error ? submitError.message : 'Failed to submit feedback');
      } finally {
        setBusy(false);
      }
    },
    [activePrompt?.promptId, loopKind, mode, note, runId, selection],
  );

  const submitSteeringMessage = React.useCallback(async () => {
    if (!loopKind || !runId || mode === 'replay' || !note.trim()) return;
    setBusy(true);
    setError(null);
    setReceipt(null);
    try {
      const response = await submitAgentViewerFeedback(loopKind, runId, {
        prompt_id: null,
        choice: null,
        note: note.trim(),
        metadata: {
          action: 'steering_message',
          lifecycle: 'submitted',
          selection_kind: selection?.kind || null,
          selection_id: selection?.id || null,
          selection_ref: selection?.ref || null,
        },
      });
      setEntries((prev) => [response.entry, ...prev].slice(0, 40));
      setReceipt('Message queued. It remains pending until surfaced to the agent.');
      setNote('');
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to send message');
    } finally {
      setBusy(false);
    }
  }, [loopKind, mode, note, runId, selection]);

  return {
    entries,
    note,
    setNote,
    busy,
    error,
    receipt,
    activePrompt,
    hasPendingSubmissionForActivePrompt,
    submitPromptAnswer,
    submitSteeringMessage,
  };
}

export type { NormalizedHitlPrompt };

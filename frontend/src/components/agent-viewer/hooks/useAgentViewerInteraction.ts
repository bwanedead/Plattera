import React from 'react';
import {
  getAgentViewerFeedback,
  submitAgentViewerFeedback,
  type AgentViewerEvent,
  type AgentViewerFeedbackEntry,
  type AgentViewerLoopKind,
  type AgentViewerSnapshot,
} from '../../../services/agentViewerApi';
import { activeHitlPrompt } from '../model/normalizeHitl';
import type { NormalizedHitlPrompt } from '../model/viewTypes';
import type { ViewerSelection } from '../selection/selectionTypes';

type Params = {
  isOpen: boolean;
  loopKind: AgentViewerLoopKind | null;
  runId: string | null;
  snapshot: AgentViewerSnapshot | null;
  events: AgentViewerEvent[];
  selection: ViewerSelection | null;
};

export function useAgentViewerInteraction({
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
    if (!isOpen || !loopKind || !runId) return;
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
  }, [isOpen, loopKind, runId]);

  const answeredPromptIds = React.useMemo(() => {
    return new Set(entries.map((entry) => String(entry.prompt_id || '').trim()).filter(Boolean));
  }, [entries]);

  const activePrompt = React.useMemo(
    () => activeHitlPrompt(snapshot, events, answeredPromptIds),
    [answeredPromptIds, events, snapshot],
  );

  const submitPromptAnswer = React.useCallback(
    async (choice?: string | null) => {
      if (!loopKind || !runId) return;
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
    [activePrompt?.promptId, loopKind, note, runId, selection],
  );

  const submitSteeringMessage = React.useCallback(async () => {
    if (!loopKind || !runId || !note.trim()) return;
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
  }, [loopKind, note, runId, selection]);

  return {
    entries,
    note,
    setNote,
    busy,
    error,
    receipt,
    activePrompt,
    submitPromptAnswer,
    submitSteeringMessage,
  };
}

export type { NormalizedHitlPrompt };

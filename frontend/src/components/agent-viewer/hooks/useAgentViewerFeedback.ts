import React from 'react';
import {
  getAgentViewerFeedback,
  submitAgentViewerFeedback,
  type AgentViewerEvent,
  type AgentViewerFeedbackEntry,
  type AgentViewerLoopKind,
} from '../../../services/agentViewerApi';

export type ActivePrompt = {
  promptId: string;
  blocking: boolean;
  line1: string;
  line2: string;
  choices: string[];
  context: Record<string, any>;
  evidenceRefs: string[];
  primaryEvidenceRef: string | null;
  annotatedEvidenceRef: string | null;
  questionRegions: string[];
  synthetic?: boolean;
};

type Params = {
  isOpen: boolean;
  activeLoopKind: AgentViewerLoopKind | null;
  activeRunId: string | null;
  isRunTerminal: boolean;
  allowTerminalFeedback: boolean;
  orderedEvents: AgentViewerEvent[];
  canvasMode: string;
};

export function useAgentViewerFeedback({
  isOpen,
  activeLoopKind,
  activeRunId,
  isRunTerminal,
  allowTerminalFeedback,
  orderedEvents,
  canvasMode,
}: Params) {
  const [feedbackEntries, setFeedbackEntries] = React.useState<AgentViewerFeedbackEntry[]>([]);
  const [feedbackNote, setFeedbackNote] = React.useState('');
  const [feedbackBusy, setFeedbackBusy] = React.useState(false);
  const [feedbackError, setFeedbackError] = React.useState<string | null>(null);
  const [promptReceipt, setPromptReceipt] = React.useState<string | null>(null);
  const [decisionOtherByKey, setDecisionOtherByKey] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) return;
    let cancelled = false;
    (async () => {
      try {
        const feedback = await getAgentViewerFeedback(activeLoopKind, activeRunId);
        if (!cancelled) {
          setFeedbackEntries(Array.isArray(feedback.entries) ? feedback.entries : []);
        }
      } catch {
        if (!cancelled) setFeedbackEntries([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeLoopKind, activeRunId]);

  const activeFeedbackPrompt = React.useMemo<ActivePrompt | null>(() => {
    if (isRunTerminal && !allowTerminalFeedback) return null;
    const answeredPromptIds = new Set(
      feedbackEntries.map((entry) => String(entry.prompt_id || '').trim()).filter(Boolean),
    );
    for (const evt of orderedEvents) {
      if (evt.event_type !== 'human_feedback_needed') continue;
      const promptId = typeof evt.payload?.prompt_id === 'string' ? evt.payload.prompt_id : '';
      if (!promptId) continue;
      const alreadyAnswered = answeredPromptIds.has(promptId);
      if (alreadyAnswered) continue;
      const choices = Array.isArray(evt.payload?.choices) ? evt.payload.choices.filter((c: any) => typeof c === 'string') : [];
      const context =
        evt.payload?.context && typeof evt.payload.context === 'object' && !Array.isArray(evt.payload.context)
          ? evt.payload.context
          : {};
      const primaryEvidenceRef =
        typeof context.primary_evidence_ref === 'string' && context.primary_evidence_ref.trim()
          ? context.primary_evidence_ref.trim()
          : null;
      const annotatedEvidenceRef =
        typeof context.annotated_evidence_ref === 'string' && context.annotated_evidence_ref.trim()
          ? context.annotated_evidence_ref.trim()
          : null;
      const evidenceRefs = collectArtifactRefs(context.evidence_refs, primaryEvidenceRef, annotatedEvidenceRef);
      const questionRegions = normalizePromptContextList(context.question_regions);
      return {
        promptId,
        blocking: Boolean(evt.payload?.blocking),
        line1: String(evt.status?.line1 || 'Human feedback needed'),
        line2: String(evt.status?.line2 || ''),
        choices: choices.slice(0, 8),
        context,
        evidenceRefs,
        primaryEvidenceRef,
        annotatedEvidenceRef,
        questionRegions,
        synthetic: false,
      };
    }
    return null;
  }, [orderedEvents, isRunTerminal, allowTerminalFeedback, feedbackEntries]);

  const activePromptSatisfied = React.useMemo(() => {
    if (!activeFeedbackPrompt?.promptId) return false;
    return feedbackEntries.some((entry) => String(entry.prompt_id || '') === activeFeedbackPrompt.promptId);
  }, [activeFeedbackPrompt, feedbackEntries]);

  const recentFeedbackEntries = React.useMemo(() => feedbackEntries.slice(0, 5), [feedbackEntries]);

  React.useEffect(() => {
    if (activeFeedbackPrompt) setPromptReceipt(null);
  }, [activeFeedbackPrompt]);

  const submitFeedback = React.useCallback(async (choice?: string) => {
    if (!activeLoopKind || !activeRunId) return null;
    setFeedbackBusy(true);
    setFeedbackError(null);
    setPromptReceipt(null);
    const activePromptId = activeFeedbackPrompt?.promptId || null;
    try {
      const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
        prompt_id: activePromptId,
        choice: choice || null,
        note: feedbackNote.trim() || null,
        metadata: {
          canvas_mode: canvasMode,
          event_count: orderedEvents.length,
          action: 'prompt_feedback',
          decision_key: inferDecisionKeyFromPromptId(activePromptId || '') || null,
        },
      });
      setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      if (activePromptId) {
        setPromptReceipt(`Received ${choice || 'feedback'}; queued for next checkpoint.`);
      }
      setFeedbackNote('');
      return {
        activePromptId,
        choice: choice || null,
      };
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : 'Failed to submit feedback');
      return null;
    } finally {
      setFeedbackBusy(false);
    }
  }, [activeLoopKind, activeRunId, activeFeedbackPrompt, feedbackNote, canvasMode, orderedEvents.length]);

  const resendFeedbackEntry = React.useCallback(
    async (entry: AgentViewerFeedbackEntry) => {
      if (!activeLoopKind || !activeRunId) return;
      setFeedbackBusy(true);
      setFeedbackError(null);
      try {
        const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
          prompt_id: entry.prompt_id || null,
          choice: entry.choice || null,
          note: entry.note || null,
          metadata: {
            ...(entry.metadata || {}),
            action: 'resend_feedback_entry',
          },
        });
        setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to resend feedback');
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeLoopKind, activeRunId],
  );

  const requestDecisionReview = React.useCallback(
    async (decisionKey: string) => {
      if (!activeLoopKind || !activeRunId) return;
      setFeedbackBusy(true);
      setFeedbackError(null);
      try {
        const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
          prompt_id: null,
          choice: null,
          note: `Please re-check decision key: ${decisionKey}`,
          metadata: {
            action: 'review_again',
            decision_key: decisionKey,
            source: 'decision_ledger_panel',
          },
        });
        setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to submit decision review');
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeLoopKind, activeRunId],
  );

  const submitDecisionResolution = React.useCallback(
    async (decisionKey: string, choice: string | null, extraNote?: string | null) => {
      if (!activeLoopKind || !activeRunId) return;
      const key = String(decisionKey || '').trim();
      if (!key) return;
      const chosen = choice ? String(choice).trim() : '';
      const otherRaw = String(decisionOtherByKey[key] || '').trim();
      const noteParts = [
        chosen ? `Resolved ${key} as: ${chosen}` : '',
        extraNote ? String(extraNote).trim() : '',
        !chosen && otherRaw ? `Resolved ${key} as: ${otherRaw}` : '',
      ].filter(Boolean);
      setFeedbackBusy(true);
      setFeedbackError(null);
      try {
        const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
          prompt_id: null,
          choice: chosen || null,
          note: noteParts.length ? noteParts.join(' | ') : null,
          metadata: {
            action: 'resolve_closure_requirement',
            decision_key: key,
            resolved_value: chosen || otherRaw || null,
            source: 'closure_requirement_panel',
          },
        });
        setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
        if (!chosen) {
          setDecisionOtherByKey((prev) => ({ ...prev, [key]: '' }));
        }
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to submit closure resolution');
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeLoopKind, activeRunId, decisionOtherByKey],
  );

  return {
    feedbackEntries,
    setFeedbackEntries,
    feedbackNote,
    setFeedbackNote,
    feedbackBusy,
    feedbackError,
    setFeedbackError,
    promptReceipt,
    setPromptReceipt,
    decisionOtherByKey,
    setDecisionOtherByKey,
    activeFeedbackPrompt,
    activePromptSatisfied,
    recentFeedbackEntries,
    submitFeedback,
    resendFeedbackEntry,
    requestDecisionReview,
    submitDecisionResolution,
  };
}

function inferDecisionKeyFromPromptId(promptId: string): string | null {
  const value = String(promptId || '').trim().toLowerCase();
  if (!value) return null;
  if (value.startsWith('closure_req_')) return value.replace('closure_req_', '').trim() || null;
  if (value.startsWith('hitl_range_')) return 'range';
  if (value.startsWith('hitl_township_')) return 'township';
  if (value.startsWith('hitl_section_')) return 'section';
  if (value.startsWith('hitl_tie_distance_')) return 'tie_distance';
  if (value.startsWith('hitl_tie_bearing_')) return 'tie_bearing';
  if (value.startsWith('hitl_closure_or_pob_')) return 'closure_or_pob';
  if (value.startsWith('hitl_acreage_')) return 'acreage';
  return null;
}

function collectArtifactRefs(
  raw: unknown,
  primaryEvidenceRef: string | null,
  annotatedEvidenceRef: string | null,
): string[] {
  const out = new Set<string>();
  for (const value of normalizePromptContextList(raw)) {
    out.add(value);
  }
  if (primaryEvidenceRef) out.add(primaryEvidenceRef);
  if (annotatedEvidenceRef) out.add(annotatedEvidenceRef);
  return Array.from(out).slice(0, 8);
}

function normalizePromptContextList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((value) => {
      if (typeof value === 'string') return value.trim();
      if (value && typeof value === 'object') return JSON.stringify(value);
      return '';
    })
    .filter(Boolean)
    .slice(0, 8);
}

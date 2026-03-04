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
  synthetic?: boolean;
};

type Params = {
  isOpen: boolean;
  activeLoopKind: AgentViewerLoopKind | null;
  activeRunId: string | null;
  isRunTerminal: boolean;
  orderedEvents: AgentViewerEvent[];
  canvasMode: string;
};

export function useAgentViewerFeedback({
  isOpen,
  activeLoopKind,
  activeRunId,
  isRunTerminal,
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
    if (isRunTerminal) return null;
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
      return {
        promptId,
        blocking: Boolean(evt.payload?.blocking),
        line1: String(evt.status?.line1 || 'Human feedback needed'),
        line2: String(evt.status?.line2 || ''),
        choices: choices.slice(0, 8),
        synthetic: false,
      };
    }
    const fallback = deriveClosurePromptFromEvents(orderedEvents, answeredPromptIds, feedbackEntries);
    if (fallback) return fallback;
    return null;
  }, [orderedEvents, isRunTerminal, feedbackEntries]);

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

type ClosureItem = {
  key: string;
  label: string;
  blocking: boolean;
  mappingBlocking: boolean;
  state: string;
  closureRequirement: Record<string, any> | null;
};

const KEY_PRIORITY: Record<string, number> = {
  township: 0,
  range: 1,
  section: 2,
  tie_distance: 3,
  tie_bearing: 4,
  closure_or_pob: 5,
  acreage: 6,
};

function deriveClosurePromptFromEvents(
  orderedEvents: AgentViewerEvent[],
  answeredPromptIds: Set<string>,
  feedbackEntries: AgentViewerFeedbackEntry[],
): ActivePrompt | null {
  const ledgerItems = extractLedgerItems(orderedEvents);
  if (ledgerItems.length === 0) return null;
  const resolvedKeys = new Set(
    feedbackEntries
      .map((entry) => String(entry.metadata?.decision_key || '').trim().toLowerCase())
      .filter(Boolean),
  );
  const candidates = ledgerItems
    .filter((item) => {
      const state = item.state.toLowerCase();
      const unresolved = state === 'disputed' || state === 'open' || state === 'unknown' || state === 'candidate_found' || state === 'accepted_with_risk';
      if (!unresolved) return false;
      if (!item.closureRequirement) return false;
      if (resolvedKeys.has(item.key.toLowerCase())) return false;
      return true;
    })
    .sort((a, b) => {
      if (a.mappingBlocking !== b.mappingBlocking) return a.mappingBlocking ? -1 : 1;
      if (a.blocking !== b.blocking) return a.blocking ? -1 : 1;
      const aReason = String(a.closureRequirement?.block_reason || '').toLowerCase();
      const bReason = String(b.closureRequirement?.block_reason || '').toLowerCase();
      const reasonRank = (r: string) => (r === 'contradiction' ? 0 : r === 'ambiguity' ? 1 : r === 'dependency' ? 2 : 3);
      const rr = reasonRank(aReason) - reasonRank(bReason);
      if (rr !== 0) return rr;
      return (KEY_PRIORITY[a.key] ?? 99) - (KEY_PRIORITY[b.key] ?? 99);
    });
  const mappingCandidates = candidates.filter((item) => item.mappingBlocking);
  const top = (mappingCandidates.length > 0 ? mappingCandidates[0] : candidates[0]) || null;
  if (!top) return null;
  const promptId = `closure_req_${top.key}`;
  if (answeredPromptIds.has(promptId)) return null;
  const req = top.closureRequirement || {};
  const choices = Array.isArray(req.resolution_options)
    ? req.resolution_options.filter((v: any) => typeof v === 'string').slice(0, 6)
    : [];
  return {
    promptId,
    blocking: Boolean(top.mappingBlocking || top.blocking),
    line1: String(req.required_information || `Resolve ${top.label} ambiguity.`),
    line2: String(req.minimal_user_action || 'Select the correct value, or provide Other.'),
    choices,
    synthetic: true,
  };
}

function extractLedgerItems(orderedEvents: AgentViewerEvent[]): ClosureItem[] {
  for (const evt of orderedEvents) {
    const detailLedger = evt.payload?.detail?.decision_ledger;
    const terminalLedger = evt.payload?.summary?.decision_ledger;
    const unresolvedFromSummary = evt.payload?.summary?.unresolved_closure_requirements;
    const itemsRaw =
      (detailLedger && Array.isArray(detailLedger.items) ? detailLedger.items : null)
      || (terminalLedger && Array.isArray(terminalLedger.items) ? terminalLedger.items : null);
    if (itemsRaw) {
      return itemsRaw
        .filter((item: any) => item && typeof item === 'object')
        .map((item: any) => ({
          key: String(item.key || ''),
          label: String(item.label || item.key || 'decision'),
          blocking: Boolean(item.blocking),
          mappingBlocking: Boolean(
            item.closure_requirement?.mapping_blocking ?? item.mapping_blocking ?? item.blocking,
          ),
          state: String(item.state || 'unknown'),
          closureRequirement: item.closure_requirement && typeof item.closure_requirement === 'object' ? item.closure_requirement : null,
        }))
        .filter((item: ClosureItem) => item.key);
    }
    if (Array.isArray(unresolvedFromSummary)) {
      return unresolvedFromSummary
        .filter((item: any) => item && typeof item === 'object')
        .map((item: any) => ({
          key: String(item.key || ''),
          label: String(item.label || item.key || 'decision'),
          blocking: Boolean(item.blocking),
          mappingBlocking: Boolean(
            item.closure_requirement?.mapping_blocking ?? item.mapping_blocking ?? item.blocking,
          ),
          state: String(item.state || 'unknown'),
          closureRequirement: item.closure_requirement && typeof item.closure_requirement === 'object' ? item.closure_requirement : null,
        }))
        .filter((item: ClosureItem) => item.key);
    }
  }
  return [];
}

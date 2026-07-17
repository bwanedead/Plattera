import type {
  AgentViewerEvent,
  AgentViewerHitlPrompt,
} from '../../../services/agentViewerApi';
import { firstText, isRecord } from './modelUtils';
import type { ReplayBundle, ReplayFeedbackFile } from '../transport/replay/replayTypes';

export type ReplayHitlExchange = {
  exchangeId: string;
  promptId: string;
  blocking: boolean;
  status: string;
  issuedAtTurn: number | null;
  consumedAtTurn: number | null;
  receivedAtTurn: number | null;
  question: string;
  detail: string | null;
  choices: string[];
  evidenceRefs: string[];
  responseChoice: string | null;
  responseNote: string | null;
  responseSubmittedAt: number | null;
  raw: Record<string, unknown>;
};

export function extractHitlExchangesFromTurnSnapshot(
  turnSnapshot: Record<string, unknown> | null,
): ReplayHitlExchange[] {
  if (!turnSnapshot) return [];
  const summary = turnSnapshot.prompt_observability_summary;
  if (!isRecord(summary)) return [];
  const exchanges = summary.recent_hitl_exchanges;
  if (!Array.isArray(exchanges)) return [];
  return exchanges
    .map((entry) => normalizeReplayExchange(entry))
    .filter((entry): entry is ReplayHitlExchange => Boolean(entry));
}

export function hitlExchangesVisibleAtTurn(
  exchanges: ReplayHitlExchange[],
  atTurn: number,
): ReplayHitlExchange[] {
  return exchanges.filter((exchange) => {
    if (exchange.issuedAtTurn == null) return false;
    return exchange.issuedAtTurn <= atTurn;
  });
}

export function hitlPromptsFromReplayExchanges(
  exchanges: ReplayHitlExchange[],
  atTurn: number,
): AgentViewerHitlPrompt[] {
  return hitlExchangesVisibleAtTurn(exchanges, atTurn)
    .filter((exchange) => exchange.status === 'pending')
    .map((exchange) => ({
      prompt_id: exchange.promptId,
      blocking: exchange.blocking,
      question: exchange.question,
      choices: exchange.choices,
      note_enabled: true,
      evidence_refs: exchange.evidenceRefs,
      affected_work_item_refs: [],
      context: {
        exchange_id: exchange.exchangeId,
        status: exchange.status,
        response_choice: exchange.responseChoice,
        response_note: exchange.responseNote,
      },
    }));
}

export function replayInteractionEventsUpToTurn(
  bundle: ReplayBundle,
  atTurn: number,
  exchanges: ReplayHitlExchange[],
): AgentViewerEvent[] {
  const source = bundle.manifest.source;
  const out: AgentViewerEvent[] = [];

  for (const exchange of exchanges) {
    if (exchange.issuedAtTurn == null || exchange.issuedAtTurn > atTurn) continue;

    out.push({
      protocol: 'agent_viewer_event_v1',
      run_id: source.run_id,
      loop_kind: source.domain_id,
      lane: 'interaction',
      lane_seq: exchange.issuedAtTurn,
      timestamp_epoch_seconds: exchange.responseSubmittedAt,
      event_type: 'human_feedback_needed',
      status: {
        stage: 'hitl',
        line1: exchange.question,
        line2: exchange.detail,
      },
      payload: {
        __replay: true,
        __view_id: `hitl-request-${exchange.promptId}-t${exchange.issuedAtTurn}`,
        turn_index: exchange.issuedAtTurn,
        prompt_id: exchange.promptId,
        blocking: exchange.blocking,
        choices: exchange.choices,
        lifecycle: 'requested',
        exchange_status: exchange.status,
        context: {
          evidence_refs: exchange.evidenceRefs,
        },
      },
    });

    if (exchange.status === 'answered' || exchange.responseChoice) {
      const responseTurn = exchange.receivedAtTurn ?? exchange.issuedAtTurn;
      if (responseTurn <= atTurn) {
        out.push({
          protocol: 'agent_viewer_event_v1',
          run_id: source.run_id,
          loop_kind: source.domain_id,
          lane: 'interaction',
          lane_seq: responseTurn,
          timestamp_epoch_seconds: exchange.responseSubmittedAt,
          event_type: 'human_feedback_submitted',
          status: {
            stage: 'hitl',
            line1: `Response submitted: ${exchange.responseChoice || 'note'}`,
            line2: exchange.responseNote,
          },
          payload: {
            __replay: true,
            __view_id: `hitl-submitted-${exchange.promptId}-t${responseTurn}`,
            turn_index: responseTurn,
            prompt_id: exchange.promptId,
            lifecycle: 'submitted',
            choice: exchange.responseChoice,
            note: exchange.responseNote,
          },
        });
      }
    }

    if (exchange.status === 'consumed' && exchange.consumedAtTurn != null && exchange.consumedAtTurn <= atTurn) {
      out.push({
        protocol: 'agent_viewer_event_v1',
        run_id: source.run_id,
        loop_kind: source.domain_id,
        lane: 'interaction',
        lane_seq: exchange.consumedAtTurn,
        event_type: 'human_feedback_consumed',
        status: {
          stage: 'hitl',
          line1: `HITL consumed: ${exchange.promptId}`,
          line2: exchange.responseChoice,
        },
        payload: {
          __replay: true,
          __view_id: `hitl-consumed-${exchange.promptId}-t${exchange.consumedAtTurn}`,
          turn_index: exchange.consumedAtTurn,
          prompt_id: exchange.promptId,
          lifecycle: 'consumed',
          choice: exchange.responseChoice,
        },
      });
    }
  }

  return out.sort((a, b) => {
    const at = a.timestamp_epoch_seconds ?? 0;
    const bt = b.timestamp_epoch_seconds ?? 0;
    return bt - at;
  });
}

export function mergeReplayFeedbackIntoExchanges(
  exchanges: ReplayHitlExchange[],
  feedback: ReplayFeedbackFile | null,
): ReplayHitlExchange[] {
  if (!feedback?.entries?.length) return exchanges;
  const byPrompt = new Map(exchanges.map((exchange) => [exchange.promptId, exchange]));
  for (const entry of feedback.entries) {
    const promptId = firstText(entry.prompt_id);
    if (!promptId) continue;
    const existing = byPrompt.get(promptId);
    if (existing) {
      existing.responseChoice = firstText(entry.choice) || existing.responseChoice;
      existing.responseNote = firstText(entry.note) || existing.responseNote;
      existing.responseSubmittedAt = entry.submitted_at_epoch_seconds ?? existing.responseSubmittedAt;
      continue;
    }
    byPrompt.set(promptId, {
      exchangeId: `feedback:${promptId}`,
      promptId,
      blocking: true,
      status: 'answered',
      issuedAtTurn: null,
      consumedAtTurn: null,
      receivedAtTurn: null,
      question: firstText(entry.choice, 'Recorded HITL response'),
      detail: firstText(entry.note) || null,
      choices: entry.choice ? [entry.choice] : [],
      evidenceRefs: [],
      responseChoice: firstText(entry.choice) || null,
      responseNote: firstText(entry.note) || null,
      responseSubmittedAt: entry.submitted_at_epoch_seconds ?? null,
      raw: entry as Record<string, unknown>,
    });
  }
  return Array.from(byPrompt.values());
}

function normalizeReplayExchange(raw: unknown): ReplayHitlExchange | null {
  if (!isRecord(raw)) return null;
  const promptId = firstText(raw.prompt_id);
  if (!promptId) return null;
  const request = isRecord(raw.request) ? raw.request : {};
  const response = isRecord(raw.response) ? raw.response : {};
  const context = isRecord(request.context) ? request.context : {};
  const choices = Array.isArray(request.choices)
    ? request.choices.filter((value): value is string => typeof value === 'string')
    : [];
  const evidenceRefs = Array.isArray(request.evidence_refs)
    ? request.evidence_refs.map(String)
    : Array.isArray(context.evidence_refs)
      ? context.evidence_refs.map(String)
      : [];

  return {
    exchangeId: firstText(raw.exchange_id, `hitl:${promptId}`),
    promptId,
    blocking: Boolean(raw.blocking),
    status: firstText(raw.status, 'pending'),
    issuedAtTurn: typeof raw.issued_at_iteration === 'number' ? raw.issued_at_iteration : null,
    consumedAtTurn: typeof raw.consumed_at_iteration === 'number' ? raw.consumed_at_iteration : null,
    receivedAtTurn: typeof raw.received_at_iteration === 'number' ? raw.received_at_iteration : null,
    question: firstText(request.message, 'Human feedback needed'),
    detail: Array.isArray(context.notes) ? context.notes.map(String).join(' ') : null,
    choices,
    evidenceRefs,
    responseChoice: firstText(response.choice) || null,
    responseNote: firstText(response.note) || null,
    responseSubmittedAt:
      typeof response.submitted_at_epoch_seconds === 'number' ? response.submitted_at_epoch_seconds : null,
    raw,
  };
}

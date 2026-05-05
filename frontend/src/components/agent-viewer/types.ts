import type { AgentViewerEvent, AgentViewerLoopKind } from '../../services/agentViewerApi';

export interface AgentViewerPanelProps {
  isOpen: boolean;
  loopKind: AgentViewerLoopKind | null;
  runId: string | null;
  sessionKey?: string;
  transcriptionDrafts?: Array<{ id: string; label: string; text: string }>;
  isTranscribing?: boolean;
  onClose: () => void;
}

export type ViewerTheme = 'void' | 'space';
export type CanvasMode = 'transcription' | 'agent';
export type AgentCanvasPage = 'live_draft' | 'diff' | 'verify_image' | 'ops' | 'wip_preview';

export type CanvasPageOption = {
  id: AgentCanvasPage;
  label: string;
};

export type ClosureRequirement = {
  block_reason?: string;
  required_information?: string;
  self_retrievable?: string;
  retrieval_attempted?: boolean;
  retrieval_blocker?: string | null;
  minimal_user_action?: string;
  resolution_options?: string[];
  evidence_refs?: string[];
  attempt_summary?: string;
  mapping_blocking?: boolean;
};

export type DecisionLedgerItem = {
  key?: string;
  label?: string;
  state?: string;
  selected_value?: string | null;
  alternatives?: string[];
  blocking?: boolean;
  confidence?: string | number | null;
  closure_requirement?: ClosureRequirement | null;
};

export type DecisionSummary = Record<string, any> | null;
export type GenericDetailEvent = AgentViewerEvent | null;

export type LaneChip = {
  lane: string;
  state: string;
  text: string;
  elapsedLabel?: string | null;
  retryLabel?: string | null;
};

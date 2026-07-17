import type { AgentViewerLoopKind } from '../../services/agentViewerApi';

/** Stable overlay contract used by workspaces — viewer implementation is native-only. */
export interface AgentViewerPanelProps {
  isOpen: boolean;
  loopKind: AgentViewerLoopKind | null;
  runId: string | null;
  /** Resets viewer-local state when the host session changes. */
  sessionKey?: string;
  /** Ignored by the viewer; transcription drafts belong to the host workspace. */
  transcriptionDrafts?: Array<{ id: string; label: string; text: string }>;
  /** Ignored by the viewer; host workspace processing posture. */
  isTranscribing?: boolean;
  onClose: () => void;
}

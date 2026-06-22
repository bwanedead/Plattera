export type ViewerSelectionKind =
  | 'turn'
  | 'event'
  | 'artifact'
  | 'work_item'
  | 'evidence'
  | 'hitl'
  | 'action'
  | 'raw';

export type ViewerSelection = {
  kind: ViewerSelectionKind;
  id: string;
  ref?: string | null;
  label?: string | null;
  payload?: Record<string, unknown>;
};

export const EMPTY_SELECTION: ViewerSelection | null = null;

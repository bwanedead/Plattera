import type { AgentViewerAction } from '../../../services/agentViewerApi';
import type { ViewerSelection } from '../selection/selectionTypes';

export type ViewerActionContext = {
  select: (selection: ViewerSelection) => void;
  refreshSnapshot: () => void;
  replay?: {
    restart: () => void;
    scrubToTurn: (turn: number) => void;
  };
};

export type ViewerActionHandler = (
  action: AgentViewerAction,
  context: ViewerActionContext,
) => boolean | void | Promise<boolean | void>;

export type ViewerActionRegistry = Record<string, ViewerActionHandler>;

const BUILTIN_HANDLERS: ViewerActionRegistry = {
  viewer_command: (action, context) => {
    const command = action.target?.command;
    if (command === 'restart') {
      context.replay?.restart();
      return true;
    }
    if (command === 'refresh_snapshot') {
      context.refreshSnapshot();
      return true;
    }
    const turn = action.target?.turn_index;
    if (command === 'scrub_turn' && typeof turn === 'number') {
      context.replay?.scrubToTurn(turn);
      return true;
    }
    return false;
  },
  select_artifact: (action, context) => {
    const ref = action.target?.artifact_ref;
    if (typeof ref !== 'string' || !ref.trim()) return false;
    context.select({
      kind: 'artifact',
      id: ref.trim(),
      ref: ref.trim(),
      label: action.label || ref.trim(),
    });
    return true;
  },
};

export function createActionRegistry(extensions: ViewerActionRegistry = {}): ViewerActionRegistry {
  return { ...BUILTIN_HANDLERS, ...extensions };
}

export const defaultActionRegistry = createActionRegistry();

export async function executeViewerAction(
  action: AgentViewerAction,
  context: ViewerActionContext,
  registry: ViewerActionRegistry = defaultActionRegistry,
): Promise<{ ok: boolean; reason?: string }> {
  if (action.disabled) {
    return { ok: false, reason: action.reason || 'Action is disabled' };
  }

  const handler = registry[action.kind];
  if (!handler) {
    return { ok: false, reason: `Unsupported action kind "${action.kind}"` };
  }

  const handled = await handler(action, context);
  if (handled === false) {
    return { ok: false, reason: `Action "${action.id}" is not supported by handler "${action.kind}"` };
  }
  return { ok: true };
}

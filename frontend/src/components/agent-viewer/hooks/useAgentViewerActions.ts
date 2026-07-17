import React from 'react';
import type { AgentViewerAction, AgentViewerSnapshot } from '../../../services/agentViewerApi';
import {
  defaultActionRegistry,
  executeViewerAction,
  type ViewerActionContext,
  type ViewerActionRegistry,
} from '../registry/actionRegistry';

export type ViewerActionView = AgentViewerAction & {
  onExecute: () => void;
};

type Params = {
  snapshot: AgentViewerSnapshot | null;
  context: ViewerActionContext;
  registry?: ViewerActionRegistry;
};

export function useAgentViewerActions({ snapshot, context, registry = defaultActionRegistry }: Params) {
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [lastResult, setLastResult] = React.useState<{ actionId: string; ok: boolean; reason?: string } | null>(
    null,
  );

  const execute = React.useCallback(
    async (action: AgentViewerAction) => {
      setBusyId(action.id);
      setLastResult(null);
      try {
        const result = await executeViewerAction(action, context, registry);
        setLastResult({ actionId: action.id, ...result });
      } finally {
        setBusyId(null);
      }
    },
    [context, registry],
  );

  const actions = React.useMemo<ViewerActionView[]>(() => {
    const source = snapshot?.actions ?? [];
    return source.map((action) => ({
      ...action,
      onExecute: () => {
        void execute(action);
      },
    }));
  }, [execute, snapshot?.actions]);

  return {
    actions,
    busyId,
    lastResult,
    execute,
  };
}

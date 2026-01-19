import React, { useState } from 'react';
import { DiagnoseResponse, ExecuteIndexRequest } from '../../types/retrieval';

interface IndexExecutionControlsProps {
  diagnose: DiagnoseResponse | null;
  onExecute: (req: Omit<ExecuteIndexRequest, 'pool_identifier'>) => void;
  isExecuting: boolean;
  activeJobId: string | null;
}

export const IndexExecutionControls: React.FC<IndexExecutionControlsProps> = ({
  diagnose,
  onExecute,
  isExecuting,
  activeJobId
}) => {
  const [limit, setLimit] = useState(25);
  const [dryRun, setDryRun] = useState(false);

  if (!diagnose) return null;

  const isUnavailable = diagnose.pool_open.status !== 'ok';
  const reason = diagnose.pool_open.reason_code;
  const detail = diagnose.pool_open.detail;
  const actionHint = diagnose.pool_open.action_hint;

  // If running, disable
  const isBusy = isExecuting || !!activeJobId;

  const handleExecute = () => {
    onExecute({
      mode: 'missing_and_stale',
      limit,
      dry_run: dryRun
    });
  };

  if (isUnavailable) {
    return (
      <div className="index-execution-controls">
        <div className="unavailable-msg">
          <strong>Unavailable:</strong> {reason}
          {detail && <div style={{ fontSize: '0.8em', marginTop: 4 }}>{detail}</div>}
          {actionHint === 'REBUILD_POOL' && (
             <div style={{ marginTop: 8 }}>Recommendation: Rebuild Pool (Not yet implemented in v0 UI)</div>
          )}
        </div>
      </div>
    );
  }

  const { missing, stale } = diagnose.counts;
  const nothingToDo = missing === 0 && stale === 0;

  return (
    <div className="index-execution-controls">
      <div className="controls-row">
        <input 
          type="number" 
          className="limit-input"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          min={1}
          max={100}
          title="Batch Limit"
        />
        <label className="dry-run-label">
          <input 
            type="checkbox" 
            checked={dryRun} 
            onChange={(e) => setDryRun(e.target.checked)} 
          />
          Dry Run
        </label>
      </div>

      <button 
        className="execute-btn primary"
        onClick={handleExecute}
        disabled={isBusy || nothingToDo}
      >
        {isBusy ? 'Indexing...' : 'Update Index (Safe)'}
      </button>
    </div>
  );
};

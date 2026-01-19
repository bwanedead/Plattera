import React, { useState } from 'react';
import { DiagnoseResponse, ExecuteIndexRequest } from '../../types/retrieval';

interface IndexExecutionControlsProps {
  diagnose: DiagnoseResponse | null;
  onExecute: (req: Omit<ExecuteIndexRequest, 'pool_identifier'>) => void;
  onBootstrap: () => void;
  isExecuting: boolean;
  activeJobId: string | null;
}

export const IndexExecutionControls: React.FC<IndexExecutionControlsProps> = ({
  diagnose,
  onExecute,
  onBootstrap,
  isExecuting,
  activeJobId
}) => {
  const EMBEDDING_ASSET_ID = 'embedding_model_bge_small_en_v1_5';
  const [limit, setLimit] = useState(25);
  const [dryRun, setDryRun] = useState(false);

  if (!diagnose) return null;

  const isUnavailable = diagnose.pool_open.status !== 'ok';
  const reason = diagnose.pool_open.reason_code;
  const detail = diagnose.pool_open.detail;
  const actionHint = diagnose.pool_open.action_hint;
  const isEmbeddingMissing = !!detail?.includes('EmbeddingAssetMissingError') ||
    !!detail?.includes('embedding_asset_missing') ||
    reason === 'unavailable_embeddings_missing';
  const isMissingArtifacts = detail?.startsWith('missing_files') || detail === 'manifest_unavailable';
  const isEmptyVectors = diagnose.pool_health?.active_vectors === 0;

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
    if (isEmbeddingMissing) {
      return (
        <div className="index-execution-controls">
          <div className="unavailable-msg">
            <strong>Embedding model not installed.</strong>
            <div style={{ marginTop: 8 }}>
              <button
                className="execute-btn primary"
                onClick={() => document.dispatchEvent(new Event(`asset:open-modal:${EMBEDDING_ASSET_ID}`))}
              >
                Install embeddings
              </button>
            </div>
          </div>
        </div>
      );
    }

    if (isMissingArtifacts) {
      return (
        <div className="index-execution-controls">
          <div className="unavailable-msg">
            <strong>Not Indexed Yet.</strong>
            <div style={{ fontSize: '0.8em', marginTop: 4 }}>Initialize index artifacts to begin indexing.</div>
            <div style={{ marginTop: 8 }}>
              <button
                className="execute-btn primary"
                onClick={onBootstrap}
                disabled={isBusy}
              >
                Initialize Index
              </button>
            </div>
          </div>
        </div>
      );
    }

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
  const showInitialize = isEmptyVectors && missing > 0;

  if (showInitialize) {
    return (
      <div className="index-execution-controls">
        <div className="unavailable-msg">
          <strong>Not Indexed Yet.</strong>
          <div style={{ fontSize: '0.8em', marginTop: 4 }}>Initialize index artifacts to begin indexing.</div>
          <div style={{ marginTop: 8 }}>
            <button
              className="execute-btn primary"
              onClick={onBootstrap}
              disabled={isBusy}
            >
              Initialize Index
            </button>
          </div>
        </div>
      </div>
    );
  }

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

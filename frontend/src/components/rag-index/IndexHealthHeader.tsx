import React from 'react';
import { PoolIdentifier, DiagnoseResponse } from '../../types/retrieval';

interface IndexHealthHeaderProps {
  pool: PoolIdentifier;
  setPool: (p: PoolIdentifier) => void;
  diagnose: DiagnoseResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export const IndexHealthHeader: React.FC<IndexHealthHeaderProps> = ({
  pool,
  setPool,
  diagnose,
  isLoading,
  onRefresh
}) => {
  // Determine status pill state
  let statusClass = 'not-indexed';
  let statusText = 'Unknown';

  if (!diagnose) {
    statusText = isLoading ? 'Loading...' : 'Unknown';
  } else if (diagnose.pool_open.status !== 'ok') {
    const detail = diagnose.pool_open.detail;
    const embeddingMissing = !!detail?.includes('EmbeddingAssetMissingError') || !!detail?.includes('embedding_asset_missing');
    const missingArtifacts = detail?.startsWith('missing_files') || detail === 'manifest_unavailable';

    if (embeddingMissing) {
      statusClass = 'unavailable';
      statusText = 'Embedding model not installed';
    } else if (missingArtifacts) {
      statusClass = 'not-indexed';
      statusText = 'Not Indexed Yet';
    } else {
      statusClass = 'unavailable';
      statusText = 'Unavailable';
    }
  } else {
    // Pool is OK
    const { missing, stale } = diagnose.counts;
    const vectorMismatch = diagnose.pool_health?.vector_consistency_ok === false;
    if (vectorMismatch) {
      statusClass = 'unavailable';
      statusText = 'Index mismatch';
    } else {
      if (missing === 0 && stale === 0) {
        statusClass = 'ready';
        statusText = 'Ready';
      } else {
        statusClass = 'needs-update';
        statusText = 'Needs Update';
      }
      // Check for "Not indexed yet" specifically
      if (diagnose.pool_health?.active_vectors === 0 && missing > 0) {
        statusClass = 'not-indexed';
        statusText = 'Not Indexed Yet';
      }
    }
  }

  return (
    <div className="index-health-header">
      <div className="header-top-row">
        <h3 className="header-title">RAG Index Health</h3>
        <button className="refresh-btn" onClick={onRefresh} title="Refresh Diagnosis">
          {isLoading ? '...' : '↻'}
        </button>
      </div>

      <div className="header-status-row">
        <div className="pool-selector">
          <button 
            className={`pool-option ${pool === 'FINAL_SEGMENTS' ? 'active' : ''}`}
            onClick={() => setPool('FINAL_SEGMENTS')}
          >
            Final Segments
          </button>
          <button 
            className={`pool-option ${pool === 'EVERYTHING' ? 'active' : ''}`}
            onClick={() => setPool('EVERYTHING')}
          >
            Everything
          </button>
        </div>

        <div className={`status-pill ${statusClass}`}>
          {statusText}
        </div>
      </div>
    </div>
  );
};

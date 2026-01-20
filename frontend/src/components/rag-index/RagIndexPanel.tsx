import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useIndexMaintenance } from '../../hooks/useIndexMaintenance';
import { PoolIdentifier } from '../../types/retrieval';
import { IndexJobStrip } from './IndexJobStrip';
import { IndexDetailsPanel } from './IndexDetailsPanel';

export const RagIndexPanel: React.FC = () => {
  type PoolActionState = {
    execute: () => Promise<void>;
    canExecute: boolean;
    isBusy: boolean;
  };

  const poolActionsRef = useRef<Record<PoolIdentifier, PoolActionState | null>>({
    FINAL_SEGMENTS: null,
    EVERYTHING: null
  });
  const [poolStates, setPoolStates] = useState<Record<PoolIdentifier, { canExecute: boolean; isBusy: boolean }>>({
    FINAL_SEGMENTS: { canExecute: false, isBusy: false },
    EVERYTHING: { canExecute: false, isBusy: false }
  });

  const registerPoolActions = useCallback(
    (pool: PoolIdentifier, state: PoolActionState) => {
      poolActionsRef.current[pool] = state;
      setPoolStates(prev => ({
        ...prev,
        [pool]: { canExecute: state.canExecute, isBusy: state.isBusy }
      }));
    },
    []
  );

  const updateAllPools = useCallback(async () => {
    const actions = Object.values(poolActionsRef.current).filter(
      (entry): entry is PoolActionState => !!entry && entry.canExecute
    );
    if (actions.length === 0) return;
    await Promise.all(actions.map(entry => entry.execute()));
  }, []);

  const anyBusy = poolStates.FINAL_SEGMENTS.isBusy || poolStates.EVERYTHING.isBusy;
  const anyExecutable = poolStates.FINAL_SEGMENTS.canExecute || poolStates.EVERYTHING.canExecute;

  const pools: PoolIdentifier[] = useMemo(() => ['FINAL_SEGMENTS', 'EVERYTHING'], []);

  return (
    <div className="rag-index-panel">
      <div className="pool-stack">
        {pools.map(pool => (
          <PoolSection key={pool} pool={pool} onRegister={registerPoolActions} />
        ))}
      </div>
      <div className="pool-footer">
        <button
          className="pool-btn primary"
          onClick={updateAllPools}
          disabled={!anyExecutable || anyBusy}
        >
          Update all pools
        </button>
      </div>
    </div>
  );
};

type PoolSectionProps = {
  pool: PoolIdentifier;
  onRegister: (pool: PoolIdentifier, state: { execute: () => Promise<void>; canExecute: boolean; isBusy: boolean }) => void;
};

const PoolSection: React.FC<PoolSectionProps> = ({ pool, onRegister }) => {
  const {
    diagnoseResult,
    isLoadingDiagnose,
    refreshDiagnose,
    executeIndex,
    bootstrapIndex,
    isExecuting,
    activeJob,
    activeJobId,
    detailsOpen,
    setDetailsOpen
  } = useIndexMaintenance(pool);

  const counts = diagnoseResult?.counts ?? { healthy: 0, missing: 0, stale: 0, unavailable: 0 };
  const poolHealth = diagnoseResult?.pool_health;
  const poolOpen = diagnoseResult?.pool_open;
  const isUnavailable = poolOpen?.status !== 'ok';
  const detail = poolOpen?.detail ?? '';
  const reason = poolOpen?.reason_code ?? '';
  const embeddingMissing =
    detail.includes('EmbeddingAssetMissingError') ||
    detail.includes('embedding_asset_missing') ||
    reason === 'unavailable_embeddings_missing';
  const missingArtifacts = detail.startsWith('missing_files') || detail === 'manifest_unavailable';
  const notIndexed = missingArtifacts || (poolHealth?.active_vectors === 0 && counts.missing > 0);
  const isBusy = isExecuting || !!activeJobId || isLoadingDiagnose;
  const canExecute = !embeddingMissing && !missingArtifacts && !isUnavailable;

  const statusTone = embeddingMissing || isUnavailable
    ? 'danger'
    : notIndexed
    ? 'warn'
    : counts.stale > 0 || counts.missing > 0
    ? 'warn'
    : 'good';

  const statusLabel = embeddingMissing
    ? 'Embeddings missing'
    : notIndexed
    ? 'Not indexed'
    : counts.stale > 0 || counts.missing > 0
    ? 'Needs update'
    : 'Ready';

  const handleUpdate = useCallback(async () => {
    await executeIndex({
      mode: 'missing_and_stale',
      limit: 25,
      dry_run: false
    });
  }, [executeIndex]);

  const handleInitialize = useCallback(async () => {
    await bootstrapIndex();
  }, [bootstrapIndex]);

  useEffect(() => {
    onRegister(pool, {
      execute: handleUpdate,
      canExecute,
      isBusy
    });
  }, [pool, onRegister, handleUpdate, canExecute, isBusy]);

  const poolLabel = pool === 'FINAL_SEGMENTS' ? 'Final Segments' : 'Everything';
  const poolSubtitle = pool === 'FINAL_SEGMENTS' ? 'Recommended default scope' : 'Full corpus coverage';

  return (
    <div className="pool-card">
      <div className="pool-header">
        <div className="pool-title">
          <span className={`pool-dot ${statusTone}`} />
          <div>
            <div className="pool-name">{poolLabel}</div>
            <div className="pool-sub">{poolSubtitle}</div>
          </div>
        </div>
        <div className="pool-status">
          <span className={`pool-pill ${statusTone}`}>{statusLabel}</span>
          <button className="pool-btn ghost" onClick={refreshDiagnose} disabled={isLoadingDiagnose}>
            {isLoadingDiagnose ? '...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="pool-metrics">
        <div className="metric-pill healthy">
          Healthy <span>{counts.healthy}</span>
        </div>
        <div className="metric-pill missing">
          Missing <span>{counts.missing}</span>
        </div>
        <div className="metric-pill stale">
          Stale <span>{counts.stale}</span>
        </div>
        <div className="metric-pill unavailable">
          Unavailable <span>{counts.unavailable}</span>
        </div>
        <div className="metric-pill info">
          Vectors <span>{poolHealth?.active_vectors ?? 0}</span>
        </div>
      </div>

      <div className="pool-actions">
        {embeddingMissing ? (
          <button
            className="pool-btn primary"
            onClick={() => document.dispatchEvent(new Event('asset:open-modal:embedding_model_bge_small_en_v1_5'))}
            disabled={isBusy}
          >
            Install embeddings
          </button>
        ) : notIndexed ? (
          <button className="pool-btn primary" onClick={handleInitialize} disabled={isBusy}>
            Initialize pool
          </button>
        ) : (
          <button className="pool-btn primary" onClick={handleUpdate} disabled={isBusy || !canExecute}>
            Update index
          </button>
        )}
        <div className="pool-actions-hint">
          {embeddingMissing
            ? 'Embeddings are required before indexing.'
            : notIndexed
            ? 'Creates empty index artifacts without indexing documents.'
            : 'Indexes missing and stale entries only.'}
        </div>
      </div>

      <IndexJobStrip job={activeJob} />

      <IndexDetailsPanel
        diagnose={diagnoseResult}
        detailsOpen={detailsOpen}
        toggleDetails={() => setDetailsOpen(!detailsOpen)}
      />
    </div>
  );
};

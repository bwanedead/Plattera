import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useIndexMaintenance } from '../../hooks/useIndexMaintenance';
import { PoolIdentifier, SliceStatus } from '../../types/retrieval';
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
      const current = poolActionsRef.current[pool];
      if (
        current &&
        current.canExecute === state.canExecute &&
        current.isBusy === state.isBusy &&
        current.execute === state.execute
      ) {
        return;
      }
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
    executeIndexAndWait,
    bootstrapIndex,
    isExecuting,
    activeJob,
    activeJobId,
    detailsOpen,
    setDetailsOpen
  } = useIndexMaintenance(pool);

  const [bootstrapStatus, setBootstrapStatus] = useState<string | null>(null);
  const [detailsFilter, setDetailsFilter] = useState<null | SliceStatus | 'stale'>(null);

  const counts = diagnoseResult?.counts ?? { healthy: 0, missing: 0, stale: 0, unavailable: 0, orphaned: 0 };
  const poolHealth = diagnoseResult?.pool_health;
  const poolOpen = diagnoseResult?.pool_open;
  const isUnavailable = poolOpen?.status !== 'ok';
  const detail = poolOpen?.detail ?? '';
  const reason = poolOpen?.reason_code ?? '';
  const isInitializing = isLoadingDiagnose && !diagnoseResult;
  const embeddingMissing =
    !isInitializing && (
    detail.includes('EmbeddingAssetMissingError') ||
    detail.includes('embedding_asset_missing') ||
    reason === 'unavailable_embeddings_missing');
  const missingArtifacts = !isInitializing && (detail.startsWith('missing_files') || detail === 'manifest_unavailable');
  const needsInitialize = !isInitializing && missingArtifacts;
  const emptyButReady = !isInitializing && !missingArtifacts && poolOpen?.status === 'ok' && (poolHealth?.active_vectors === 0);
  const isIndexing =
    isExecuting ||
    activeJob?.status === 'queued' ||
    activeJob?.status === 'running' ||
    !!activeJobId;
  const isBusy = isIndexing || isLoadingDiagnose;
  const canExecute = !isInitializing && !embeddingMissing && !missingArtifacts && !isUnavailable;
  const canPrune = !isInitializing && !isUnavailable;

  const statusTone = isInitializing
    ? 'info'
    : embeddingMissing || isUnavailable
    ? 'danger'
    : needsInitialize
    ? 'warn'
    : counts.orphaned > 0
    ? 'warn'
    : emptyButReady
    ? 'info'
    : counts.stale > 0 || counts.missing > 0
    ? 'warn'
    : 'good';

  const statusLabel = isInitializing
    ? 'Checking...'
    : embeddingMissing
    ? 'Embeddings missing'
    : needsInitialize
    ? 'Not initialized'
    : counts.orphaned > 0
    ? 'Orphaned'
    : emptyButReady
    ? 'Empty (Ready)'
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

  const handleRepair = useCallback(async () => {
    if (isBusy) return;
    const needsIndexing = emptyButReady || counts.missing > 0 || counts.stale > 0;
    const needsPrune = counts.orphaned > 0;

    if (needsIndexing) {
      await executeIndexAndWait({
        mode: 'missing_and_stale',
        limit: 25,
        dry_run: false
      });
    }
    if (needsPrune) {
      await executeIndexAndWait({
        mode: 'prune_orphans',
        limit: Math.min(200, Math.max(1, counts.orphaned || 1)),
        dry_run: false
      });
    }
  }, [counts.missing, counts.orphaned, counts.stale, emptyButReady, executeIndexAndWait, isBusy]);

  const handlePrune = useCallback(async () => {
    await executeIndex({
      mode: 'prune_orphans',
      limit: Math.min(200, Math.max(1, counts.orphaned || 1)),
      dry_run: false
    });
  }, [executeIndex, counts.orphaned]);

  const handleInitialize = useCallback(async () => {
    setBootstrapStatus('Initializing...');
    try {
      await bootstrapIndex();
      setBootstrapStatus('Artifacts initialized');
      window.setTimeout(() => setBootstrapStatus(null), 3000);
    } catch (err) {
      setBootstrapStatus('Initialization failed');
      window.setTimeout(() => setBootstrapStatus(null), 5000);
    }
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
          <span className={`pool-pill ${statusTone}`}>
            <span className="pool-pill-label">{statusLabel}</span>
            {isLoadingDiagnose ? <span className="rag-spinner small" /> : null}
            {isIndexing && !isLoadingDiagnose ? <span className="rag-spinner small" /> : null}
          </span>
          <button className="pool-btn ghost" onClick={refreshDiagnose} disabled={isLoadingDiagnose}>
            {isLoadingDiagnose ? '...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="pool-metrics">
        <button className="metric-pill healthy" type="button" onClick={() => { setDetailsOpen(true); setDetailsFilter('healthy'); }}>
          Healthy <span>{counts.healthy}</span>
        </button>
        <button className="metric-pill missing" type="button" onClick={() => { setDetailsOpen(true); setDetailsFilter('missing'); }}>
          Missing <span>{counts.missing}</span>
        </button>
        <button className="metric-pill stale" type="button" onClick={() => { setDetailsOpen(true); setDetailsFilter('stale'); }}>
          Stale <span>{counts.stale}</span>
        </button>
        <button className="metric-pill orphaned" type="button" onClick={() => { setDetailsOpen(true); setDetailsFilter('orphaned'); }}>
          Orphaned <span>{counts.orphaned}</span>
        </button>
        <button className="metric-pill unavailable" type="button" onClick={() => { setDetailsOpen(true); setDetailsFilter('unavailable'); }}>
          Unavailable <span>{counts.unavailable}</span>
        </button>
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
        ) : needsInitialize ? (
          <button className="pool-btn primary" onClick={handleInitialize} disabled={isBusy}>
            Initialize pool
          </button>
        ) : (
          <div className="pool-actions-row">
            {(counts.missing > 0 || counts.stale > 0 || counts.orphaned > 0 || emptyButReady) ? (
              <button className="pool-btn primary" onClick={handleRepair} disabled={isBusy || !canExecute}>
                {isIndexing ? <span className="rag-spinner small" /> : null}
                {isIndexing ? 'Repairing...' : 'Repair index'}
              </button>
            ) : null}
            <button className="pool-btn ghost" onClick={handleUpdate} disabled={isBusy || !canExecute}>
              {isIndexing ? <span className="rag-spinner small" /> : null}
              {isIndexing
                ? (emptyButReady ? 'Indexing...' : 'Updating...')
                : (emptyButReady ? 'Index now' : 'Update index')}
            </button>
            {counts.orphaned > 0 ? (
              <button className="pool-btn ghost" onClick={handlePrune} disabled={isBusy || !canPrune}>
                Prune deleted
              </button>
            ) : null}
          </div>
        )}
        <div className="pool-actions-hint">
          {bootstrapStatus ? (
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>{bootstrapStatus}</span>
          ) : embeddingMissing
            ? 'Embeddings are required before indexing.'
            : needsInitialize
            ? 'Creates empty index artifacts without indexing documents.'
            : counts.orphaned > 0
            ? 'Index contains deleted entries; prune to clean orphaned slices.'
            : emptyButReady
            ? 'Starts indexing from scratch.'
            : 'Indexes missing and stale entries only.'}
        </div>
      </div>

      <IndexJobStrip job={activeJob} />

      <IndexDetailsPanel
        diagnose={diagnoseResult}
        detailsOpen={detailsOpen}
        statusFilter={detailsFilter}
        clearStatusFilter={() => setDetailsFilter(null)}
        toggleDetails={() => setDetailsOpen(!detailsOpen)}
      />
    </div>
  );
};

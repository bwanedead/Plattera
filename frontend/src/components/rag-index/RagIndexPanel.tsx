import React from 'react';
import { useIndexMaintenance } from '../../hooks/useIndexMaintenance';
import { IndexHealthHeader } from './IndexHealthHeader';
import { IndexCountsRow } from './IndexCountsRow';
import { IndexExecutionControls } from './IndexExecutionControls';
import { IndexJobStrip } from './IndexJobStrip';
import { IndexDetailsPanel } from './IndexDetailsPanel';
import '../../../styles/components/rag-index.css';

export const RagIndexPanel: React.FC = () => {
  const {
    pool,
    setPool,
    diagnoseResult,
    isLoadingDiagnose,
    refreshDiagnose,
    executeIndex,
    isExecuting,
    activeJob,
    activeJobId,
    detailsOpen,
    setDetailsOpen
  } = useIndexMaintenance();

  return (
    <div className="rag-index-panel">
      <IndexHealthHeader 
        pool={pool}
        setPool={setPool}
        diagnose={diagnoseResult}
        isLoading={isLoadingDiagnose}
        onRefresh={refreshDiagnose}
      />

      <IndexCountsRow diagnose={diagnoseResult} />

      <IndexExecutionControls 
        diagnose={diagnoseResult}
        onExecute={executeIndex}
        isExecuting={isExecuting}
        activeJobId={activeJobId}
      />

      <IndexJobStrip job={activeJob} />

      <IndexDetailsPanel 
        diagnose={diagnoseResult}
        detailsOpen={detailsOpen}
        toggleDetails={() => setDetailsOpen(!detailsOpen)}
      />
    </div>
  );
};

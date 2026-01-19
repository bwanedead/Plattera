import React from 'react';
import { DiagnoseResponse } from '../../types/retrieval';

interface IndexCountsRowProps {
  diagnose: DiagnoseResponse | null;
}

export const IndexCountsRow: React.FC<IndexCountsRowProps> = ({ diagnose }) => {
  if (!diagnose) return null;

  const counts = diagnose.counts;
  const isOk = diagnose.pool_open.status === 'ok';

  return (
    <div className={`index-counts-row ${!isOk ? 'disabled' : ''}`}>
      <div className="count-item healthy">
        <span className="count-val">{counts.healthy}</span>
        <span className="count-label">Healthy</span>
      </div>
      <div className="count-item missing">
        <span className="count-val">{counts.missing}</span>
        <span className="count-label">Missing</span>
      </div>
      <div className="count-item stale">
        <span className="count-val">{counts.stale}</span>
        <span className="count-label">Stale</span>
      </div>
      <div className="count-item unavailable">
        <span className="count-val">{counts.unavailable}</span>
        <span className="count-label">Unavail</span>
      </div>
    </div>
  );
};

import React from 'react';
import { IndexJob } from '../../types/retrieval';

interface IndexJobStripProps {
  job: IndexJob | null;
}

export const IndexJobStrip: React.FC<IndexJobStripProps> = ({ job }) => {
  if (!job) return null;

  const { status, progress, results_total, results_returned } = job;
  const percent = progress.total > 0 ? (progress.done / progress.total) * 100 : 0;

  return (
    <div className="index-job-strip">
      <div className="job-header">
        <div className={`job-status ${status}`}>{status}</div>
        <div className="job-stats">
          {progress.done} / {progress.total}
        </div>
      </div>

      <div className="job-progress-bar">
        <div 
          className="job-progress-fill" 
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="job-stats">
        <span>OK: {progress.ok}</span>
        <span>Failed: {progress.failed}</span>
      </div>
      {job.error && (
        <div style={{ color: '#ef4444', fontSize: '0.8rem', marginTop: 4 }}>
          Error: {job.error}
        </div>
      )}
    </div>
  );
};

import React from 'react';
import { DiagnoseResponse } from '../../types/retrieval';

interface IndexDetailsPanelProps {
  diagnose: DiagnoseResponse | null;
  detailsOpen: boolean;
  toggleDetails: () => void;
}

export const IndexDetailsPanel: React.FC<IndexDetailsPanelProps> = ({
  diagnose,
  detailsOpen,
  toggleDetails
}) => {
  return (
    <div className="index-details-panel">
      <div className="details-toggle" onClick={toggleDetails}>
        <span>{detailsOpen ? 'Hide Details' : 'Show Details'}</span>
        <span>{detailsOpen ? '▲' : '▼'}</span>
      </div>

      {detailsOpen && diagnose && (
        <div className="details-content">
          {!diagnose.slice_diagnoses ? (
            <div style={{ padding: 16, textAlign: 'center', color: '#64748b' }}>
              Loading slices...
            </div>
          ) : (
            <table className="slice-table">
              <thead>
                <tr>
                  <th>Dossier</th>
                  <th>Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {diagnose.slice_diagnoses.map((slice, i) => (
                  <tr key={`${slice.dossier_id}-${slice.entry_id}-${i}`}>
                    <td className="id-col" title={slice.dossier_id}>{slice.dossier_id}</td>
                    <td>
                      <span className={`slice-status-badge ${slice.status}`}>
                        {slice.status}
                      </span>
                    </td>
                    <td>{slice.reason}</td>
                  </tr>
                ))}
                {diagnose.slice_diagnoses.length === 0 && (
                  <tr>
                    <td colSpan={3} style={{ textAlign: 'center', padding: 16, color: '#64748b' }}>
                      No slices returned (limit reached or empty)
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

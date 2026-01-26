import React, { useEffect, useState } from 'react';
import { DiagnoseResponse } from '../../types/retrieval';
import { dossierApi } from '../../services/dossier/dossierApi';

interface IndexDetailsPanelProps {
  diagnose: DiagnoseResponse | null;
  detailsOpen: boolean;
  statusFilter: string | null;
  clearStatusFilter: () => void;
  toggleDetails: () => void;
}

export const IndexDetailsPanel: React.FC<IndexDetailsPanelProps> = ({
  diagnose,
  detailsOpen,
  statusFilter,
  clearStatusFilter,
  toggleDetails
}) => {
  const [dossierTitles, setDossierTitles] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    const loadDossiers = async () => {
      if (!detailsOpen) return;
      try {
        const list = await dossierApi.getDossiers();
        if (cancelled) return;
        const next: Record<string, string> = {};
        list.forEach((dossier: any) => {
          const title = dossier?.title || dossier?.name;
          if (dossier?.id && title) {
            next[String(dossier.id)] = title;
          }
        });
        setDossierTitles(next);
      } catch {
        // ignore lookup failures
      }
    };
    loadDossiers();
    return () => {
      cancelled = true;
    };
  }, [detailsOpen]);

  return (
    <div className="index-details-panel">
      <div className="details-toggle" onClick={toggleDetails}>
        <span>{detailsOpen ? 'Hide Details' : 'Show Details'}</span>
        <span>{detailsOpen ? '▲' : '▼'}</span>
      </div>

      {detailsOpen && diagnose && (
        <div className="details-content">
          {statusFilter && (
            <div style={{ padding: '8px 16px', fontSize: '0.7rem', color: '#9ca3af' }}>
              Filter: <strong style={{ color: '#e5e7eb' }}>{statusFilter.toUpperCase()}</strong>{' '}
              <button
                type="button"
                onClick={clearStatusFilter}
                style={{ marginLeft: 8, background: 'transparent', border: 'none', color: '#60a5fa', cursor: 'pointer' }}
              >
                Clear
              </button>
            </div>
          )}
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
                {(statusFilter
                  ? diagnose.slice_diagnoses.filter((slice) => {
                      if (statusFilter === 'stale') {
                        return slice.status === 'stale_content' || slice.status === 'stale_identity';
                      }
                      return slice.status === statusFilter;
                    })
                  : diagnose.slice_diagnoses
                ).map((slice, i) => {
                  const dossierLabel = dossierTitles[slice.dossier_id] || slice.dossier_id;
                  const showId = dossierLabel !== slice.dossier_id;
                  return (
                    <tr key={`${slice.dossier_id}-${slice.entry_id}-${i}`}>
                      <td className="id-col" title={slice.dossier_id}>
                        {dossierLabel}
                        {showId && (
                          <div style={{ fontSize: '0.65rem', color: '#6b7280', marginTop: 2 }}>
                            {slice.dossier_id}
                          </div>
                        )}
                      </td>
                      <td>
                        <span className={`slice-status-badge ${slice.status}`}>
                          {slice.status.toUpperCase()}
                        </span>
                      </td>
                      <td>{slice.reason}</td>
                    </tr>
                  );
                })}
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

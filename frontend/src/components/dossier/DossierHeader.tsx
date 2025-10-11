// ============================================================================
// DOSSIER HEADER COMPONENT
// ============================================================================
// Displays dossier context, stats, and primary actions
// ============================================================================

import React from 'react';
import { Dossier } from '../../types/dossier';

interface DossierHeaderProps {
  selectedDossier?: Dossier;
  onCreateDossier: any;
  onRefresh: () => void;
  onFinalizeDossier?: (dossierId: string) => void;
  stats: {
    totalDossiers: number;
    totalSegments: number;
    totalRuns: number;
    totalDrafts: number;
  };
  onToggleBulkMode?: () => void;
  isBulkMode?: boolean;
}

export const DossierHeader: React.FC<DossierHeaderProps> = ({
  selectedDossier,
  onCreateDossier,
  onRefresh,
  onFinalizeDossier,
  stats,
  onToggleBulkMode,
  isBulkMode
}) => {
  const handleCreateDossier = async () => {
    try {
      // Create a dossier with a generic name
      await onCreateDossier({
        title: `Dossier ${new Date().toLocaleDateString()}`,
        description: "New dossier"
      });
    } catch (error) {
      console.error('Failed to create dossier:', error);
    }
  };
  
  const handleFinalize = async () => {
    if (!selectedDossier) {
      alert('Please select a dossier first');
      return;
    }
    if (!window.confirm(`Finalize "${selectedDossier.title || selectedDossier.name}"?\n\nThis will stitch all segment final selections into a snapshot.`)) {
      return;
    }
    try {
      await onFinalizeDossier?.(selectedDossier.id);
    } catch (e: any) {
      console.error('Finalize failed:', e);
      alert(`Finalize failed: ${e?.message || e}`);
    }
  };
  
  return (
    <div className="dossier-header">
      {/* Left section - Title and current info */}
      <div className="dossier-header-left">
        <span className="dossier-header-title">Dossier Manager</span>

        {selectedDossier && (
          <div className="dossier-current-info">
            <span className="dossier-current-name">{selectedDossier.title || selectedDossier.name}</span>
            <span className="dossier-current-stats">
              {(selectedDossier.segments?.length || 0)} segments
            </span>
          </div>
        )}
      </div>

      {/* Right section - Action buttons */}
      <div className="dossier-header-right">
        <button
          className="dossier-action-btn primary"
          onClick={handleCreateDossier}
          title="Create new dossier"
        >
          New
        </button>

        <button
          className={`dossier-action-btn ${isBulkMode ? 'danger' : ''}`}
          onClick={onToggleBulkMode}
          title="Bulk delete mode"
        >
          {isBulkMode ? 'Exit Bulk' : 'Bulk Delete'}
        </button>

        {selectedDossier && onFinalizeDossier && (
          <button
            className="dossier-action-btn primary"
            onClick={handleFinalize}
            title="Finalize dossier - stitch all segment finals into a snapshot"
          >
            Finalize Dossier
          </button>
        )}

        <button
          className="dossier-action-btn"
          onClick={onRefresh}
          title="Refresh dossiers"
        >
          Refresh
        </button>
      </div>
    </div>
  );
};

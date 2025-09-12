// ============================================================================
// DRAFT ITEM COMPONENT
// ============================================================================
// Displays individual transcription drafts
// ============================================================================

import React, { useCallback } from 'react';
import { Draft, DossierPath } from '../../../types/dossier';

interface DraftItemProps {
  draft: Draft;
  run: { id: string; position: number; transcription_id?: string };
  segment: { id: string; name: string };
  dossier: { id: string; title?: string; name?: string };
  onItemAction: (action: string, data: any) => void;
  onItemSelect: (path: DossierPath) => void;
  onViewRequest?: (path: DossierPath) => void;
}

export const DraftItem: React.FC<DraftItemProps> = ({
  draft,
  run,
  segment,
  dossier,
  onItemAction,
  onItemSelect,
  onViewRequest
}) => {
  // Early return for safety
  if (!draft) {
    console.error('❌ DraftItem: draft is null/undefined');
    return null;
  }

  // Handle missing ID defensively (backend/frontend field name mismatches)
  if (!draft.id) {
    console.error('❌ DraftItem: draft.id is missing!', draft);
    return <div className="draft-item-error">Error: Draft missing ID</div>;
  }

  // 🔍 DEBUG: Log the actual data structure we're receiving
  console.log('🔍 DraftItem Debug - Received data:', {
    draft: draft,
    draftKeys: Object.keys(draft),
    draftId: draft.id,
    hasId: 'id' in draft,
    transcriptionId: draft.transcriptionId,
    hasTranscriptionId: 'transcriptionId' in draft,
    transcription_id: (draft as any).transcription_id,
    hasTranscription_id: 'transcription_id' in draft,
    isBest: draft.isBest,
    hasIsBest: 'isBest' in draft,
    is_best: (draft as any).is_best,
    hasIs_best: 'is_best' in draft,
    metadata: draft.metadata
  });

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const stats = {
    size: draft.metadata?.sizeBytes || 0,
    confidence: draft.metadata?.confidence || 0,
    quality: draft.metadata?.quality || 'low'
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const formatDate = (dateInput: Date | string): string => {
    try {
      // Handle both Date objects and ISO date strings from backend
      const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
      
      // Safety check for invalid dates
      if (isNaN(date.getTime())) {
        console.warn('Invalid date received:', dateInput);
        return 'Unknown Date';
      }
      
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (error) {
      console.warn('Error formatting date:', dateInput, error);
      return 'Invalid Date';
    }
  };

  const formatQuality = (quality: string, confidence: number): string => {
    // Use the quality string if available, otherwise derive from confidence
    if (quality && quality !== 'low') {
      return quality.charAt(0).toUpperCase() + quality.slice(1);
    }
    
    // Fallback to confidence-based quality
    if (confidence >= 0.9) return 'Excellent';
    if (confidence >= 0.7) return 'Good';
    if (confidence >= 0.5) return 'Fair';
    return 'Poor';
  };

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleClick = useCallback(() => {
    const path: DossierPath = {
      dossierId: dossier.id,
      segmentId: segment.id,
      runId: run.id,
      draftId: draft.id
    };
    onItemSelect(path);
  }, [dossier.id, segment.id, run.id, draft.id, onItemSelect]);

  const handleDoubleClick = useCallback(() => {
    console.log('👁️ Draft view request', { draftId: draft.id, runId: run.id, segmentId: segment.id, dossierId: dossier.id });
    onViewRequest?.({
      dossierId: dossier.id,
      segmentId: segment.id,
      runId: run.id,
      draftId: draft.id
    });
  }, [onViewRequest, dossier.id, segment.id, run.id, draft.id]);

  const handleSetBest = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    onItemAction('set_best_draft', {
      dossier_id: dossier.id,
      segment_id: segment.id,
      run_id: run.id,
      draft_id: draft.id
    });
  }, [dossier.id, segment.id, run.id, draft.id, onItemAction]);

  // ============================================================================
  // RENDER
  // ============================================================================

  const [isHovered, setIsHovered] = React.useState(false);

  return (
    <div
      className={`draft-item ${draft.isBest ? 'best' : ''}`}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="draft-header">
        <div className="draft-info">
          <div className="draft-name">
            Draft {draft.position + 1} {draft.isBest && '(Best)'}
          </div>
          <div className="draft-details">
            <span className="draft-date">
              {formatDate(draft.metadata?.createdAt || new Date().toISOString())}
            </span>
             <span className="draft-stats">
               {formatSize(stats.size)} • {formatQuality(stats.quality, stats.confidence)}
             </span>
          </div>
        </div>

        <div className="draft-actions">
          {isHovered && (
            <button
              className="draft-action-btn"
              onClick={(e) => {
                e.stopPropagation();
                console.log('👁️ Draft view button', { draftId: draft.id, runId: run.id, segmentId: segment.id, dossierId: dossier.id });
                onViewRequest?.({
                  dossierId: dossier.id,
                  segmentId: segment.id,
                  runId: run.id,
                  draftId: draft.id
                });
              }}
              title="View draft"
            >
              View
            </button>
          )}
          {!draft.isBest && (
            <button
              className="draft-action-btn set-best"
              onClick={handleSetBest}
              title="Mark as best draft"
            >
              Set Best
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

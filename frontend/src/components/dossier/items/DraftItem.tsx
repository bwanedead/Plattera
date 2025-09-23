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
  currentDisplayPath?: DossierPath;
  onItemAction: (action: string, data: any) => void;
  onItemSelect: (path: DossierPath) => void;
  onViewRequest?: (path: DossierPath) => void;
}

export const DraftItem: React.FC<DraftItemProps> = ({
  draft,
  run,
  segment,
  dossier,
  currentDisplayPath,
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

  // Debug logging removed to reduce noise during hover/rerenders

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const stats = {
    size: draft.metadata?.sizeBytes || 0,
    confidence: draft.metadata?.confidence || 0,
    quality: draft.metadata?.quality || 'low'
  };

  const isProcessing = draft.metadata?.status === 'processing' || Boolean((draft.metadata as any)?.['_placeholder'] === true);
  const isFailed = draft.metadata?.status === 'failed';
  const isLLMConsensus = (draft.metadata as any)?.type === 'llm_consensus';

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
    // Do not persist selection for sub-items; rely on hover styles
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

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div
      className={`draft-item ${(currentDisplayPath?.dossierId === dossier.id && currentDisplayPath?.segmentId === segment.id && currentDisplayPath?.runId === run.id && currentDisplayPath?.draftId === draft.id) ? 'selected' : ''}`}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      <div className="draft-header">
        <div className="draft-info">
          <div className={`draft-name ${
            ((draft.metadata as any)?.type === 'llm_consensus') ? 'consensus' :
            ((draft.metadata as any)?.type === 'alignment_consensus') ? 'alignment-consensus' : ''
          }`}>
            {((draft.metadata as any)?.type === 'llm_consensus')
              ? (isProcessing ? 'LLM Consensus (Processing...)': 'LLM Consensus Draft')
              : ((draft.metadata as any)?.type === 'alignment_consensus')
              ? 'Alignment Consensus Draft'
              : (isProcessing ? `Draft ${draft.position + 1} (Processing...)` : `Draft ${draft.position + 1}`)}
            {draft.isBest && <span className="best-indicator">*</span>}
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
          {isProcessing ? (
            <div className="draft-loading">
              <span className="loading-dots">Processing</span>
            </div>
          ) : (
            <button
              className="dossier-action-btn"
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
          {isLLMConsensus && (
            <>
              {isFailed && (
                <button
                  className="dossier-action-btn warning"
                  onClick={(e) => {
                    e.stopPropagation();
                    const model = window.prompt('Retry LLM consensus. Choose model: gpt-5-nano-consensus | gpt-5-mini-consensus | gpt-5-consensus', 'gpt-5-mini-consensus') || 'gpt-5-mini-consensus';
                    console.log('🔁 Retrying LLM consensus with model:', model);
                    document.dispatchEvent(new CustomEvent('consensus:retry', {
                      detail: { dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: draft.id, model }
                    }));
                  }}
                  title="Retry LLM consensus"
                >
                  Retry
                </button>
              )}
              {!isFailed && (
                <button
                  className="dossier-action-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    const model = window.prompt('Run another LLM consensus. Choose model: gpt-5-nano-consensus | gpt-5-mini-consensus | gpt-5-consensus', 'gpt-5-consensus') || 'gpt-5-consensus';
                    console.log('➕ Running additional LLM consensus with model:', model);
                    document.dispatchEvent(new CustomEvent('consensus:retry', {
                      detail: { dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: draft.id, model }
                    }));
                  }}
                  title="Run another LLM consensus"
                >
                  Run again
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

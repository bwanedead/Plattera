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

  // Resolve the base transcription id reliably across backend/FE variants
  // Sanitize to avoid double-suffix like "..._v2_v2" by stripping a trailing _v1/_v2 if present
  const baseTidRaw = (run as any)?.transcription_id || (run as any)?.transcriptionId || (draft as any)?.transcriptionId || (draft as any)?.transcription_id || '';
  const baseTid = String(baseTidRaw).replace(/_v[12]$/, '');
  const vIndex = draft.position + 1;
  const rawV1Id = `${baseTid}_v${vIndex}_v1`;
  const rawV2Id = `${baseTid}_v${vIndex}_v2`;
  const alignV1Id = `${baseTid}_draft_${vIndex}_v1`;
  const alignV2Id = `${baseTid}_draft_${vIndex}_v2`;
  const consLLMHeadId = `${baseTid}_consensus_llm`;
  const consLLMV1Id = `${baseTid}_consensus_llm_v1`;
  const consLLMV2Id = `${baseTid}_consensus_llm_v2`;
  const consAlignHeadId = `${baseTid}_consensus_alignment`;
  const consAlignV1Id = `${baseTid}_consensus_alignment_v1`;
  const consAlignV2Id = `${baseTid}_consensus_alignment_v2`;
  const baseSelected = currentDisplayPath?.draftId === draft.id;
  const explicitRawVersionSelected = currentDisplayPath?.draftId === rawV1Id || currentDisplayPath?.draftId === rawV2Id;
  const explicitAlignVersionSelected = currentDisplayPath?.draftId === alignV1Id || currentDisplayPath?.draftId === alignV2Id;
  const explicitConsLLMSelected = currentDisplayPath?.draftId === consLLMV1Id || currentDisplayPath?.draftId === consLLMV2Id || currentDisplayPath?.draftId === consLLMHeadId;
  const explicitConsAlignSelected = currentDisplayPath?.draftId === consAlignV1Id || currentDisplayPath?.draftId === consAlignV2Id || currentDisplayPath?.draftId === consAlignHeadId;

  const stats = {
    size: draft.metadata?.sizeBytes || 0,
    confidence: draft.metadata?.confidence || 0,
    quality: draft.metadata?.quality || 'low'
  };

  const isProcessing = draft.metadata?.status === 'processing' || Boolean((draft.metadata as any)?.['_placeholder'] === true);
  const isFailed = draft.metadata?.status === 'failed';
  const isLLMConsensus = (draft.metadata as any)?.type === 'llm_consensus';
  const isAlignmentConsensus = (draft.metadata as any)?.type === 'alignment_consensus';
  const versions = (draft.metadata as any)?.versions as any | undefined;

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
    // Default to HEAD for raw if available; else just open the draft id
    const v = (draft.metadata as any)?.versions as any;
    let headId = draft.id;
    try {
      if (v && v.raw && typeof v.raw.head === 'string') {
        const head = v.raw.head; // 'v1' | 'v2'
        headId = `${baseTid}_v${draft.position + 1}_${head}`;
      }
    } catch {}
    onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: headId });
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
          </div>
          {/* Version indicators: only render available versions; grey text; current selection highlighted */}
          {versions && (
            <div className="draft-versions" style={{ marginTop: 6, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              {/* Raw + Alignment only for raw draft items */}
              {!(isLLMConsensus || isAlignmentConsensus) && (
                <>
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: rawV1Id });
                    }}
                    style={{ cursor: 'pointer', color: ((explicitRawVersionSelected ? (currentDisplayPath?.draftId === rawV1Id) : (versions.raw?.head === 'v1' && baseSelected))) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                    title="Raw v1"
                  >
                    v1
                  </span>
                  {versions.raw?.v2 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: rawV2Id });
                      }}
                      style={{ cursor: 'pointer', color: ((explicitRawVersionSelected ? (currentDisplayPath?.draftId === rawV2Id) : (versions.raw?.head === 'v2' && baseSelected))) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                      title="Raw v2"
                    >
                      v2
                    </span>
                  )}
                  {versions.alignment?.v1 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: alignV1Id });
                      }}
                      style={{ cursor: 'pointer', color: ((explicitAlignVersionSelected ? (currentDisplayPath?.draftId === alignV1Id) : (versions.alignment?.head === 'v1' && baseSelected))) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                      title="Alignment v1"
                    >
                      Av1
                    </span>
                  )}
                  {versions.alignment?.v2 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: alignV2Id });
                      }}
                      style={{ cursor: 'pointer', color: ((explicitAlignVersionSelected ? (currentDisplayPath?.draftId === alignV2Id) : (versions.alignment?.head === 'v2' && baseSelected))) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                      title="Alignment v2"
                    >
                      Av2
                    </span>
                  )}
                </>
              )}

              {/* Consensus pills only for consensus items; labels are simple v1/v2 */}
              {isLLMConsensus && versions.consensus?.llm && (versions.consensus.llm.v1 || versions.consensus.llm.v2) && (
                <>
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: consLLMV1Id });
                    }}
                    style={{ cursor: 'pointer', color: (((currentDisplayPath?.draftId === consLLMV1Id)) || (versions.consensus.llm.head === 'v1' && baseSelected)) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                    title="v1"
                  >
                    v1
                  </span>
                  {versions.consensus.llm.v2 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: consLLMV2Id });
                      }}
                      style={{ cursor: 'pointer', color: (((currentDisplayPath?.draftId === consLLMV2Id)) || (versions.consensus.llm.head === 'v2' && baseSelected)) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                      title="v2"
                    >
                      v2
                    </span>
                  )}
                </>
              )}
              {isAlignmentConsensus && versions.consensus?.alignment && (versions.consensus.alignment.v1 || versions.consensus.alignment.v2) && (
                <>
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: consAlignV1Id });
                    }}
                    style={{ cursor: 'pointer', color: (((currentDisplayPath?.draftId === consAlignV1Id)) || (versions.consensus.alignment.head === 'v1' && baseSelected)) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                    title="v1"
                  >
                    v1
                  </span>
                  {versions.consensus.alignment.v2 && (
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: consAlignV2Id });
                      }}
                      style={{ cursor: 'pointer', color: (((currentDisplayPath?.draftId === consAlignV2Id)) || (versions.consensus.alignment.head === 'v2' && baseSelected)) ? 'var(--accent-primary)' : 'var(--text-secondary)' }}
                      title="v2"
                    >
                      v2
                    </span>
                  )}
                </>
              )}
            </div>
          )}
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
                // Open HEAD if available so version pill highlights correctly
                const v = (draft.metadata as any)?.versions as any;
                let headId = draft.id;
                try {
                  if (v && v.raw && typeof v.raw.head === 'string') {
                    const head = v.raw.head; // 'v1' | 'v2'
                    headId = `${baseTid}_v${draft.position + 1}_${head}`;
                  }
                } catch {}
                onViewRequest?.({ dossierId: dossier.id, segmentId: segment.id, runId: run.id, draftId: headId });
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

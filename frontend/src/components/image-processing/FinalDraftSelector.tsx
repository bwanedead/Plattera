import React, { useState, useMemo } from 'react';
import { AnimatedBorder } from '../AnimatedBorder';
import { dossierApi } from '../../services/dossier/dossierApi';
import { isStrictVersionedId } from '../../services/dossier/versionResolver';

interface FinalDraftSelectorProps {
  redundancyAnalysis?: {
    individual_results: Array<{
      success: boolean;
      text: string;
      tokens: number;
      error?: string;
    }>;
    consensus_text: string;
    best_formatted_text: string;
    best_result_index: number;
    word_confidence_map?: Record<string, number>;
  };
  alignmentResult?: any;
  selectedDraft: number | 'consensus' | 'best';
  onFinalDraftSelected?: (finalText: string, metadata: any) => void;
  isProcessing?: boolean;
  // Add edited draft support
  editedDraftContent?: string;
  editedFromDraft?: number | 'consensus' | 'best' | null;
  // New: IDs for setting final selection via dossier endpoints
  dossierId?: string;
  transcriptionId?: string;
  currentDraftId?: string; // strict versioned id currently viewed
  segmentId?: string; // prefer segment-scoped finals when available
}

export const FinalDraftSelector: React.FC<FinalDraftSelectorProps> = ({
  redundancyAnalysis,
  alignmentResult,
  selectedDraft,
  onFinalDraftSelected,
  isProcessing = false,
  editedDraftContent,
  editedFromDraft,
  dossierId,
  transcriptionId,
  currentDraftId
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);
  // Track which draft was selected as final within this session
  const [selectedFinalDraft, setSelectedFinalDraft] = useState<number | 'consensus' | 'best' | null>(null);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);

  // Always render the button; rely on disabled state when insufficient context
  const isDisabled = isSelecting || isProcessing || !currentDraftId || !dossierId || !transcriptionId;
  const hasFinalDraft = useMemo(() => selectedFinalDraft !== null && selectedFinalDraft === selectedDraft, [selectedFinalDraft, selectedDraft]);

  const handleSelectFinalDraft = async () => {
    if (isSelecting || isProcessing) return;

    setIsSelecting(true);
    try {
      // Normalize: keep base ids for consensus/alignment/raw heads; do not append v1 by default
      const normalize = (id?: string) => {
        const val = String(id || '').trim();
        if (!val) return val;
        if (isStrictVersionedId(val)) return val;
        // consensus: keep base id (matches llm_{tid}.json)
        if (/_consensus_llm$/.test(val)) return val;
        if (/_consensus_alignment$/.test(val)) return val;
        // alignment head (draft_n): keep base
        if (/_draft_\d+$/.test(val)) return val;
        // raw head (tid_vN): keep base
        if (/_v\d+$/.test(val)) return val;
        return val;
      };
      const strictId = normalize(currentDraftId);

      // Confirm overwrite when a different final already exists
      try {
        const existing = (typeof segmentId === 'string' && segmentId.trim())
          ? await dossierApi.getSegmentFinal(String(dossierId), String(segmentId))
          : await dossierApi.getFinalSelection(String(dossierId), String(transcriptionId));
        const existingId = (existing as any)?.draft_id ?? existing;
        if (existingId && existingId !== strictId) {
          setConfirmOverwrite(true);
          return;
        }
      } catch {}

      if (typeof segmentId === 'string' && segmentId.trim()) {
        await dossierApi.setSegmentFinal(String(dossierId), String(segmentId), String(transcriptionId), String(strictId));
      } else {
        await dossierApi.setFinalSelection(String(dossierId), String(transcriptionId), String(strictId));
      }
      setSelectedFinalDraft(selectedDraft);
      onFinalDraftSelected?.('', { draft_id: strictId });
      console.log('✅ Final selection set via dossier API:', { dossierId, transcriptionId, draftId: strictId });
    } catch (error) {
      console.error('❌ Error selecting final draft:', error);
    } finally {
      setIsSelecting(false);
    }
  };

  const getCurrentDraftLabel = () => {
    if (selectedDraft === 'consensus') return 'Consensus Draft ��';
    if (selectedDraft === 'best') return `Draft ${redundancyAnalysis.best_result_index + 1} ⭐`;
    return `Draft ${selectedDraft + 1}`;
  };

  return (
    <div className="final-draft-selector">
      <AnimatedBorder
        isHovered={isHovered}
        borderRadius={6}
        strokeWidth={2}
      >
        <button
          className={`final-draft-button ${hasFinalDraft ? 'selected' : ''} ${isSelecting ? 'processing' : ''}`}
          onClick={handleSelectFinalDraft}
          disabled={isDisabled}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          title={
            hasFinalDraft
              ? `Final draft selected: ${getCurrentDraftLabel()}`
              : (isDisabled
                  ? 'Select a specific versioned draft to enable final selection'
                  : `Select ${getCurrentDraftLabel()} as final draft`)
          }
        >
          {isSelecting ? 'Selecting…' : (hasFinalDraft ? 'Final Selected' : 'Select Final')}
        </button>
      </AnimatedBorder>

      {confirmOverwrite && (
        <div style={{ marginTop: 6, background: '#fff', border: '1px solid #ddd', borderRadius: 6, padding: 8 }}>
          <div style={{ fontSize: 12, marginBottom: 6 }}>Replace the existing final selection for this segment?</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="final-draft-button"
              onClick={async () => {
                try {
                  const normalize = (id?: string) => {
                    const val = String(id || '').trim();
                    if (!val) return val;
                    if (isStrictVersionedId(val)) return val;
                    if (/_consensus_llm$/.test(val)) return val;
                    if (/_consensus_alignment$/.test(val)) return val;
                    if (/_draft_\d+$/.test(val)) return val;
                    if (/_v\d+$/.test(val)) return val;
                    return val;
                  };
                  const strictId = normalize(currentDraftId);
                  if (typeof segmentId === 'string' && segmentId.trim()) {
                    await dossierApi.setSegmentFinal(String(dossierId), String(segmentId), String(transcriptionId), String(strictId));
                  } else {
                    await dossierApi.setFinalSelection(String(dossierId), String(transcriptionId), String(strictId));
                  }
                  setSelectedFinalDraft(selectedDraft);
                  onFinalDraftSelected?.('', { draft_id: strictId });
                } catch (e) {
                  console.error('❌ Failed to overwrite final selection', e);
                } finally {
                  setConfirmOverwrite(false);
                }
              }}
            >
              Confirm
            </button>
            <button className="final-draft-button" onClick={() => setConfirmOverwrite(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}; 
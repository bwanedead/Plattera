import React, { useState, useMemo } from 'react';
import { AnimatedBorder } from '../AnimatedBorder';
import { dossierApi } from '../../services/dossier/dossierApi';

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
      // Confirm overwrite when a different final already exists
      try {
        const existing = await dossierApi.getFinalSelection(String(dossierId), String(transcriptionId));
        if (existing && existing !== currentDraftId) {
          setConfirmOverwrite(true);
          return;
        }
      } catch {}

      await dossierApi.setFinalSelection(String(dossierId), String(transcriptionId), String(currentDraftId));
      setSelectedFinalDraft(selectedDraft);
      onFinalDraftSelected?.('', { draft_id: currentDraftId });
      console.log('✅ Final selection set via dossier API:', { dossierId, transcriptionId, draftId: currentDraftId });
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
                  await dossierApi.setFinalSelection(String(dossierId), String(transcriptionId), String(currentDraftId));
                  setSelectedFinalDraft(selectedDraft);
                  onFinalDraftSelected?.('', { draft_id: currentDraftId });
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
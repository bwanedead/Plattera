import React, { useState } from 'react';
import { Allotment } from 'allotment';
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './ParcelTracerLoader';
import { CopyButton } from '../CopyButton';
import { DraftSelector } from './DraftSelector';
import { AlignmentButton } from './AlignmentButton';
import { ConfidenceHeatmapViewer } from './ConfidenceHeatmapViewer';
import { formatJsonPretty } from '../../utils/jsonFormatter';
import { AlignmentResult, ConfidenceWord } from '../../types/imageProcessing';
import { FinalDraftSelector } from './FinalDraftSelector';
import { DossierManager } from '../dossier/DossierManager';
import { DossierPath } from '../../types/dossier';
import { resolveSelectionToText, ResolvedSelection } from '../../services/dossier/selectionResolver';
import { textApi } from '../../services/textApi';
// @ts-ignore - Temporary fix for TypeScript cache issue with new DossierReader module
import DossierReader from './DossierReader';

// Define interfaces for props to ensure type safety
interface ResultsViewerProps {
  isProcessing: boolean;
  sessionResults: any[];
  selectedResult: any;
  onSelectResult: (result: any) => void;
  isHistoryVisible: boolean;
  onToggleHistory: (visible: boolean) => void;
  getCurrentText: () => string;
  getRawText: () => string;
  getOriginalJsonText: () => string;
  getNormalizedSectionsText: () => string;
  hasNormalizedSections: () => boolean;
  isCurrentResultJson: () => boolean;
  onSaveDraft: () => void;
  selectedDraft: number | 'consensus' | 'best';
  onDraftSelect: (draft: number | 'consensus' | 'best') => void;
  // New alignment-related props
  alignmentResult?: AlignmentResult | null;
  showHeatmap?: boolean;
  onAlign?: () => void;
  isAligning?: boolean;
  // New editing-related props
  onTextUpdate?: (newText: string) => void;
  onApplyEdit?: (blockIndex: number, tokenIndex: number, newValue: string, editType?: 'alternative_selection' | 'manual_edit') => void;
  editableDraftState?: {
    hasUnsavedChanges: boolean;
    canUndo: boolean;
    canRedo: boolean;
    editedDraft: {
      content: string;
      blockTexts: string[];
    };
    editedFromDraft?: number | 'consensus' | 'best' | null;
    editHistory?: any[]; // Allow any edit history format
  };
  onUndoEdit?: () => void;
  onRedoEdit?: () => void;
  onResetToOriginal?: () => void;
  onSaveAsOriginal?: () => void;
  // Toggle functionality for showing original vs edited versions
  showEditedVersion?: boolean;
  onToggleEditedVersion?: () => void;
  onFinalDraftSelected?: (finalText: string, metadata: any) => void;
}

export const ResultsViewer: React.FC<ResultsViewerProps> = ({
  isProcessing,
  sessionResults,
  selectedResult,
  onSelectResult,
  isHistoryVisible,
  onToggleHistory,
  getCurrentText,
  getRawText,
  getOriginalJsonText,
  getNormalizedSectionsText,
  hasNormalizedSections,
  isCurrentResultJson,
  onSaveDraft,
  selectedDraft,
  onDraftSelect,
  alignmentResult,
  showHeatmap = false,
  onAlign,
  isAligning = false,
  onTextUpdate,
  onApplyEdit,
  editableDraftState,
  onUndoEdit,
  onRedoEdit,
  onResetToOriginal,
  onSaveAsOriginal,
  showEditedVersion = true,
  onToggleEditedVersion,
  onFinalDraftSelected,
}) => {
  const [activeTab, setActiveTab] = useState('text');
  const [showAlignedText, setShowAlignedText] = useState(false);
  const [currentDisplayPath, setCurrentDisplayPath] = useState<DossierPath | undefined>();

  // Check if current result has multiple drafts for alignment
  const hasMultipleDrafts = selectedResult?.result?.metadata?.redundancy_analysis?.individual_results?.length > 1;

  // Check if this is a dossier-level view (stitched content)
  const isDossierView = selectedResult?.result?.metadata?.service_type === 'dossier' &&
                       selectedResult?.result?.metadata?.is_dossier_level === true;

  // Clear currentDisplayPath when not showing dossier results
  React.useEffect(() => {
    if (selectedResult?.result?.metadata?.service_type !== 'dossier') {
      setCurrentDisplayPath(undefined);
    }
  }, [selectedResult]);

  // Text update handler from editing functionality
  const handleTextUpdate = (newText: string) => {
    if (onTextUpdate) {
      onTextUpdate(newText);
    }
  };

  return (
    <div className="results-area" style={{ width: '100%', height: '100%' }}>
      <Allotment defaultSizes={[300, 700]} vertical={false}>
        {isHistoryVisible && (
          <Allotment.Pane minSize={200} maxSize={500}>
            <div className="results-history-panel visible">
              <div className="history-header">
                <h4>Dossier Manager</h4>
                <button onClick={() => onToggleHistory(false)}>‹</button>
              </div>
              <div className="dossier-manager-content">
                <DossierManager
                  currentDisplayPath={currentDisplayPath}
                  onSelectionChange={(path: DossierPath) => {
                    console.log('📁 Dossier selection changed:', path);
                  }}
                  onViewRequest={async (path: DossierPath) => {
                    console.log('👁️ View requested:', path);
                    try {
                      const resolved: ResolvedSelection = await resolveSelectionToText(path);

                      // Update the current display path for highlighting
                      setCurrentDisplayPath(path);

                      // Check if this is dossier-level viewing (no segment/run/draft specified)
                      const isDossierLevel = !path.segmentId && !path.runId && !path.draftId;

                      if (isDossierLevel) {
                        // Create dossier-level result for DossierReader
                        const dossierResult = {
                          input: 'Dossier View',
                          status: 'completed' as const,
                          result: {
                            extracted_text: resolved.text || '',
                            metadata: {
                              model_used: 'dossier-view',
                              service_type: 'dossier',
                              is_dossier_level: true,
                              dossier_title: resolved.context?.dossier?.title || resolved.context?.dossier?.name,
                              dossier_id: path.dossierId,
                              stitched_content: resolved.text || ''
                            }
                          }
                        };
                        onSelectResult(dossierResult);
                        setActiveTab('text');
                      } else {
                        // Handle individual draft/run/segment selection
                        const draftCount = resolved.context?.run?.drafts?.length || 1;
                        const selectedDraftId = resolved.context?.draft?.id;
                        const selectedIndex = selectedDraftId && resolved.context?.run?.drafts
                          ? Math.max(0, (resolved.context.run.drafts || []).findIndex(d => d.id === selectedDraftId))
                          : 0;

                        // Fetch raw JSON for all drafts for JSON tab, and clean text for TEXT tab
                        const draftIds = (resolved.context?.run?.drafts || []).map(d => d.id);
                        const jsonStrings: string[] = [];
                        const cleanTexts: string[] = [];
                        for (let i = 0; i < draftIds.length; i++) {
                          const draftId = draftIds[i];
                          try {
                            const js = await textApi.getDraftJson(draftId);
                            jsonStrings.push(js || '');
                          } catch (e) {
                            jsonStrings.push('');
                          }
                          try {
                            const text = await textApi.getDraftText(
                              resolved.context?.run?.transcriptionId || (resolved.context?.run as any)?.transcription_id || '',
                              draftId
                            );
                            cleanTexts.push(text || '');
                          } catch (e) {
                            cleanTexts.push('');
                          }
                        }

                        // Build redundancy_analysis with JSON strings per draft
                        const individual_results = (draftIds.length ? draftIds : [selectedDraftId]).map((_, i) => ({
                          success: true,
                          text: jsonStrings[i] || '',
                          display_text: cleanTexts[i] || '',
                          model: 'dossier-selection',
                          confidence: 1.0,
                          draft_index: i
                        }));

                        const syntheticResult = {
                          input: 'Dossier Selection',
                          status: 'completed' as const,
                          result: {
                            // Keep the selected draft's raw JSON here to keep JSON tab behavior consistent
                            extracted_text: jsonStrings[selectedIndex] || '',
                            metadata: {
                              model_used: 'dossier-selection',
                              service_type: 'dossier',
                              is_imported_draft: true,
                              selected_draft_index: selectedIndex,
                              redundancy_analysis: {
                                enabled: false,
                                count: draftCount,
                                individual_results,
                                // Keep consensus_text as cleaned text for convenience
                                consensus_text: resolved.text || ''
                              }
                            }
                          }
                        };
                        onSelectResult(syntheticResult);
                        onDraftSelect(selectedIndex as any);
                        setActiveTab('text');
                      }
                    } catch (e) {
                      console.warn('Failed to resolve dossier selection', e);
                    }
                  }}
                  onProcessingComplete={() => {
                    // Refresh dossiers when new processing completes
                    console.log('🔄 Processing completed - refreshing dossiers');
                  }}
                />
              </div>
            </div>
          </Allotment.Pane>
        )}
        <Allotment.Pane>
          <div className="results-viewer-panel">
            {!isHistoryVisible && (
              <button
                className="history-toggle-button"
                onClick={() => onToggleHistory(true)}
              >
                ›
              </button>
            )}
            {isProcessing && (
              <div className="loading-view">
                <ParcelTracerLoader />
                <h4>Tracing Parcels...</h4>
                <p>Analyzing document geometry.</p>
              </div>
            )}
            {!isProcessing && !selectedResult && (
              <div className="placeholder-view">
                <p>Your results will appear here.</p>
              </div>
            )}
            {!isProcessing && selectedResult && (
              <div className="result-display-area">
                <CopyButton
                  onCopy={() => {
                    if (activeTab === 'text') {
                      navigator.clipboard.writeText(getCurrentText());
                    } else if (activeTab === 'json') {
                      navigator.clipboard.writeText(formatJsonPretty(getOriginalJsonText()));
                    } else if (activeTab === 'normalized') {
                      navigator.clipboard.writeText(getNormalizedSectionsText());
                    } else if (activeTab === 'metadata') {
                      navigator.clipboard.writeText(
                        selectedResult.status === 'completed'
                          ? JSON.stringify(selectedResult.result?.metadata, null, 2)
                          : 'No metadata available for failed processing.'
                      );
                    }
                  }}
                  title={`Copy ${activeTab}`}
                  style={{
                    position: 'absolute',
                    top: '5rem',
                    left: '-3rem',
                    zIndex: 20,
                  }}
                />

                {/* Alignment Button - positioned to the left of DraftSelector */}
                <AlignmentButton
                  visible={hasMultipleDrafts}
                  onAlign={onAlign || (() => {})}
                  isAligning={isAligning}
                  disabled={!hasMultipleDrafts}
                />

                <DraftSelector
                  redundancyAnalysis={
                    selectedResult.result?.metadata?.redundancy_analysis
                  }
                  onDraftSelect={onDraftSelect}
                  selectedDraft={selectedDraft}
                  alignmentResult={alignmentResult}  // ← NEW: Pass alignmentResult (may be null initially)
                />

                {/* NEW: Final Draft Selector - positioned to the right of DraftSelector */}
                <FinalDraftSelector
                  redundancyAnalysis={selectedResult.result?.metadata?.redundancy_analysis}
                  alignmentResult={alignmentResult}
                  selectedDraft={selectedDraft}
                  onFinalDraftSelected={onFinalDraftSelected}
                  isProcessing={isProcessing}
                  editedDraftContent={editableDraftState?.hasUnsavedChanges && 
                     editableDraftState?.editedFromDraft === selectedDraft 
                     ? editableDraftState.editedDraft.content 
                     : undefined}
                  editedFromDraft={editableDraftState?.editedFromDraft}
                />

                {/* Edit Toggle Button - shown when there are unsaved changes */}
                {editableDraftState?.hasUnsavedChanges && (
                  <div className="edit-toggle-section">
                    <button
                      className="edit-toggle-button"
                      onClick={() => {
                        // Toggle between showing original and edited versions
                        if (onToggleEditedVersion) {
                          onToggleEditedVersion();
                        }
                      }}
                      title={`Currently showing ${showEditedVersion ? 'edited' : 'original'} version - click to toggle`}
                    >
                      {showEditedVersion ? '📝 Edited' : '📄 Original'}
                    </button>
                    
                    {/* Undo/Redo buttons */}
                    <div className="edit-controls">
                      <button
                        className="edit-control-button"
                        onClick={onUndoEdit}
                        disabled={!editableDraftState.canUndo}
                        title="Undo last edit"
                      >
                        ↶
                      </button>
                      <button
                        className="edit-control-button"
                        onClick={onRedoEdit}
                        disabled={!editableDraftState.canRedo}
                        title="Redo last edit"
                      >
                        ↷
                      </button>
                      <button
                        className="edit-control-button reset"
                        onClick={onResetToOriginal}
                        disabled={!editableDraftState.hasUnsavedChanges}
                        title="Reset to original"
                      >
                        🔄
                      </button>
                    </div>
                  </div>
                )}

                {/* Original vs Aligned Text Toggle */}
                {alignmentResult?.success && (
                  <div className="text-source-toggle">
                    <label className="toggle-label">
                      <input
                        type="checkbox"
                        checked={showAlignedText}
                        onChange={(e) => setShowAlignedText(e.target.checked)}
                      />
                      Show aligned text (vs original)
                    </label>
                  </div>
                )}

                <div className="result-tabs">
                  <button
                    className={activeTab === 'text' ? 'active' : ''}
                    onClick={() => setActiveTab('text')}
                  >
                    📄 Text
                  </button>
                  {isCurrentResultJson() && (
                    <button
                      className={activeTab === 'json' ? 'active' : ''}
                      onClick={() => setActiveTab('json')}
                    >
                      🔧 JSON
                    </button>
                  )}
                  {hasNormalizedSections() && (
                    <button
                      className={activeTab === 'normalized' ? 'active' : ''}
                      onClick={() => setActiveTab('normalized')}
                    >
                      📋 Normalized Sections
                    </button>
                  )}
                  <button
                    className={activeTab === 'metadata' ? 'active' : ''}
                    onClick={() => setActiveTab('metadata')}
                  >
                    📊 Metadata
                  </button>
                </div>

                <div className="result-tab-content">
                  {activeTab === 'text' && (
                    <div
                      className="text-viewer-pane"
                      style={{ height: '100%' }}
                    >
                      {isDossierView ? (
                        <DossierReader
                          dossierId={currentDisplayPath?.dossierId || ''}
                          dossierTitle={selectedResult.result?.metadata?.dossier_title || 'Dossier'}
                        />
                      ) : showHeatmap && alignmentResult ? (
                        <ConfidenceHeatmapViewer
                          alignmentResult={alignmentResult}
                          onTextUpdate={handleTextUpdate}
                          onApplyEdit={onApplyEdit}
                          editableDraftState={editableDraftState ? {
                            hasUnsavedChanges: editableDraftState.hasUnsavedChanges,
                            canUndo: editableDraftState.canUndo,
                            canRedo: editableDraftState.canRedo,
                            editedDraft: editableDraftState.editedDraft,
                            editHistory: (editableDraftState as any).editHistory || [],
                            editedFromDraft: (editableDraftState as any).editedFromDraft
                          } : undefined}
                          onUndoEdit={onUndoEdit}
                          onRedoEdit={onRedoEdit}
                          onResetToOriginal={onResetToOriginal}
                          selectedDraft={selectedDraft}
                          redundancyAnalysis={selectedResult.result?.metadata?.redundancy_analysis}
                        />
                      ) : (
                        <div className="text-content-wrapper">
                          {editableDraftState?.hasUnsavedChanges &&
                           editableDraftState?.editedFromDraft === selectedDraft &&
                           showEditedVersion && (
                            <div className="edited-text-indicator">
                              ✏️ Showing edited version
                            </div>
                          )}
                          <div
                            className="text-content"
                            style={{ whiteSpace: 'pre-wrap', height: '100%', overflowY: 'auto', padding: '1rem', fontFamily: 'monospace' }}
                          >
                            {getCurrentText()}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {activeTab === 'json' && isCurrentResultJson() && (
                    <div className="json-display">
                      <div className="json-actions">
                        <button
                          className="save-draft-button"
                          onClick={onSaveDraft}
                          title="Save this draft for future alignment testing"
                        >
                          💾 Save Draft
                        </button>
                      </div>
                      <pre className="json-content">
                        {formatJsonPretty(getOriginalJsonText())}
                      </pre>
                    </div>
                  )}
                  {activeTab === 'normalized' && hasNormalizedSections() && (
                    <div className="normalized-sections-display">
                      <div className="normalized-sections-header">
                        <h4>Section-Normalized Drafts</h4>
                        <p>Shows drafts after section count normalization (splitting under-sectioned drafts)</p>
                      </div>
                      <div className="normalized-sections-content">
                        <pre className="normalized-sections-text" style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                          {getNormalizedSectionsText()}
                        </pre>
                      </div>
                    </div>
                  )}
                  {activeTab === 'metadata' && (
                    <div className="metadata-display">
                      <pre>
                        {selectedResult.status === 'completed'
                          ? JSON.stringify(
                              selectedResult.result?.metadata,
                              null,
                              2
                            )
                          : 'No metadata available for failed processing.'}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  );
}; 
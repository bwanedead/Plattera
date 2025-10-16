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
import ToolTray from './ToolTray';
import { DossierManager } from '../dossier/DossierManager';
import { DossierPath } from '../../types/dossier';
import { resolveSelectionToText, ResolvedSelection } from '../../services/dossier/selectionResolver';
import { textApi } from '../../services/textApi';
// @ts-ignore - Temporary fix for TypeScript cache issue with new DossierReader module
import DossierReader from './DossierReader';
import ImageOverlayViewer from './ImageOverlayViewer';

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
  onToggleAlignmentPanel?: () => void;
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
  // NEW: Free-form edit plumbing
  onSetEditedContent?: (text: string) => void;
  onSaveEditedContent?: (payload?: { sections?: Array<{ id: number | string; body: string }>; text?: string }) => Promise<void>;
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
  onToggleAlignmentPanel,
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
  onSetEditedContent,
  onSaveEditedContent,
}) => {
  const [activeTab, setActiveTab] = useState('text');
  const [showAlignedText, setShowAlignedText] = useState(false);
  const [currentDisplayPath, setCurrentDisplayPath] = useState<DossierPath | undefined>();
  const [isEditing, setIsEditing] = useState(false);
  const [showFinalConfirm, setShowFinalConfirm] = useState<null | { nextDraftId: string }>(null);
  const latestViewReqRef = React.useRef<string | null>(null);

  const setFinalForCurrentView = async (nextDraftId?: string) => {
    const dossierId = currentDisplayPath?.dossierId || selectedResult?.result?.metadata?.dossier_id;
    const transcriptionId = selectedResult?.result?.metadata?.transcription_id;
    const draftId = nextDraftId || currentDisplayPath?.draftId || selectedResult?.result?.metadata?.selected_versioned_draft_id;
    const segmentId = currentDisplayPath?.segmentId; // ensure segment scope
    if (!dossierId || !transcriptionId || !draftId) {
      alert('Select a specific versioned draft in the Dossier Manager first.');
      return;
    }
    if (!segmentId) {
      alert('Segment is not selected. Choose a segment in the Dossier Manager.');
      return;
    }
    // confirm only if overwriting an existing different final
    let needsConfirm = false;
    try {
      const { dossierApi } = await import('../../services/dossier/dossierApi');
      const existing = await dossierApi.getSegmentFinal(String(dossierId), String(segmentId));
      needsConfirm = !!(existing && existing.draft_id && existing.draft_id !== draftId);
    } catch {}
    if (needsConfirm) {
      setShowFinalConfirm({ nextDraftId: String(draftId) });
      return;
    }
    const { dossierApi } = await import('../../services/dossier/dossierApi');
    await dossierApi.setSegmentFinal(String(dossierId), String(segmentId), String(transcriptionId), String(draftId));
    try {
      document.dispatchEvent(new Event('dossiers:refresh'));
      document.dispatchEvent(new CustomEvent('dossier:refreshOne', { detail: { dossierId } }));
    } catch {}
    console.log('✅ Set final selection:', { dossierId, transcriptionId, draftId });
  };

  // Check if current result has multiple drafts for alignment
  const hasMultipleDrafts = selectedResult?.result?.metadata?.redundancy_analysis?.individual_results?.length > 1;

  // Compute if alignment can run: need at least 2 successful raw drafts
  const individualResults = selectedResult?.result?.metadata?.redundancy_analysis?.individual_results || [];
  const successfulCount = Array.isArray(individualResults) ? individualResults.filter((r: any) => r && r.success).length : 0;
  const canAlign = successfulCount > 1;

  // Check if this is a dossier-level view (stitched content)
  const isDossierView = selectedResult?.result?.metadata?.service_type === 'dossier' &&
                       selectedResult?.result?.metadata?.is_dossier_level === true;

  // Clear currentDisplayPath when not showing dossier results
  React.useEffect(() => {
    if (selectedResult?.result?.metadata?.service_type !== 'dossier') {
      setCurrentDisplayPath(undefined);
    }
  }, [selectedResult]);

  // Listen for draft revert events to reload the current draft
  React.useEffect(() => {
    const handleDraftReverted = async (event: Event) => {
      const customEvent = event as CustomEvent;
      const { dossierId, transcriptionId } = customEvent.detail || {};
      
      console.log('🔄 Draft reverted event received:', { dossierId, transcriptionId });
      
      // Check if this revert affects the currently displayed draft
      const currentDossierId = selectedResult?.result?.metadata?.dossier_id;
      const currentTranscriptionId = selectedResult?.result?.metadata?.transcription_id;
      
      if (dossierId === currentDossierId && transcriptionId === currentTranscriptionId) {
        console.log('✅ Revert affects current draft - reloading from dossier manager');
        
        // Re-trigger the view request for the current display path to force reload
        if (currentDisplayPath) {
          console.log('🔄 Re-requesting view for path:', currentDisplayPath);
          
          // Import the resolver here to avoid circular dependencies
          const { resolveSelectionToText } = await import('../../services/dossier/selectionResolver');
          const { textApi } = await import('../../services/textApi');
          
          try {
            const resolved = await resolveSelectionToText(currentDisplayPath, undefined);
            
            // Rebuild the result with fresh data from v1
            const path = currentDisplayPath;
            const isDossierLevel = !path.segmentId && !path.runId && !path.draftId;
            
            if (!isDossierLevel && path.draftId) {
              const selectedDraftId = path.draftId;
              // Strict: fetch only the selected draft's clean text; no fallback
              let selectedCleanText = '';
              try {
                selectedCleanText = await textApi.getDraftText(transcriptionId, selectedDraftId, dossierId);
              } catch {}

              const allDrafts = resolved.context?.run?.drafts || [];
              const rawDrafts = allDrafts.filter(d => !d.id.endsWith('_consensus_llm') && !d.id.endsWith('_consensus_alignment'));
              const individual_results = rawDrafts.map((draft, i) => ({
                success: true,
                text: '',
                display_text: '',
                model: 'dossier-selection',
                confidence: 1.0,
                draft_index: i
              }));

              const syntheticResult = {
                input: 'Dossier Selection (Reloaded)',
                status: 'completed' as const,
                result: {
                  extracted_text: selectedCleanText || '',
                  metadata: {
                    model_used: 'dossier-selection',
                    service_type: 'dossier',
                    is_imported_draft: true,
                    selected_draft_index: undefined,
                    is_consensus_selected: false,
                    transcription_id: transcriptionId,
                    dossier_id: dossierId,
                    selected_versioned_draft_id: selectedDraftId,
                    redundancy_analysis: {
                      enabled: false,
                      count: rawDrafts.length,
                      individual_results,
                      consensus_text: resolved.text || ''
                    }
                  }
                }
              };

              console.log('✅ Reloaded draft result (strict):', syntheticResult);
              onSelectResult(syntheticResult);
              console.log('✅ Draft view refreshed (strict)');
            }
          } catch (error) {
            console.error('❌ Failed to reload draft after revert:', error);
          }
        } else {
          console.warn('⚠️ No currentDisplayPath to reload - draft may not refresh properly');
        }
      } else {
        console.log('ℹ️ Revert does not affect current draft - ignoring');
      }
    };
    
    document.addEventListener('draft:reverted', handleDraftReverted);
    
    return () => {
      document.removeEventListener('draft:reverted', handleDraftReverted);
    };
  }, [selectedResult, currentDisplayPath, onSelectResult]);

  // Listen for draft saved events to immediately switch view/highlight to v2
  React.useEffect(() => {
    const handler = async (event: Event) => {
      const custom = event as CustomEvent;
      const detail = custom.detail || {};
      const savedDossierId = detail?.dossierId;
      const savedTranscriptionId = detail?.transcriptionId;
      const savedDraftId = detail?.draftId as string | undefined;

      const currentDossierId = selectedResult?.result?.metadata?.dossier_id;
      const currentTranscriptionId = selectedResult?.result?.metadata?.transcription_id;

      if (!savedDossierId || !savedTranscriptionId || savedDossierId !== currentDossierId || savedTranscriptionId !== currentTranscriptionId) return;

      // Build the v2 path from event, keep current segment/run
      const nextPath: DossierPath | undefined = currentDisplayPath && savedDraftId ? {
        dossierId: currentDisplayPath.dossierId,
        segmentId: currentDisplayPath.segmentId,
        runId: currentDisplayPath.runId,
        draftId: savedDraftId
      } : undefined;

      if (!nextPath) return;

      console.log(`🔵 Draft saved -> switching view to: draftId=${savedDraftId} (dossier=${savedDossierId}, transcription=${savedTranscriptionId})`);
      // Guard: if currentDisplayPath already points to this draftId, avoid redundant reloads
      if (currentDisplayPath?.draftId === savedDraftId) {
        return;
      }
      setCurrentDisplayPath(nextPath);

      try {
        const resolved: ResolvedSelection = await resolveSelectionToText(nextPath, undefined);

        const allDrafts = resolved.context?.run?.drafts || [];
        const rawDrafts = allDrafts.filter(d => !d.id.endsWith('_consensus_llm') && !d.id.endsWith('_consensus_alignment'));

        const draftIds = Array.from(new Set([
          ...allDrafts.map(d => d.id),
          nextPath.draftId
        ].filter(Boolean))) as string[];

        const [jsonStrings, cleanTexts] = await Promise.all([
          Promise.all(draftIds.map(did => textApi.getDraftJson(currentTranscriptionId || '', did, nextPath.dossierId).then(js => (typeof js === 'string' ? js : (js ? JSON.stringify(js) : ''))).catch(() => ''))),
          Promise.all(draftIds.map(did => textApi.getDraftText(currentTranscriptionId || '', did, nextPath.dossierId).then(t => t || '').catch(() => '')))
        ]);

        const individual_results = rawDrafts.map((draft, i) => {
          const draftIndexInAll = allDrafts.findIndex(d => d.id === draft.id);
          return {
            success: true,
            text: jsonStrings[draftIndexInAll] || '',
            display_text: cleanTexts[draftIndexInAll] || '',
            model: 'dossier-selection',
            confidence: 1.0,
            draft_index: i
          };
        });

        const idxInFetched = draftIds.findIndex(d => d === nextPath.draftId);
        const selectedCleanText = idxInFetched >= 0 ? (cleanTexts[idxInFetched] || '') : '';

        // Compute raw draft index from savedDraftId when alignment Av2 was saved
        let selectedIndexFromId: number | undefined = undefined;
        try {
          if (savedDraftId && /_draft_\d+(_v[12])?$/.test(savedDraftId)) {
            const m = savedDraftId.match(/_draft_(\d+)/);
            if (m) selectedIndexFromId = Math.max(0, parseInt(m[1], 10) - 1);
          } else if (savedDraftId && /_v\d+_v[12]$/.test(savedDraftId)) {
            const m = savedDraftId.match(/_v(\d+)_v[12]$/);
            if (m) selectedIndexFromId = Math.max(0, parseInt(m[1], 10) - 1);
          }
        } catch {}

        const syntheticResult = {
          input: 'Dossier Selection (Saved)',
          status: 'completed' as const,
          result: {
            extracted_text: selectedCleanText,
            metadata: {
              model_used: 'dossier-selection',
              service_type: 'dossier',
              is_imported_draft: true,
              selected_draft_index: selectedIndexFromId,
              is_consensus_selected: false,
              transcription_id: currentTranscriptionId,
              dossier_id: nextPath.dossierId,
              selected_versioned_draft_id: nextPath.draftId,
              redundancy_analysis: {
                enabled: false,
                count: rawDrafts.length,
                individual_results,
                consensus_text: resolved.text || ''
              }
            }
          }
        };
        onSelectResult(syntheticResult);
        setActiveTab('text');
      } catch (e) {
        console.warn('⚠️ Failed to switch view to saved draft', e);
      }
    };

    document.addEventListener('draft:saved', handler);
    return () => document.removeEventListener('draft:saved', handler);
  }, [currentDisplayPath, selectedResult, onSelectResult]);

  // Text update handler from editing functionality
  const handleTextUpdate = (newText: string) => {
    if (onTextUpdate) {
      onTextUpdate(newText);
    }
  };

  // Determine if the currently selected item has text available
  const selectedJson: any = (selectedResult as any)?.rawJson || (selectedResult as any)?.json || null;
  const isPlaceholder = !!(selectedJson && typeof selectedJson === 'object' && (selectedJson._placeholder === true || selectedJson._status === 'processing'));
  const selectedText = selectedResult && !isPlaceholder ? getCurrentText() : '';
  const hasSelectedText = !!(selectedText && selectedText.trim().length);

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
                    const reqId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
                    console.log('👁️ VIEW REQUEST START:', {
                      reqId,
                      path: {
                        dossierId: path.dossierId,
                        segmentId: path.segmentId,
                        runId: path.runId,
                        draftId: path.draftId
                      }
                    });
                    if (path?.draftId) {
                      console.log('🧩 Requested draftId:', path.draftId);
                    }
                    // Highlight immediately so the selected version pill turns blue without waiting for fetch
                    setCurrentDisplayPath(path);
                    // Reset draft selector to reflect requested version for UI coherency
                    try {
                      const id = path.draftId || '';
                      const isConsensus = id.endsWith('_consensus_llm') || id.endsWith('_consensus_alignment');
                      if (isConsensus) {
                        onDraftSelect('consensus');
                      } else if (id) {
                        const mAlign = id.match(/_draft_(\d+)(?:_v[12])?$/);
                        const mRaw = id.match(/_v(\d+)_v[12]$/);
                        if (mAlign && mAlign[1]) {
                          const n = Math.max(0, parseInt(mAlign[1], 10) - 1);
                          onDraftSelect(n as any);
                        } else if (mRaw && mRaw[1]) {
                          const n = Math.max(0, parseInt(mRaw[1], 10) - 1);
                          onDraftSelect(n as any);
                        }
                      }
                    } catch {}
                    // Race-proof: only apply latest request
                    latestViewReqRef.current = reqId;
                    console.log('🔒 RACE GUARD: Set latestViewReqRef to', reqId);
                    try {
                      const resolved: ResolvedSelection = await resolveSelectionToText(path, undefined);
                      console.log('🔍 RACE CHECK: Current reqId:', reqId, 'Latest reqId:', latestViewReqRef.current);
                      if (latestViewReqRef.current !== reqId) {
                        console.log('⚠️ RACE ABORT: Request superseded, aborting', reqId);
                        return;
                      }

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
                        // Use the explicitly requested draftId from the path so versioned selections (v1/v2/Av1/Av2) are respected
                        const selectedDraftId = path.draftId;
                        console.log('🧩 Selected draft id (from path):', selectedDraftId);
                        const allDrafts = resolved.context?.run?.drafts || [];

                        // Extract transcription ID for saving alignment consensus
                        const transcriptionId = resolved.context?.run?.transcriptionId || (resolved.context?.run as any)?.transcription_id;

                        // Consensus detection (supports LLM and alignment consensus)
                        const isConsensusId = (id: string) =>
                          typeof id === 'string' &&
                          (id.endsWith('_consensus_llm') || id.endsWith('_consensus_alignment'));

                        // Separate raw drafts from consensus drafts
                        const rawDrafts = allDrafts.filter(d => !isConsensusId(d.id));
                        const consensusDrafts = allDrafts.filter(d => isConsensusId(d.id));

                        // Check if selected draft is consensus
                        const isConsensusSelected = selectedDraftId ? isConsensusId(selectedDraftId) : false;

                        // Compute selection context
                        // - If a specific versioned draftId was requested, keep it for display
                        // - Also compute base raw draft index for selection purposes
                        const isVersionedRaw = !!(selectedDraftId && /_v(1|2)$/.test(selectedDraftId));
                        const isVersionedAlign = !!(selectedDraftId && /_draft_\d+(_v(1|2))?$/.test(selectedDraftId));

                        let selectedIndex: number | 'consensus' = 0;
                        if (selectedDraftId) {
                          if (isConsensusSelected) {
                            selectedIndex = 'consensus';
                          } else {
                            if (isVersionedAlign) {
                              // Map alignment draft_n[_v1|v2] to raw draft index n-1
                              const m = selectedDraftId.match(/_draft_(\d+)(?:_v[12])?$/);
                              const n = m ? parseInt(m[1], 10) : 1;
                              selectedIndex = Math.max(0, (n - 1));
                            } else {
                              const baseCandidate = isVersionedRaw
                                ? selectedDraftId.replace(/_v(1|2)$/,'')
                                : selectedDraftId;
                              const baseIdx = rawDrafts.findIndex(d => d.id === baseCandidate);
                              selectedIndex = Math.max(0, baseIdx);
                            }
                          }
                        }

                        // STRICT: If a specific versioned id is provided, fetch only that id
                        const draftIds = selectedDraftId ? [selectedDraftId] : allDrafts.map(d => d.id);
                        const [jsonStrings, cleanTexts] = await Promise.all([
                          Promise.all(draftIds.map(draftId => textApi.getDraftJson(
                            transcriptionId || '',
                            draftId,
                            path.dossierId
                          ).then(js => (typeof js === 'string' ? js : (js ? JSON.stringify(js) : ''))).catch(() => ''))),
                          Promise.all(draftIds.map(draftId => textApi.getDraftText(
                            resolved.context?.run?.transcriptionId || (resolved.context?.run as any)?.transcription_id || '',
                            draftId,
                            path.dossierId
                          ).then(t => t || '').catch(() => '')))
                        ]);

                        // Build redundancy_analysis with ONLY raw drafts (exclude consensus)
                        const individual_results = rawDrafts.map((draft, i) => {
                          const draftIndexInAll = allDrafts.findIndex(d => d.id === draft.id);
                          return {
                            success: true,
                            text: jsonStrings[draftIndexInAll] || '',
                            display_text: cleanTexts[draftIndexInAll] || '',
                            model: 'dossier-selection',
                            confidence: 1.0,
                            draft_index: i
                          };
                        });

                        // Determine which text to show for the selected draft
                        let displayJson: any = '';
                        if (isConsensusSelected && consensusDrafts.length > 0) {
                          const consensusIndexInFetched = draftIds.findIndex(d => d === selectedDraftId);
                          displayJson = jsonStrings[consensusIndexInFetched] || '';
                        } else if (selectedDraftId) {
                          // Strict: only show the explicitly requested id; no fallback
                          const idxInFetched = draftIds.findIndex(d => d === selectedDraftId);
                          displayJson = idxInFetched >= 0 ? (jsonStrings[idxInFetched] || '') : '';
                        } else {
                          // No explicit selection: use base raw draft by index
                          const baseIdx = typeof selectedIndex === 'number' ? selectedIndex : 0;
                          const baseDraftId = rawDrafts[baseIdx]?.id;
                          const idxBase = draftIds.findIndex(d => d === baseDraftId);
                          displayJson = idxBase >= 0 ? (jsonStrings[idxBase] || '') : '';
                        }

                        const displayJsonStr = typeof displayJson === 'string' ? displayJson : (displayJson ? JSON.stringify(displayJson) : '');
                        // Also compute the clean text for the selected draft for TEXT tab usage
                        const selectedCleanText = (() => {
                          if (isConsensusSelected) {
                            const idxInFetched = draftIds.findIndex(d => d === selectedDraftId);
                            return cleanTexts[idxInFetched] || '';
                          }
                          if (selectedDraftId) {
                            const idxInFetched = draftIds.findIndex(d => d === selectedDraftId);
                            return idxInFetched >= 0 ? (cleanTexts[idxInFetched] || '') : '';
                          }
                          if (typeof selectedIndex === 'number') {
                            const baseDraftId = rawDrafts[selectedIndex as number]?.id;
                            const idxInFetched = draftIds.findIndex(d => d === baseDraftId);
                            return idxInFetched >= 0 ? (cleanTexts[idxInFetched] || '') : '';
                          }
                          return '';
                        })();

                        const syntheticResult = {
                          input: 'Dossier Selection',
                          status: 'completed' as const,
                          result: {
                            // Store the actual fetched content for the selected version
                            extracted_text: selectedCleanText || displayJsonStr,
                            metadata: {
                              model_used: 'dossier-selection',
                              service_type: 'dossier',
                              is_imported_draft: true,
                              selected_draft_index: typeof selectedIndex === 'number' ? selectedIndex : undefined,
                              is_consensus_selected: isConsensusSelected,
                              transcription_id: transcriptionId, // Add transcription ID for saving alignment consensus
                              dossier_id: path.dossierId, // Ensure dossier_id is present for alignment persistence
                              // Store the versioned draftId for text selection utils to use
                              selected_versioned_draft_id: selectedDraftId,
                              redundancy_analysis: {
                                enabled: false,
                                count: rawDrafts.length, // Only count raw drafts for alignment
                                individual_results,
                                // Keep consensus_text as cleaned text for the TEXT tab; do not include title
                                consensus_text: isConsensusSelected ? selectedCleanText : (resolved.text || '')
                              }
                            }
                          }
                        };
                        console.log('🎯 RESULTS VIEWER: About to call onSelectResult with:', {
                          reqId,
                          isDossierLevel: false,
                          path: {
                            dossierId: path.dossierId,
                            segmentId: path.segmentId,
                            runId: path.runId,
                            draftId: path.draftId
                          },
                          selectedDraftId,
                          selectedIndex,
                          isConsensusSelected,
                          metadata_selected_versioned_draft_id: syntheticResult.result.metadata.selected_versioned_draft_id,
                          extracted_text_length: syntheticResult.result.extracted_text?.length
                        });
                        onSelectResult(syntheticResult);
                        console.log('✅ RESULTS VIEWER: onSelectResult called successfully');
                        // For versioned raw selections, keep base raw draft index for editing selection
                        onDraftSelect((isConsensusSelected ? 'consensus' : (selectedIndex as any)));
                        setActiveTab('text');
                      }
                    } catch (e) {
                      if (latestViewReqRef.current !== reqId) return;
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
            {(isProcessing && !selectedResult) || (selectedResult && !hasSelectedText) ? (
              <div className="loading-view">
                <ParcelTracerLoader />
                <h4>Tracing Parcels...</h4>
                <p>Analyzing document geometry.</p>
              </div>
            ) : null}
            {selectedResult && hasSelectedText && (
              <div className="result-display-area" style={{ position: 'relative', paddingLeft: 40 }}>
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

                {/* Multi-draft editing limitation warning */}
                {editableDraftState && (editableDraftState as any).isMultiDraft && (
                  <div style={{
                    position: 'absolute',
                    top: '1rem',
                    left: '16px',
                    right: '16px',
                    padding: '8px 12px',
                    background: '#fff3cd',
                    border: '1px solid #ffc107',
                    borderRadius: '4px',
                    fontSize: '12px',
                    zIndex: 1000
                  }}>
                    ⚠️ <strong>Note:</strong> Editing currently only supported for single-draft transcriptions. This has {(editableDraftState as any).redundancyCount} drafts.
                  </div>
                )}

                {/* Left column ToolTray aligned with Copy column (Copy remains separate) */}
                <ToolTray topRem={7.8} leftPx={-48} zIndex={4000}>
                  {/* Edit */}
                  <button
                    className="final-draft-button"
                      onClick={async () => {
                      if (isEditing) {
                        if (onSaveEditedContent) await onSaveEditedContent();
                        setIsEditing(false);
                      } else {
                        setIsEditing(true);
                      }
                    }}
                    title={isEditing ? 'Save edits and close editor' : 'Enable Edit Mode'}
                  >
                    {isEditing ? 'Save' : 'Edit'}
                  </button>
                  {isEditing && (
                    <>
                      <button
                        className="final-draft-button"
                        onClick={async () => {
                          if (onResetToOriginal) await onResetToOriginal();
                          setIsEditing(false);
                        }}
                        title="Cancel edits and revert to original"
                        style={{ marginTop: 6 }}
                      >
                        Cancel
                      </button>
                      <button
                        className="final-draft-button"
                        onClick={async () => { 
                          if (onResetToOriginal) await onResetToOriginal(); 
                        }}
                        title="Reset to original content (deletes v2 and reverts to v1)"
                        style={{ marginTop: 6 }}
                      >
                        Reset to Original
                      </button>
                    </>
                  )}

                  {/* Alignment */}
                  <div style={{ height: 36, display: 'flex', alignItems: 'center' }}>
                    <AlignmentButton
                      visible={true}
                      onAlign={onAlign || (() => {})}
                      onTogglePanel={onToggleAlignmentPanel}
                      isAligning={isAligning}
                      disabled={!canAlign}
                      tooltip={!canAlign ? 'Requires redundancy > 1 (at least 2 drafts) to run alignment' : undefined}
                    />
                  </div>

                  {/* Inline confirm UI for overwriting (triggered by Select Final button) */}
                  {showFinalConfirm && (
                    <div style={{ marginTop: 6, background: '#fff', border: '1px solid #ddd', borderRadius: 6, padding: 8 }}>
                      <div style={{ fontSize: 12, marginBottom: 6 }}>Replace the existing final selection for this segment?</div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          className="final-draft-button"
                          onClick={async () => {
                            try {
                              const nextDraftId = showFinalConfirm.nextDraftId;
                              await setFinalForCurrentView(nextDraftId);
                            } finally {
                              setShowFinalConfirm(null);
                            }
                          }}
                        >
                          Confirm
                        </button>
                        <button className="final-draft-button" onClick={() => setShowFinalConfirm(null)}>Cancel</button>
                      </div>
                    </div>
                  )}

                  {/* Select Final */}
                  <div style={{ marginTop: 4 }}>
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
                      dossierId={currentDisplayPath?.dossierId || selectedResult?.result?.metadata?.dossier_id}
                      transcriptionId={selectedResult?.result?.metadata?.transcription_id}
                    currentDraftId={currentDisplayPath?.draftId || selectedResult?.result?.metadata?.selected_versioned_draft_id}
                    segmentId={currentDisplayPath?.segmentId}
                    />
                  </div>
                  {/* Finalize dossier when in dossier-level view */}
                  {isDossierView && (
                    <button
                      className="final-draft-button"
                      style={{ marginTop: 12 }}
                      title="Finalize this dossier (stitch all segments into a snapshot)"
                      onClick={async () => {
                        try {
                          const dossierId = currentDisplayPath?.dossierId || selectedResult?.result?.metadata?.dossier_id;
                          if (!dossierId) { alert('No dossier selected'); return; }
                          const { dossierApi } = await import('../../services/dossier/dossierApi');
                          const res = await dossierApi.finalizeDossier(String(dossierId));
                          alert(`Finalized dossier.\nSegments: ${(res?.segments || []).length}\nErrors: ${(res?.errors || []).length}`);
                        } catch (e: any) {
                          console.error('❌ Finalize failed', e);
                          alert(`Finalize failed: ${e?.message || e}`);
                        }
                      }}
                    >
                      Finalize Dossier
                    </button>
                  )}
                </ToolTray>

                {/* Controls toolbar: absolute, pinned under tabs; always above text viewer */}
                <div className="results-controls-toolbar" style={{
                  position: 'absolute',
                  top: -35,
                  right: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  zIndex: 2000
                }}>
                  <DraftSelector
                    redundancyAnalysis={
                      selectedResult.result?.metadata?.redundancy_analysis
                    }
                    onDraftSelect={onDraftSelect}
                    selectedDraft={selectedDraft}
                    alignmentResult={alignmentResult}
                  />
                </div>

                {/* Remove top edit controls clutter; position small spacer just above tabs to prevent overlap */}
                {isEditing && (
                  <div style={{ position: 'absolute', top: -12, left: 16, height: 1, width: 1, zIndex: 2000 }} />
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

                <div
                  className="result-tab-content"
                  key={`${selectedResult?.result?.metadata?.selected_versioned_draft_id ?? selectedResult?.result?.metadata?.transcription_id ?? ''}:${selectedDraft}:${activeTab}`}
                >
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
                          onSaveEditedContent={onSaveEditedContent}
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
                      ) : isEditing ? (
                        <div className="text-content-wrapper">
                          <textarea
                            className="text-editor"
                            style={{ width: '100%', height: '100%', padding: '1rem', fontFamily: 'monospace' }}
                            value={
                              (editableDraftState?.hasUnsavedChanges && editableDraftState?.editedFromDraft === selectedDraft)
                                ? editableDraftState.editedDraft.content
                                : getCurrentText()
                            }
                            onChange={(e) => onSetEditedContent && onSetEditedContent(e.target.value)}
                          />
                        </div>
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
      {/* Overlay viewer rendered at root so it can cover panels */}
      <ImageOverlayViewer zIndex={9999} />
    </div>
  );
}; 
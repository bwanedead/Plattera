import React, { useState, useEffect } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ImageEnhancementModal } from './ImageEnhancementModal';
import { DraftLoader } from './DraftLoader';
import { AlignmentPanel } from './AlignmentPanel';
import { ControlPanel } from './ControlPanel';
import { ResultsViewer } from './ResultsViewer';
import { AnimatedBorder } from '../AnimatedBorder';
import { AlignmentTableViewer } from './AlignmentTableViewer';
import { saveDraft, getDraftCount, DraftSession } from '../../utils/draftStorage';
import { useImageProcessing } from '../../hooks/useImageProcessing';
import { useAlignmentState } from '../../hooks/useAlignmentState';
import { useDraftSelection } from '../../hooks/useDraftSelection';


interface ImageProcessingWorkspaceProps {
  onExit: () => void;
  onNavigateToTextSchema?: () => void;
}

export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ 
  onExit, 
  onNavigateToTextSchema 
}) => {
  // Navigation button hover states
  const [homeHovered, setHomeHovered] = useState(false);
  const [textSchemaHovered, setTextSchemaHovered] = useState(false);
  const [isHistoryVisible, setIsHistoryVisible] = useState(true);
  const [showEnhancementModal, setShowEnhancementModal] = useState(false);
  const [showDraftLoader, setShowDraftLoader] = useState(false);
  const [draftCount, setDraftCount] = useState(0);

  // Custom hooks for state management
  const imageProcessing = useImageProcessing();
  const alignmentState = useAlignmentState();
  const draftSelection = useDraftSelection(
    imageProcessing.selectedResult, 
    alignmentState.selectedConsensusStrategy
  );

  // Reset draft selection when result changes
  useEffect(() => {
    if (imageProcessing.selectedResult) {
      draftSelection.resetDraftSelection();
      alignmentState.resetAlignmentState();
    }
  }, [imageProcessing.selectedResult]); // Fixed: removed hook objects from dependencies

  // Initialize draft count
  useEffect(() => {
    setDraftCount(getDraftCount());
  }, []);



  // Save draft functionality
  const handleSaveDraft = () => {
    if (!imageProcessing.selectedResult || imageProcessing.selectedResult.status !== 'completed' || !imageProcessing.selectedResult.result) {
      alert('No valid result to save');
      return;
    }

    try {
      const content = draftSelection.getRawText();
      
      // Get metadata for the selected draft
      let draftMetadata: any = {};
      const redundancyAnalysis = imageProcessing.selectedResult.result.metadata?.redundancy_analysis;
      
      if (redundancyAnalysis && typeof draftSelection.selectedDraft === 'number') {
        const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
        
        if (draftSelection.selectedDraft < individualResults.length) {
          const specificDraft = individualResults[draftSelection.selectedDraft];
          draftMetadata = {
            model_used: specificDraft.model || imageProcessing.selectedResult.result.metadata?.model_used || 'unknown',
            original_draft_index: draftSelection.selectedDraft,
            saved_draft_type: `draft_${draftSelection.selectedDraft + 1}`,
            confidence_score: specificDraft.confidence || 1.0,
            service_type: imageProcessing.selectedResult.result.metadata?.service_type || 'llm'
          };
        }
      } else {
        draftMetadata = {
          model_used: imageProcessing.selectedResult.result.metadata?.model_used || 'unknown',
          saved_draft_type: draftSelection.selectedDraft,
          confidence_score: imageProcessing.selectedResult.result.metadata?.confidence_score || 1.0,
          service_type: imageProcessing.selectedResult.result.metadata?.service_type || 'llm'
        };
      }
      
      const savedDraft = saveDraft(content, draftMetadata.model_used || 'unknown', draftMetadata);
      setDraftCount(getDraftCount());
      alert(`Draft saved successfully!\nDraft: ${draftMetadata.saved_draft_type || 'unknown'}\nID: ${savedDraft.draft_id}`);
    } catch (error) {
      alert('Failed to save draft: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  };

  // Load drafts functionality
  const handleLoadDrafts = (results: DraftSession[]) => {
    if (results.length === 0) return;

    // Create a combined session that mimics a redundancy result
    const combinedResult = {
      input: `Combined Drafts (${results.length} drafts)`,
      status: 'completed' as const,
      result: {
        extracted_text: results[0].result.extracted_text,
        metadata: {
          model_used: results.map(r => r.result.model_used).join(', '),
          service_type: 'imported-combined',
          tokens_used: 0,
          confidence_score: 1.0,
          imported_at: new Date().toISOString(),
          is_imported_draft: true,
          redundancy_analysis: {
            enabled: true,
            count: results.length,
            individual_results: results.map((result, index) => ({
              success: true,
              text: result.result.extracted_text,
              model: result.result.model_used,
              confidence: result.result.confidence_score,
              tokens_used: result.result.tokens_used,
              draft_index: index,
              imported_draft_id: result.result.metadata?.original_draft_id
            })),
            consensus_text: results[0].result.extracted_text,
            consensus_strategy: 'imported_first',
            confidence_scores: results.map(() => 1.0),
            average_confidence: 1.0
          }
        }
      }
    };

    imageProcessing.setSessionResults([combinedResult]);
    imageProcessing.selectResult(combinedResult);
    alignmentState.resetAlignmentState();
  };

  // Calculate Allotment sizes based on alignment panel visibility
  const getAllotmentSizes = () => {
    if (alignmentState.alignmentState.showAlignmentPanel) {
      return [300, 250, 450]; // ControlPanel, AlignmentPanel, ResultsViewer
    }
    return [300, 700]; // ControlPanel, ResultsViewer
  };

  return (
    <div className="image-processing-workspace">
      <div className="workspace-nav">
        <AnimatedBorder
          isHovered={homeHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-home" 
            onClick={onExit}
            onMouseEnter={() => setHomeHovered(true)}
            onMouseLeave={() => setHomeHovered(false)}
          >
            Home
          </button>
        </AnimatedBorder>
        <AnimatedBorder
          isHovered={textSchemaHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-next" 
            onClick={onNavigateToTextSchema}
            onMouseEnter={() => setTextSchemaHovered(true)}
            onMouseLeave={() => setTextSchemaHovered(false)}
          >
            Text to Schema
          </button>
        </AnimatedBorder>
      </div>
      
      <Allotment defaultSizes={getAllotmentSizes()} vertical={false}>
        <Allotment.Pane minSize={250} maxSize={400}>
          <ControlPanel
            stagedFiles={imageProcessing.stagedFiles}
            onDrop={imageProcessing.onDrop}
            onRemoveStagedFile={imageProcessing.removeStagedFile}
            draftCount={draftCount}
            onShowDraftLoader={() => setShowDraftLoader(true)}
            isProcessing={imageProcessing.isProcessing}
            onProcess={imageProcessing.handleProcess}
            availableModels={imageProcessing.availableModels}
            selectedModel={imageProcessing.selectedModel}
            onModelChange={imageProcessing.setSelectedModel}
            loadingModes={imageProcessing.loadingModes}
            availableExtractionModes={imageProcessing.availableExtractionModes}
            extractionMode={imageProcessing.extractionMode}
            onExtractionModeChange={imageProcessing.setExtractionMode}
            enhancementSettings={imageProcessing.enhancementSettings}
            onShowEnhancementModal={() => setShowEnhancementModal(true)}
            redundancySettings={imageProcessing.redundancySettings}
            onRedundancySettingsChange={imageProcessing.setRedundancySettings}
          />
        </Allotment.Pane>
        
        {alignmentState.alignmentState.showAlignmentPanel && (
          <Allotment.Pane minSize={200} maxSize={300}>
            <AlignmentPanel
              alignmentResult={alignmentState.alignmentState.alignmentResult}
              showHeatmap={alignmentState.alignmentState.showHeatmap}
              onToggleHeatmap={alignmentState.toggleHeatmap}
              onClose={alignmentState.closeAlignmentPanel}
              onToggleAlignmentTable={alignmentState.toggleAlignmentTable}
            />
          </Allotment.Pane>
        )}
        
        {alignmentState.showAlignmentTable && alignmentState.alignmentState.alignmentResult && (
          <Allotment.Pane minSize={200} maxSize={300}>
            <AlignmentTableViewer
              alignmentResult={alignmentState.alignmentState.alignmentResult}
              onClose={() => alignmentState.toggleAlignmentTable(false)}
            />
          </Allotment.Pane>
        )}
        
        <Allotment.Pane>
          <ResultsViewer
            isProcessing={imageProcessing.isProcessing}
            sessionResults={imageProcessing.sessionResults}
            selectedResult={imageProcessing.selectedResult}
            onSelectResult={(res: any) => {
              imageProcessing.selectResult(res);
              draftSelection.resetDraftSelection();
              alignmentState.resetAlignmentState();
            }}
            isHistoryVisible={isHistoryVisible}
            onToggleHistory={setIsHistoryVisible}
            getCurrentText={draftSelection.getCurrentText}
            getRawText={draftSelection.getRawText}
            isCurrentResultJson={draftSelection.isCurrentResultJson}
            onSaveDraft={handleSaveDraft}
            selectedDraft={draftSelection.selectedDraft}
            onDraftSelect={draftSelection.setSelectedDraft}
            alignmentResult={alignmentState.alignmentState.alignmentResult}
            showHeatmap={alignmentState.alignmentState.showHeatmap}
            onAlign={() => alignmentState.handleAlign(imageProcessing.selectedResult)}
            isAligning={alignmentState.alignmentState.isAligning}
          />
        </Allotment.Pane>
      </Allotment>
      
      {/* Image Enhancement Modal */}
      {showEnhancementModal && (
        <ImageEnhancementModal
          isOpen={showEnhancementModal}
          onClose={() => setShowEnhancementModal(false)}
          enhancementSettings={imageProcessing.enhancementSettings}
          onSettingsChange={imageProcessing.setEnhancementSettings}
          previewImage={imageProcessing.stagedFiles[0]}
        />
      )}

      {/* Draft Loader Modal */}
      <DraftLoader
        isOpen={showDraftLoader}
        onClose={() => setShowDraftLoader(false)}
        onLoadDrafts={handleLoadDrafts}
      />
    </div>
  );
}; 
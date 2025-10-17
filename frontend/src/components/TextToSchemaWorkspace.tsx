import React, { useState, useCallback, useEffect } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { AnimatedBorder } from './AnimatedBorder';
import { useTextToSchemaState, useWorkspaceNavigation } from '../hooks/useWorkspaceState';
import { convertTextToSchema, getTextToSchemaModels } from '../services/textToSchemaApi';
import { finalizedApi } from '../services/dossier/finalizedApi';
import { saveSchemaForDossier } from '../services/textToSchemaApi';
import { TextToSchemaControlPanel } from './text-to-schema/TextToSchemaControlPanel';
import { SchemaResultsTabs } from './text-to-schema/SchemaResultsTabs';
import { OriginalTextTab } from './text-to-schema/OriginalTextTab';
import { JsonSchemaTab } from './text-to-schema/JsonSchemaTab';
import { FieldViewTab } from './text-to-schema/FieldViewTab';
import { SchemaTab, TextToSchemaResult } from '../types/textToSchema';

interface TextToSchemaWorkspaceProps {
  onExit: () => void;
  onNavigateToImageText?: () => void;
}

export const TextToSchemaWorkspace: React.FC<TextToSchemaWorkspaceProps> = ({ 
  onExit, 
  onNavigateToImageText 
}) => {
  // State persistence hooks
  const { state, updateState } = useTextToSchemaState();
  const { setActiveWorkspace } = useWorkspaceNavigation();
  
  // Local UI state (not persisted)
  const [homeHovered, setHomeHovered] = useState(false);
  const [imageTextHovered, setImageTextHovered] = useState(false);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [selectedTab, setSelectedTab] = useState<SchemaTab>('original');

  // Finalized dossier selection state
  const [finalizedList, setFinalizedList] = useState<Array<{ dossier_id: string; title?: string; latest_generated_at?: string }>>([]);
  const [finalizedLoading, setFinalizedLoading] = useState(false);
  const [selectedFinalizedId, setSelectedFinalizedId] = useState<string | null>(
    (state as any)?.selectedFinalizedDossierId || null
  );

  // Debug the final draft text
  useEffect(() => {
    console.log('🔍 TEXT-TO-SCHEMA DEBUG: Final draft text type and value:', {
      type: typeof state.finalDraftText,
      value: state.finalDraftText,
      isString: typeof state.finalDraftText === 'string',
      length: state.finalDraftText ? state.finalDraftText.length : 'null'
    });
  }, [state.finalDraftText]);

  // Set active workspace when component mounts
  useEffect(() => {
    setActiveWorkspace('text-to-schema');
  }, [setActiveWorkspace]);

  // Load models on mount
  useEffect(() => {
    loadAvailableModels();
  }, []);

  // Load finalized dossiers list on mount
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setFinalizedLoading(true);
        const list = await finalizedApi.listFinalized();
        if (!mounted) return;
        setFinalizedList(list || []);
        // Detect staleness if selected dossier is chosen and timestamps differ
        if (selectedFinalizedId) {
          const entry = (list || []).find(e => String(e.dossier_id) === String(selectedFinalizedId));
          const latest = entry?.latest_generated_at;
          if (latest && state.selectedFinalizedSnapshotAt && latest !== state.selectedFinalizedSnapshotAt) {
            updateState({ isFinalizedSnapshotStale: true } as any);
          }
        }
      } catch (e) {
        console.warn('Failed to load finalized dossiers', e);
      } finally {
        if (!mounted) return;
        setFinalizedLoading(false);
      }
    })();

    const onFinalized = async (ev: Event) => {
      try {
        const d: any = (ev as CustomEvent)?.detail;
        if (d?.dossierId) {
          // refresh list and, if this is the selected dossier, reload snapshot
          const list = await finalizedApi.listFinalized();
          setFinalizedList(list || []);
          if (String(d.dossierId) === String(selectedFinalizedId)) {
            try {
              const data = await finalizedApi.getFinal(String(d.dossierId));
              const sectionsArr: string[] = Array.isArray(data?.sections)
                ? data.sections.map((s: any) => String(s?.text || '').trim())
                : (data?.stitched_text ? [String(data.stitched_text)] : []);
              const stitched = sectionsArr.filter(Boolean).join('\n\n');
              updateState({
                finalDraftText: stitched,
                finalDraftMetadata: {
                  source: 'finalized-dossier',
                  dossierId: String(d.dossierId),
                  dossierTitle: data?.dossier_title,
                  generatedAt: data?.generated_at
                },
                schemaResults: null,
                selectedFinalizedSnapshotAt: data?.generated_at || null,
                isFinalizedSnapshotStale: false,
                selectedFinalizedSections: sectionsArr
              } as any);
              setSelectedTab('original');
            } catch (e) {
              console.warn('Failed to reload finalized snapshot after event', e);
            }
          }
        }
      } catch {}
    };
    document.addEventListener('dossier:finalized', onFinalized as any);

    return () => {
      mounted = false;
      document.removeEventListener('dossier:finalized', onFinalized as any);
    };
  }, [selectedFinalizedId, state.selectedFinalizedSnapshotAt, updateState]);

  // Load available models
  const loadAvailableModels = async () => {
    try {
      const response = await getTextToSchemaModels();
      if (response.status === 'success' && response.models) {
        setAvailableModels(response.models);
      }
    } catch (error) {
      console.warn('Failed to load models, using defaults:', error);
      setAvailableModels({
        "gpt-4o": { name: "GPT-4o", provider: "openai" },
        "gpt-4": { name: "GPT-4", provider: "openai" },
      });
    }
  };

  // Handle model selection change
  const handleModelChange = useCallback((model: string) => {
    updateState({ selectedModel: model });
  }, [updateState]);

  // Handle tab change
  const handleTabChange = useCallback((tab: SchemaTab) => {
    setSelectedTab(tab);
  }, []);

  // Handle text-to-schema processing
  const handleStartTextToSchema = useCallback(async (directText?: string) => {
    // Use direct text if provided, otherwise use final draft text
    const textToProcess = directText || (typeof state.finalDraftText === 'string' 
      ? state.finalDraftText 
      : String(state.finalDraftText || ''));

    console.log('🔍 TEXT-TO-SCHEMA PROCESSING: Starting with text:', {
      isDirectInput: !!directText,
      textSource: directText ? 'direct-input' : 'final-draft',
      textLength: textToProcess.length
    });

    if (!textToProcess.trim()) {
      console.warn('No text available for processing');
      return;
    }

    updateState({ isProcessing: true, schemaResults: null });

    try {
      const response = await convertTextToSchema({
        text: textToProcess,
        model: state.selectedModel,
        parcel_id: `parcel-${Date.now()}`,
        // pass dossier id for metadata if a finalized dossier is selected
        dossier_id: selectedFinalizedId || undefined as any
      } as any);

      const result: TextToSchemaResult = {
        success: response.status === 'success',
        structured_data: response.structured_data,
        original_text: response.original_text,
        model_used: response.model_used,
        service_type: response.service_type,
        tokens_used: response.tokens_used,
        confidence_score: response.confidence_score,
        validation_warnings: response.validation_warnings,
        metadata: response.metadata
      };

      updateState({ schemaResults: result, isProcessing: false });
      console.log('✅ Schema processing completed:', result);

      // Persist schema to dossier if a finalized dossier is selected
      if (selectedFinalizedId && result.success && result.structured_data) {
        try {
          await saveSchemaForDossier({
            dossier_id: selectedFinalizedId,
            model_used: result.model_used,
            structured_data: result.structured_data,
            original_text: textToProcess,
            metadata: {
              ...(state.finalDraftMetadata || {}),
              selection_source: 'finalized_dossier'
            }
          });
          console.log('💾 Schema saved for dossier', selectedFinalizedId);
        } catch (e) {
          console.warn('Failed to save schema for dossier', e);
        }
      }
      
      // Auto-switch to Field View tab when results come in
      setSelectedTab('fields');
    } catch (error) {
      const errorResult: TextToSchemaResult = {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
      
      updateState({
        schemaResults: errorResult,
        isProcessing: false
      });
      console.error('❌ Schema processing failed:', error);
    }
  }, [state.finalDraftText, state.selectedModel, updateState, selectedFinalizedId]);

  // Finalized selection handler
  const handleSelectFinalized = useCallback(async (dossierId: string) => {
    try {
      setSelectedFinalizedId(dossierId);
      updateState({ selectedFinalizedDossierId: dossierId } as any);
      const data = await finalizedApi.getFinal(dossierId);
      const sectionsArr: string[] = Array.isArray(data?.sections)
        ? data.sections.map((s: any) => String(s?.text || '').trim())
        : (data?.stitched_text ? [String(data.stitched_text)] : []);
      const stitched = sectionsArr.filter(Boolean).join('\n\n');
      updateState({
        finalDraftText: stitched,
        finalDraftMetadata: {
          source: 'finalized-dossier',
          dossierId,
          dossierTitle: data?.dossier_title,
          generatedAt: data?.generated_at
        },
        schemaResults: null,
        selectedFinalizedSnapshotAt: data?.generated_at || null,
        isFinalizedSnapshotStale: false,
        selectedFinalizedSections: sectionsArr
      });
      setSelectedTab('original');
    } catch (e) {
      console.error('Failed to load finalized dossier', e);
    }
  }, [updateState]);

  // Render the appropriate tab content
  const renderTabContent = () => {
    // Ensure we have a valid string for display
    const finalText = typeof state.finalDraftText === 'string' 
      ? state.finalDraftText 
      : String(state.finalDraftText || '');

    switch (selectedTab) {
      case 'original':
        return finalText ? (
          <OriginalTextTab text={finalText} showSectionMarkers={true} sections={state.selectedFinalizedSections || undefined} />
        ) : (
          <div className="processing-placeholder">
            <p>No final draft available. Complete image-to-text processing to continue.</p>
          </div>
        );

      case 'json':
        return (
          <JsonSchemaTab
            schemaData={state.schemaResults?.structured_data}
            isSuccess={state.schemaResults?.success || false}
            error={state.schemaResults?.error}
          />
        );

      case 'fields':
        return (
          <FieldViewTab
            schemaData={state.schemaResults?.structured_data || null}
            isSuccess={state.schemaResults?.success || false}
            error={state.schemaResults?.error}
          />
        );

      default:
        return null;
    }
  };

  // Ensure we have a valid string for the control panel
  const finalText = typeof state.finalDraftText === 'string' 
    ? state.finalDraftText 
    : String(state.finalDraftText || '');

  return (
    <div className="text-to-schema-workspace">
      {/* Navigation Header */}
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
          isHovered={imageTextHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-prev" 
            onClick={onNavigateToImageText}
            onMouseEnter={() => setImageTextHovered(true)}
            onMouseLeave={() => setImageTextHovered(false)}
          >
            Image to Text
          </button>
        </AnimatedBorder>
      </div>

      {/* Main Content Area */}
      <Allotment defaultSizes={[300, 700]} vertical={false}>
        {/* Control Panel (Left) */}
        <Allotment.Pane minSize={250} maxSize={400}>
          <TextToSchemaControlPanel
            finalDraftText={finalText}
            finalDraftMetadata={state.finalDraftMetadata}
            selectedModel={state.selectedModel}
            availableModels={availableModels}
            isProcessing={state.isProcessing}
            onModelChange={handleModelChange}
            onStartProcessing={handleStartTextToSchema} // Now accepts optional text parameter
            finalizedDossiers={finalizedList}
            finalizedLoading={finalizedLoading}
            selectedFinalizedId={selectedFinalizedId}
            onSelectFinalized={handleSelectFinalized}
          />
        </Allotment.Pane>

        {/* Results Viewer (Right) */}
        <Allotment.Pane>
          <div className="results-viewer-panel">
            {!finalText && !state.schemaResults && (
              <div className="placeholder-view">
                <div className="placeholder-content">
                  <h3>Text to Schema Processing</h3>
                  <p>
                    Convert your final legal text into structured JSON data with organized PLSS Description and Metes & Bounds information.
                  </p>
                  <div className="placeholder-steps">
                    <div className="step">
                      <span className="step-number">1</span>
                      <span className="step-text">Complete image-to-text processing</span>
                    </div>
                    <div className="step">
                      <span className="step-number">2</span>
                      <span className="step-text">Select a final draft</span>
                    </div>
                    <div className="step">
                      <span className="step-number">3</span>
                      <span className="step-text">Convert to structured schema</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {(finalText || state.schemaResults) && (
              <div className="schema-results-viewer">
                <div className="viewer-header">
                  <h3>Processing Results</h3>
                </div>
                
                {/* Tab Navigation */}
                <SchemaResultsTabs
                  selectedTab={selectedTab}
                  onTabChange={handleTabChange}
                  hasResults={state.schemaResults?.success || false}
                />

                {/* Tab Content */}
                <div className="tab-content">
                  {renderTabContent()}
                </div>
              </div>
            )}
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  );
};
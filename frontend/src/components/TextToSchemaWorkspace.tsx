import React, { useState, useCallback, useEffect } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { AnimatedBorder } from './AnimatedBorder';
import { useTextToSchemaState, useWorkspaceNavigation } from '../hooks/useWorkspaceState';
import { convertTextToSchema, getTextToSchemaModels } from '../services/textToSchemaApi';
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
        parcel_id: `parcel-${Date.now()}`
      });

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
  }, [state.finalDraftText, state.selectedModel, updateState]);

  // Render the appropriate tab content
  const renderTabContent = () => {
    // Ensure we have a valid string for display
    const finalText = typeof state.finalDraftText === 'string' 
      ? state.finalDraftText 
      : String(state.finalDraftText || '');

    switch (selectedTab) {
      case 'original':
        return finalText ? (
          <OriginalTextTab text={finalText} />
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
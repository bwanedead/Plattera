import React, { useState, useCallback, useEffect } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './image-processing/ParcelTracerLoader';
import { AnimatedBorder } from './AnimatedBorder';
import { CopyButton } from './CopyButton';
import { useTextToSchemaState, useWorkspaceNavigation } from '../hooks/useWorkspaceState';
import { workspaceStateManager } from '../services/workspaceStateManager';

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

  // Set active workspace when component mounts
  useEffect(() => {
    setActiveWorkspace('text-to-schema');
  }, [setActiveWorkspace]);

  // Load models on mount
  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
  }, []);

  // API call for text-to-schema processing
  const processTextToSchema = async (text: string, model: string) => {
    console.log(' Starting text-to-schema processing:', {
      textLength: text.length,
      model
    });

    try {
      const response = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content_type: 'text-to-schema',
          text: text,
          model: model,
          cleanup_after: true
        })
      });

      const data = await response.json();
      console.log('📊 Schema processing response:', data);

      if (data.status === 'success') {
        return {
          success: true,
          structured_data: data.structured_data,
          metadata: {
            model_used: data.model_used,
            service_type: data.service_type,
            tokens_used: data.tokens_used,
            confidence_score: data.confidence_score,
            ...data.metadata
          }
        };
      } else {
        throw new Error(data.error || 'Processing failed');
      }
    } catch (error) {
      console.error('❌ Schema processing error:', error);
      throw error;
    }
  };

  // Handle start text-to-schema processing
  const handleStartTextToSchema = async () => {
    if (!state.finalDraftText) {
      console.warn('No final draft available for processing');
      return;
    }

    updateState({ isProcessing: true, schemaResults: null });

    try {
      const result = await processTextToSchema(state.finalDraftText, state.selectedModel);
      updateState({ schemaResults: result, isProcessing: false });
      console.log('✅ Schema processing completed:', result);
    } catch (error) {
      updateState({
        schemaResults: {
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error'
        },
        isProcessing: false
      });
      console.error('❌ Schema processing failed:', error);
    }
  };

  // API call for fetching models
  const fetchModelsAPI = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/models');
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      
      if (data.status === 'success' && data.models) {
        return data.models;
      } else {
        throw new Error(data.error || 'Invalid response format');
      }
    } catch (error) {
      console.warn('Failed to load models from API, using defaults:', error);
      return {
        "gpt-4o": { name: "GPT-4o", provider: "openai" },
        "gpt-4": { name: "GPT-4", provider: "openai" },
      };
    }
  };

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
          <div className="control-panel">
            <h2>Text to Schema</h2>
            
            {/* Final Draft Status */}
            <div className="final-draft-status">
              <h3>Final Draft Status</h3>
              {state.finalDraftText ? (
                <div className="draft-available">
                  <div className="status-indicator available">✅ Available</div>
                  <div className="draft-info">
                    <span className="draft-length">{state.finalDraftText.length} characters</span>
                    {state.finalDraftMetadata && (
                      <span className="draft-method">
                        Method: {state.finalDraftMetadata.selection_method || 'Unknown'}
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="draft-unavailable">
                  <div className="status-indicator unavailable">❌ Not Available</div>
                  <p className="draft-hint">
                    Complete image-to-text processing and select a final draft to continue.
                  </p>
                </div>
              )}
            </div>

            {/* Model Selection */}
            <div className="model-section">
              <label>Model Selection</label>
              <select 
                value={state.selectedModel} 
                onChange={(e) => updateState({ selectedModel: e.target.value })}
                className="model-selector"
              >
                {Object.entries(availableModels).map(([key, model]) => (
                  <option key={key} value={key}>
                    {model.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Process Button */}
            <button 
              onClick={handleStartTextToSchema}
              disabled={!state.finalDraftText || state.isProcessing}
              className="process-btn"
            >
              {state.isProcessing ? (
                <>
                  <ParcelTracerLoader />
                  <span>Processing Schema...</span>
                </>
              ) : (
                'Start Text to Schema'
              )}
            </button>

            {/* Processing Status */}
            {state.isProcessing && (
              <div className="processing-status">
                <div className="status-message">
                  Converting legal text to structured JSON...
                </div>
                <div className="status-details">
                  This may take a few moments depending on the text length.
                </div>
              </div>
            )}
          </div>
        </Allotment.Pane>

        {/* Results Viewer (Right) */}
        <Allotment.Pane>
          <div className="results-viewer-panel">
            {!state.finalDraftText && !state.schemaResults && (
              <div className="placeholder-view">
                <div className="placeholder-content">
                  <h3>Text to Schema Processing</h3>
                  <p>
                    Convert your final legal text into structured JSON data.
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

            {state.finalDraftText && !state.schemaResults && (
              <div className="final-draft-viewer">
                <div className="viewer-header">
                  <h3>Final Draft Content</h3>
                  <CopyButton
                    onCopy={() => navigator.clipboard.writeText(state.finalDraftText!)}
                    title="Copy final draft"
                  />
                </div>
                <div className="draft-content">
                  <pre className="draft-text">
                    {state.finalDraftText}
                  </pre>
                </div>
              </div>
            )}

            {state.schemaResults && (
              <div className="schema-results-viewer">
                <div className="viewer-header">
                  <h3>Schema Results</h3>
                  <CopyButton
                    onCopy={() => navigator.clipboard.writeText(JSON.stringify(state.schemaResults.structured_data, null, 2))}
                    title="Copy schema JSON"
                  />
                </div>
                
                {state.schemaResults.success ? (
                  <div className="schema-content">
                    <div className="schema-tabs">
                      <button className="tab active">JSON Schema</button>
                      <button className="tab">Metadata</button>
                    </div>
                    <div className="schema-output">
                      <pre className="json-schema">
                        {JSON.stringify(state.schemaResults.structured_data, null, 2)}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <div className="error-display">
                    <h4>Processing Error</h4>
                    <p>{state.schemaResults.error}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  );
}; 
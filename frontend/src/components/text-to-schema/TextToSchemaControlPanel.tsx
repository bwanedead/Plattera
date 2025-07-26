import React from 'react';
import { ParcelTracerLoader } from '../image-processing/ParcelTracerLoader';

interface TextToSchemaControlPanelProps {
  finalDraftText: string | null;
  finalDraftMetadata: any | null;
  selectedModel: string;
  availableModels: Record<string, any>;
  isProcessing: boolean;
  onModelChange: (model: string) => void;
  onStartProcessing: () => void;
}

export const TextToSchemaControlPanel: React.FC<TextToSchemaControlPanelProps> = ({
  finalDraftText,
  finalDraftMetadata,
  selectedModel,
  availableModels,
  isProcessing,
  onModelChange,
  onStartProcessing
}) => {
  // Ensure we have a valid string
  const text = typeof finalDraftText === 'string' ? finalDraftText : String(finalDraftText || '');
  const hasText = text && text.trim().length > 0;

  return (
    <div className="control-panel">
      <h2>Text to Schema</h2>
      
      {/* Final Draft Status */}
      <div className="final-draft-status">
        <h3>Final Draft Status</h3>
        {hasText ? (
          <div className="draft-available">
            <div className="status-indicator available">✅ Available</div>
            <div className="draft-info">
              <span className="draft-length">{text.length} characters</span>
              {finalDraftMetadata && (
                <span className="draft-method">
                  Method: {finalDraftMetadata.selection_method || 'Unknown'}
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
          value={selectedModel} 
          onChange={(e) => onModelChange(e.target.value)}
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
        onClick={onStartProcessing}
        disabled={!hasText || isProcessing}
        className="process-btn"
      >
        {isProcessing ? (
          <>
            <ParcelTracerLoader />
            <span>Processing Schema...</span>
          </>
        ) : (
          'Convert to Schema'
        )}
      </button>

      {/* Processing Status */}
      {isProcessing && (
        <div className="processing-status">
          <div className="status-message">
            Extracting PLSS Description and Metes & Bounds data...
          </div>
          <div className="status-details">
            This may take a few moments depending on the text complexity.
          </div>
        </div>
      )}
    </div>
  );
}; 
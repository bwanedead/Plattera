import React, { useState, useCallback } from 'react';
import { ParcelTracerLoader } from '../image-processing/ParcelTracerLoader';

type InputMode = 'final-draft' | 'direct-input';

interface TextToSchemaControlPanelProps {
  finalDraftText: string | null;
  finalDraftMetadata: any | null;
  selectedModel: string;
  availableModels: Record<string, any>;
  isProcessing: boolean;
  onModelChange: (model: string) => void;
  onStartProcessing: (text?: string) => void; // Updated to accept optional text
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
  const [inputMode, setInputMode] = useState<InputMode>('final-draft');
  const [directText, setDirectText] = useState('');

  // Ensure we have a valid string for final draft
  const finalText = typeof finalDraftText === 'string' ? finalDraftText : String(finalDraftText || '');
  const hasFinalDraft = finalText && finalText.trim().length > 0;
  
  // Determine which text to use based on mode
  const getActiveText = useCallback(() => {
    if (inputMode === 'direct-input') {
      return directText.trim();
    }
    return finalText.trim();
  }, [inputMode, directText, finalText]);

  const activeText = getActiveText();
  const hasValidText = activeText.length > 0;

  // Handle processing with the appropriate text
  const handleStartProcessing = useCallback(() => {
    const textToProcess = inputMode === 'direct-input' ? directText : undefined;
    onStartProcessing(textToProcess);
  }, [inputMode, directText, onStartProcessing]);

  // Handle paste functionality for direct input
  const handlePaste = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      setDirectText(text);
    } catch (error) {
      console.warn('Failed to read from clipboard:', error);
      // Fallback: focus the textarea for manual paste
      const textarea = document.getElementById('direct-text-input') as HTMLTextAreaElement;
      if (textarea) {
        textarea.focus();
      }
    }
  }, []);

  return (
    <div className="control-panel">
      <h2>Text to Schema</h2>
      
      {/* Input Mode Toggle */}
      <div className="input-mode-section">
        <h3>Input Source</h3>
        <div className="input-mode-toggle">
          <button
            className={`mode-button ${inputMode === 'final-draft' ? 'active' : ''}`}
            onClick={() => setInputMode('final-draft')}
            disabled={isProcessing}
          >
            📄 Use Final Draft
          </button>
          <button
            className={`mode-button ${inputMode === 'direct-input' ? 'active' : ''}`}
            onClick={() => setInputMode('direct-input')}
            disabled={isProcessing}
          >
            ✏️ Direct Text Input
          </button>
        </div>
      </div>

      {/* Input Source Status/Content */}
      {inputMode === 'final-draft' ? (
        <div className="final-draft-status">
          <h3>Final Draft Status</h3>
          {hasFinalDraft ? (
            <div className="draft-available">
              <div className="status-indicator available">✅ Available</div>
              <div className="draft-info">
                <span className="draft-length">{finalText.length} characters</span>
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
                Complete image-to-text processing and select a final draft, or switch to direct text input.
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="direct-input-section">
          <h3>Direct Text Input</h3>
          <div className="input-controls">
            <button 
              onClick={handlePaste}
              className="paste-button"
              disabled={isProcessing}
              title="Paste from clipboard"
            >
              📋 Paste Text
            </button>
            <span className="char-count">{directText.length} characters</span>
          </div>
          <textarea
            id="direct-text-input"
            value={directText}
            onChange={(e) => setDirectText(e.target.value)}
            placeholder="Paste or type your deed text here...

Example:
Right of Way Deed
This Indenture, made this 3rd day of August, A.D. 1915, by and between...

Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-five (75) West..."
            className="direct-text-input"
            disabled={isProcessing}
            rows={12}
          />
          {directText.trim() && (
            <div className="input-status">
              <div className="status-indicator available">✅ Text Ready</div>
            </div>
          )}
        </div>
      )}

      {/* Model Selection */}
      <div className="model-section">
        <label>Model Selection</label>
        <select 
          value={selectedModel} 
          onChange={(e) => onModelChange(e.target.value)}
          className="model-selector"
          disabled={isProcessing}
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
        onClick={handleStartProcessing}
        disabled={!hasValidText || isProcessing}
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
            {inputMode === 'direct-input' 
              ? 'Processing your directly entered text...'
              : 'Processing final draft from image-to-text...'
            }
          </div>
        </div>
      )}
    </div>
  );
}; 
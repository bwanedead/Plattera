import React from 'react';
import { useDropzone } from 'react-dropzone';

// Define interfaces for props to ensure type safety
interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

interface RedundancySettings {
  enabled: boolean;
  count: number;
  consensusStrategy: string;
}

interface ControlPanelProps {
  stagedFiles: File[];
  onDrop: (acceptedFiles: File[]) => void;
  onRemoveStagedFile: (fileName: string) => void;
  draftCount: number;
  onShowDraftLoader: () => void;
  isProcessing: boolean;
  onProcess: () => void;
  availableModels: Record<string, any>;
  selectedModel: string;
  onModelChange: (model: string) => void;
  loadingModes: boolean;
  availableExtractionModes: Record<string, { name: string; description: string }>;
  extractionMode: string;
  onExtractionModeChange: (mode: string) => void;
  enhancementSettings: EnhancementSettings;
  onShowEnhancementModal: () => void;
  redundancySettings: RedundancySettings;
  onRedundancySettingsChange: (settings: RedundancySettings) => void;
  boundingBoxSettings: {
    enabled: boolean;
    complexity: 'simple' | 'standard' | 'enhanced';
    model: string;
  };
  onBoundingBoxSettingsChange: (settings: {
    enabled: boolean;
    complexity: 'simple' | 'standard' | 'enhanced';
    model: string;
  }) => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  stagedFiles,
  onDrop,
  onRemoveStagedFile,
  draftCount,
  onShowDraftLoader,
  isProcessing,
  onProcess,
  availableModels,
  selectedModel,
  onModelChange,
  loadingModes,
  availableExtractionModes,
  extractionMode,
  onExtractionModeChange,
  enhancementSettings,
  onShowEnhancementModal,
  redundancySettings,
  onRedundancySettingsChange,
  boundingBoxSettings,
  onBoundingBoxSettingsChange,
}) => {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
    },
    multiple: true,
  });

  return (
    <div className="control-panel">
      <div className="panel-header">
        <h2>Image to Text</h2>
      </div>

      <div className="import-section">
        <label>Import Files</label>

        <div className="draft-loader-section">
          <button
            className="load-drafts-button"
            onClick={onShowDraftLoader}
            disabled={draftCount === 0}
          >
            📁 Load Saved Drafts ({draftCount})
          </button>
        </div>

        <div
          {...getRootProps()}
          className={`file-drop-zone ${isDragActive ? 'drag-active' : ''} ${
            stagedFiles.length > 0 ? 'has-files' : ''
          }`}
        >
          <input {...getInputProps()} />
          <div className="drop-zone-content">
            {stagedFiles.length === 0 ? (
              <>
                <div className="drop-icon">📁</div>
                <div className="drop-text">
                  <strong>Click to select files</strong> or drag and drop
                </div>
                <div className="drop-hint">PNG, JPG, JPEG, GIF, BMP, WebP</div>
              </>
            ) : (
              <>
                <div className="files-count">
                  {stagedFiles.length} file{stagedFiles.length > 1 ? 's' : ''} ready
                </div>
                <div className="drop-hint">Click to add more or drag additional files</div>
              </>
            )}
          </div>
        </div>

        {stagedFiles.length > 0 && (
          <div className="staged-files">
            {stagedFiles.map((file, index) => (
              <div key={index} className="staged-file">
                <span className="file-name">{file.name}</span>
                <button
                  className="remove-file"
                  onClick={() => onRemoveStagedFile(file.name)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="model-section">
        <label>AI Model</label>
        <select
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
          className="model-selector"
        >
          <option value="gpt-o4-mini">GPT-o4-mini (Recommended)</option>
          <option value="gpt-4o">GPT-4o</option>
          <option value="o3">o3 (Premium)</option>
          <option value="gpt-4">GPT-4</option>
        </select>
      </div>

      <div className="extraction-section">
        <label>Extraction Mode</label>
        <select
          value={extractionMode}
          onChange={(e) => onExtractionModeChange(e.target.value)}
          className="extraction-selector"
          disabled={loadingModes}
        >
          {loadingModes ? (
            <option>Loading modes...</option>
          ) : (
            Object.entries(availableExtractionModes).map(([modeId, modeInfo]) => (
              <option key={modeId} value={modeId}>
                {modeInfo.name} - {modeInfo.description}
              </option>
            ))
          )}
        </select>
      </div>

      <div className="enhancement-section">
        <button
          className="enhancement-modal-btn"
          onClick={onShowEnhancementModal}
          disabled={isProcessing}
        >
          🎨 Image Enhancement
        </button>
        <small className="enhancement-hint">
          Current: C:{enhancementSettings.contrast.toFixed(1)} S:
          {enhancementSettings.sharpness.toFixed(1)} B:
          {enhancementSettings.brightness.toFixed(1)} Col:
          {enhancementSettings.color.toFixed(1)}
        </small>
      </div>

      <div className="redundancy-section">
        <label>Redundancy Filter</label>
        <div className="redundancy-controls">
          <div className="redundancy-toggle">
            <input
              type="checkbox"
              id="redundancy-enabled"
              checked={redundancySettings.enabled}
              onChange={(e) =>
                onRedundancySettingsChange({
                  ...redundancySettings,
                  enabled: e.target.checked,
                })
              }
            />
            <label htmlFor="redundancy-enabled">Enable Redundancy</label>
          </div>

          {redundancySettings.enabled && (
            <>
              <div className="redundancy-slider-group">
                <label htmlFor="redundancy-count">
                  Redundancy Count: {redundancySettings.count}
                </label>
                <input
                  type="range"
                  id="redundancy-count"
                  min="1"
                  max="10"
                  value={redundancySettings.count}
                  onChange={(e) =>
                    onRedundancySettingsChange({
                      ...redundancySettings,
                      count: parseInt(e.target.value),
                    })
                  }
                  className="redundancy-slider"
                />
                <div className="redundancy-hint">
                  {redundancySettings.count === 1
                    ? 'No redundancy'
                    : redundancySettings.count <= 3
                    ? 'Light redundancy'
                    : redundancySettings.count <= 5
                    ? 'Medium redundancy'
                    : 'Heavy redundancy'}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="bounding-box-section">
        <label>Bounding Box Detection</label>
        <div className="bounding-box-controls">
          <div className="bounding-box-toggle">
            <input
              type="checkbox"
              id="bounding-box-enabled"
              checked={boundingBoxSettings.enabled}
              onChange={(e) => onBoundingBoxSettingsChange({
                ...boundingBoxSettings,
                enabled: e.target.checked,
              })}
            />
            <label htmlFor="bounding-box-enabled">Enable Bounding Box Detection</label>
          </div>
          
          {boundingBoxSettings.enabled && (
            <>
              <div className="complexity-selector">
                <label>Analysis Complexity</label>
                <select 
                  value={boundingBoxSettings.complexity}
                  onChange={(e) => onBoundingBoxSettingsChange({
                    ...boundingBoxSettings,
                    complexity: e.target.value as 'simple' | 'standard' | 'enhanced'
                  })}
                >
                  <option value="simple">Simple (Clean Text)</option>
                  <option value="standard">Standard (Mixed Handwriting)</option>
                  <option value="enhanced">Enhanced (Complex Cursive)</option>
                </select>
              </div>
              
              <div className="model-selector">
                <label>Bounding Box Model</label>
                <select 
                  value={boundingBoxSettings.model}
                  onChange={(e) => onBoundingBoxSettingsChange({
                    ...boundingBoxSettings,
                    model: e.target.value
                  })}
                >
                  <option value="gpt-4o">GPT-4o (Recommended)</option>
                  <option value="gpt-o4-mini">GPT-o4-mini</option>
                  <option value="o3">o3 (Premium)</option>
                </select>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="process-section">
        <button
          className={`process-button ${isProcessing ? 'processing' : ''}`}
          onClick={onProcess}
          disabled={stagedFiles.length === 0 || isProcessing}
        >
          {isProcessing
            ? 'Processing...'
            : `Process ${stagedFiles.length} File${
                stagedFiles.length !== 1 ? 's' : ''
              }`}
        </button>
      </div>
    </div>
  );
}; 
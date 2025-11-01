import React from 'react';
import { useDropzone } from 'react-dropzone';
import { dossierHighlightBus } from '../../services/dossier/dossierHighlightBus';
import { DossierPicker } from '../dossier/DossierPicker';

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

interface ConsensusSettings {
  enabled: boolean;
  model: string;
}

interface ControlPanelProps {
  stagedFiles: File[];
  onDrop: (acceptedFiles: File[]) => void;
  onRemoveStagedFile: (fileName: string) => void;
  draftCount: number;
  onShowDraftLoader: () => void;
  isProcessing: boolean;
  onProcess: () => void;
  // processing mode is now auto-detected in the hook; no manual toggle
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
  consensusSettings: ConsensusSettings;
  onConsensusSettingsChange: (settings: ConsensusSettings) => void;
  // DOSSIER SUPPORT
  selectedDossierId?: string | null;
  onDossierChange?: (dossierId: string | null) => void;
  dossiers?: { id: string; title?: string; name?: string; segments?: { id: string; name: string }[] }[];
  selectedSegmentId?: string | null; // null => new segment
  onSegmentChange?: (segmentId: string | null) => void;
  // Queue status
  processingQueue?: { fileName: string; jobId?: string; status: 'queued' | 'processing' | 'done' | 'error' }[];
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  stagedFiles,
  onDrop,
  onRemoveStagedFile,
  draftCount,
  onShowDraftLoader,
  isProcessing,
  onProcess,
  // processingMode removed; auto-managed
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
  consensusSettings,
  onConsensusSettingsChange,
  // DOSSIER SUPPORT
  selectedDossierId,
  onDossierChange,
  dossiers = [],
  selectedSegmentId = null,
  onSegmentChange,
  processingQueue = [],
}) => {
  // Removed noisy debug logs for production clarity

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'],
    },
    multiple: true,
    noDragEventsBubbling: true,
  });

  // Desktop bridge: consume forwarded files from Tauri file-drop
  React.useEffect(() => {
    const handler = (ev: Event) => {
      try {
        const files: File[] = (ev as CustomEvent)?.detail?.files || [];
        if (Array.isArray(files) && files.length > 0) {
          onDrop(files);
        }
      } catch {}
    };
    document.addEventListener('files:dropped', handler as any);
    return () => document.removeEventListener('files:dropped', handler as any);
  }, [onDrop]);

  return (
    <div className="control-panel">
      <div className="panel-header">
        <h2>Image to Text</h2>
      </div>

      <div className="import-section">
        <label>Import Files</label>

        {/* Mode toggle removed: mode auto-selected based on number of staged files */}

        {/* Removed testing-only load saved drafts button */}

        <div
          {...getRootProps()}
          data-allow-drop="true"
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
                  <strong>Click to select files</strong>
                </div>
                <div className="drop-hint">PNG, JPG, JPEG, GIF, BMP, WebP</div>
              </>
            ) : (
              <>
                <div className="files-count">
                  {stagedFiles.length} file{stagedFiles.length > 1 ? 's' : ''} ready
                </div>
                <div className="drop-hint">Click to add more</div>
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

      {/* DOSSIER SELECTION */}
      <div className="dossier-section">
        <label>Dossier Association</label>
        <DossierPicker
          dossiers={dossiers}
          value={selectedDossierId || null}
          onChange={(id) => onDossierChange?.(id)}
          className="dossier-selector"
        />
        <small className="dossier-hint">
          Choose an existing dossier or auto-create a new one
        </small>
        {selectedDossierId && (
          <div className="segment-subsection" style={{ marginTop: '0.5rem' }}>
            <label>Segment</label>
            <select
              value={selectedSegmentId || 'new'}
              onChange={(e) => onSegmentChange?.(e.target.value === 'new' ? null : e.target.value)}
              className="segment-selector"
            >
              <option value="new">Add as new segment</option>
              {(dossiers.find(d => d.id === selectedDossierId)?.segments || []).map(s => (
                <option key={s.id} value={s.id}>Add as run to: {s.name}</option>
              ))}
            </select>
            <small className="dossier-hint">Default: new segment. Or pick an existing segment to add a new run.</small>
          </div>
        )}
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

      {/* LLM Consensus Settings */}
      <div className="consensus-section">
        <label>AI Consensus</label>
        <div className="redundancy-controls">
          <div className="redundancy-toggle">
            <input
              type="checkbox"
              id="consensus-enabled"
              checked={consensusSettings.enabled}
              onChange={(e) => onConsensusSettingsChange({ ...consensusSettings, enabled: e.target.checked })}
            />
            <label htmlFor="consensus-enabled">Enable LLM Consensus</label>
          </div>

          {consensusSettings.enabled && (
            <div className="consensus-strategy-group" style={{ marginTop: '0.5rem' }}>
              <label htmlFor="consensus-model">Consensus Model</label>
              <select
                id="consensus-model"
                value={consensusSettings.model}
                onChange={(e) => onConsensusSettingsChange({ ...consensusSettings, model: e.target.value })}
                className="consensus-strategy-select"
              >
                <option value="gpt-5-consensus">GPT-5 (Consensus)</option>
                <option value="gpt-5-mini-consensus">GPT-5 Mini (Consensus)</option>
                <option value="gpt-5-nano-consensus">GPT-5 Nano (Consensus)</option>
              </select>
              <small className="consensus-strategy-hint">Runs only when redundancy is enabled (>1 drafts)</small>
            </div>
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
            : (stagedFiles.length <= 1
                ? `Process 1 File`
                : `Queue ${Math.min(stagedFiles.length, 20)} File${stagedFiles.length !== 1 ? 's' : ''}`)}
        </button>
      </div>

      {/* In-progress queue list persists after staging clears */}
      {(isProcessing || (processingQueue && processingQueue.length > 0)) && (
        <div className="queue-status" style={{ marginTop: '0.75rem' }}>
          <label>In-Progress Queue</label>
          <ul style={{ margin: 0, paddingLeft: '1rem' }}>
            {processingQueue.map((q, idx) => {
              const badge = q.status === 'processing' ? 'Processing' : q.status === 'queued' ? 'Queued' : q.status === 'done' ? 'Done' : 'Error';
              return (
                <li key={q.jobId || `${q.fileName}-${idx}`} style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {badge} • {q.fileName}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}; 
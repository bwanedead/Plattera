import React, { useState, useCallback } from 'react';
import { ParcelTracerLoader } from '../image-processing/ParcelTracerLoader';
import type { AgentTapeEvent, AgentTapeStatus } from '../../services/agentLoopApi';

type InputMode = 'finalized' | 'direct-input';

interface TextToSchemaControlPanelProps {
  finalDraftText: string | null;
  finalDraftMetadata: any | null;
  engine: 'legacy' | 'agent_loop';
  selectedModel: string;
  agentLoopModel: string;
  availableModels: Record<string, any>;
  isProcessing: boolean;
  agentLoopRunStatus?: string | null;
  agentLoopStatusMessage?: string | null;
  agentLoopRunId?: string | null;
  agentLoopLiveStatus?: AgentTapeStatus | null;
  agentLoopTapeEvents?: AgentTapeEvent[];
  agentLoopStreamConnected?: boolean;
  onEngineChange: (engine: 'legacy' | 'agent_loop') => void;
  onModelChange: (model: string) => void;
  onAgentLoopModelChange: (model: string) => void;
  onStartProcessing: (text?: string) => void; // Updated to accept optional text
  onResumePolling?: () => void;
  finalizedDossiers: Array<{ dossier_id: string; title?: string; latest_generated_at?: string }>;
  finalizedLoading: boolean;
  selectedFinalizedId: string | null | undefined;
  onSelectFinalized: (dossierId: string) => void;
}

export const TextToSchemaControlPanel: React.FC<TextToSchemaControlPanelProps> = ({
  finalDraftText,
  finalDraftMetadata,
  engine,
  selectedModel,
  agentLoopModel,
  availableModels,
  isProcessing,
  agentLoopRunStatus,
  agentLoopStatusMessage,
  agentLoopRunId,
  agentLoopLiveStatus,
  agentLoopTapeEvents = [],
  agentLoopStreamConnected = false,
  onEngineChange,
  onModelChange,
  onAgentLoopModelChange,
  onStartProcessing,
  onResumePolling,
  finalizedDossiers,
  finalizedLoading,
  selectedFinalizedId,
  onSelectFinalized
}) => {
  const [inputMode, setInputMode] = useState<InputMode>('finalized');
  const [directText, setDirectText] = useState('');
  const tapeEvents = Array.isArray(agentLoopTapeEvents) ? agentLoopTapeEvents : [];

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
            className={`mode-button ${inputMode === 'finalized' ? 'active' : ''}`}
            onClick={() => setInputMode('finalized')}
            disabled={isProcessing}
          >
            📦 Finalized Dossier
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
      {inputMode === 'finalized' ? (
        <div className="finalized-selector">
          <h3>Choose Finalized Dossier</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              value={selectedFinalizedId || ''}
              onChange={(e) => e.target.value && onSelectFinalized(e.target.value)}
              disabled={isProcessing || finalizedLoading}
              className="model-selector"
              title="Select a finalized dossier snapshot"
            >
              <option value="">{finalizedLoading ? 'Loading...' : 'Select a finalized dossier…'}</option>
              {finalizedDossiers.map(f => (
                <option key={f.dossier_id} value={f.dossier_id}>
                  {(f.title || f.dossier_id) + (f.latest_generated_at ? ` — ${new Date(f.latest_generated_at).toLocaleString()}` : '')}
                </option>
              ))}
            </select>
            {finalText?.trim()
              ? <span className="status-indicator available">✅ Loaded</span>
              : <span className="status-indicator unavailable">❌ Not Loaded</span>}
            {/* Manual refresh control */}
            <button
              className="mode-button"
              style={{ padding: '4px 8px' }}
              disabled={!selectedFinalizedId || isProcessing}
              onClick={() => selectedFinalizedId && onSelectFinalized(selectedFinalizedId)}
              title="Refresh finalized snapshot"
            >
              Refresh
            </button>
          </div>
          {!!finalText?.length && (
            <div className="draft-info">
              <span className="draft-length">{finalText.length} characters</span>
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
            rows={18}
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
        <label>Engine</label>
        <select
          value={engine}
          onChange={(e) => onEngineChange(e.target.value as 'legacy' | 'agent_loop')}
          className="model-selector"
          disabled={isProcessing}
        >
          <option value="legacy">Legacy</option>
          <option value="agent_loop">New (Agent Loop)</option>
        </select>
      </div>

      {engine === 'legacy' ? (
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
      ) : (
        <div className="model-section">
          <label>Agent Loop Model</label>
          <select
            value={agentLoopModel}
            onChange={(e) => onAgentLoopModelChange(e.target.value)}
            className="model-selector"
            disabled={isProcessing}
          >
            <option value="gpt-5.2">GPT-5.2</option>
          </select>
        </div>
      )}

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
            {engine === 'agent_loop'
              ? 'Running agent loop...'
              : 'Extracting PLSS Description and Metes & Bounds data...'}
          </div>
          <div className="status-details">
            {inputMode === 'direct-input' 
              ? 'Processing your directly entered text...'
              : 'Processing final draft from image-to-text...'
            }
          </div>
        </div>
      )}
      {!isProcessing && engine === 'agent_loop' && agentLoopRunStatus && (
        <div className="processing-status">
          <div className="status-message">Agent Loop Status: {agentLoopRunStatus}</div>
          {agentLoopStatusMessage && <div className="status-details">{agentLoopStatusMessage}</div>}
          {agentLoopRunStatus === 'running' && (
            <button
              className="mode-button"
              style={{ marginTop: 8, padding: '4px 8px' }}
              onClick={() => onResumePolling && onResumePolling()}
            >
              Keep Polling
            </button>
          )}
        </div>
      )}
      {engine === 'agent_loop' && (agentLoopRunId || tapeEvents.length > 0 || agentLoopLiveStatus) && (
        <div
          style={{
            marginTop: 10,
            border: '1px solid rgba(120,120,120,0.35)',
            borderRadius: 10,
            padding: 10,
            background: 'linear-gradient(180deg, rgba(18,20,24,0.92), rgba(12,13,16,0.95))',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 0.3, opacity: 0.95 }}>Agent Loop Activity</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 999,
                  display: 'inline-block',
                  background: agentLoopStreamConnected ? '#27c36f' : '#f0b23f',
                  boxShadow: agentLoopStreamConnected ? '0 0 8px rgba(39,195,111,0.6)' : '0 0 8px rgba(240,178,63,0.35)',
                }}
              />
              <span style={{ fontSize: 11, opacity: 0.8 }}>
                {agentLoopStreamConnected ? 'Live stream' : 'Polling fallback'}
              </span>
            </div>
          </div>

          {agentLoopLiveStatus && (
            <div
              style={{
                marginTop: 8,
                padding: '8px 9px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(255,255,255,0.02)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                {agentLoopLiveStatus.stage && (
                  <span
                    style={{
                      fontSize: 10,
                      textTransform: 'uppercase',
                      letterSpacing: 0.5,
                      padding: '2px 6px',
                      borderRadius: 999,
                      background: 'rgba(255,255,255,0.08)',
                      border: '1px solid rgba(255,255,255,0.12)',
                    }}
                  >
                    {agentLoopLiveStatus.stage}
                  </span>
                )}
                {agentLoopLiveStatus.phase && (
                  <span
                    style={{
                      fontSize: 10,
                      textTransform: 'uppercase',
                      letterSpacing: 0.45,
                      padding: '2px 6px',
                      borderRadius: 999,
                      background: 'rgba(54, 129, 255, 0.12)',
                      border: '1px solid rgba(54, 129, 255, 0.22)',
                      color: 'rgba(180, 214, 255, 0.95)',
                    }}
                  >
                    {agentLoopLiveStatus.phase}
                  </span>
                )}
                {typeof agentLoopLiveStatus.iteration === 'number' && (
                  <span style={{ fontSize: 11, opacity: 0.8 }}>iter {agentLoopLiveStatus.iteration}</span>
                )}
                {agentLoopLiveStatus.action_type && (
                  <span style={{ fontSize: 11, opacity: 0.9 }}>{agentLoopLiveStatus.action_type}</span>
                )}
              </div>
              {agentLoopLiveStatus.line1 && (
                <div style={{ fontSize: 12, lineHeight: 1.35, fontWeight: 600 }}>
                  {agentLoopLiveStatus.line1}
                </div>
              )}
              {agentLoopLiveStatus.line2 && (
                <div style={{ marginTop: 3, fontSize: 11, lineHeight: 1.35, opacity: 0.82 }}>
                  {agentLoopLiveStatus.line2}
                </div>
              )}
            </div>
          )}

          {tapeEvents.length > 0 && (
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {tapeEvents.slice(0, 5).map((evt, idx) => {
                const status = evt.status || {};
                const key = `${evt.seq ?? 'na'}-${idx}`;
                return (
                  <div
                    key={key}
                    style={{
                      borderRadius: 7,
                      padding: '6px 8px',
                      background: 'rgba(255,255,255,0.018)',
                      border: '1px solid rgba(255,255,255,0.06)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {typeof status.iteration === 'number' && (
                        <span style={{ fontSize: 10, opacity: 0.75 }}>#{status.iteration}</span>
                      )}
                      {status.stage && (
                        <span style={{ fontSize: 10, opacity: 0.8, textTransform: 'uppercase' }}>{status.stage}</span>
                      )}
                      {status.phase && (
                        <span style={{ fontSize: 10, opacity: 0.78, textTransform: 'uppercase' }}>{status.phase}</span>
                      )}
                      {status.action_type && (
                        <span style={{ fontSize: 10, opacity: 0.9 }}>{status.action_type}</span>
                      )}
                    </div>
                    <div style={{ fontSize: 11, lineHeight: 1.3, marginTop: 2 }}>
                      {status.line1 || 'Agent event'}
                    </div>
                    {status.line2 && (
                      <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.76, marginTop: 2 }}>
                        {status.line2}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

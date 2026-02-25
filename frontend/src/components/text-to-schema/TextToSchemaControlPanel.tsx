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
  const [agentActivityDebug, setAgentActivityDebug] = useState(false);
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
  const standardAgentMessage = (status: AgentTapeStatus | null | undefined): string => {
    if (!status) return 'Working on this deed...';
    const delta = typeof status.display_delta === 'string' ? status.display_delta.trim() : '';
    if (delta) return delta;
    const action = String(status.action_type || '').toLowerCase();
    const outcome = String(status.outcome || '').toLowerCase();
    const stage = String(status.stage || '').toLowerCase();
    const reason = String(status.reason_code || '').toLowerCase();

    if (stage === 'refused' || reason.includes('refus')) {
      return 'I hit a problem with the current step and am adjusting the next move.';
    }
    if (stage === 'parse_failed' || stage === 'resync') {
      return 'I am recovering from a formatting issue and resyncing the next step.';
    }
    if (action === 'hydrate_deed' || action === 'open_artifact' || action === 'open_text_spans') {
      return 'Reviewing deed text and saved results to confirm the next change.';
    }
    if (action === 'retrieve_evidence') {
      return 'Looking up supporting context to resolve an ambiguity in the deed.';
    }
    if (action === 'draft_ir' || action === 'propose_patch' || action === 'set_graph_requirements') {
      return stage === 'proposed'
        ? 'Preparing the next parcel draft from the deed description.'
        : 'Updating the parcel draft from the deed description.';
    }
    if (action === 'compile' || action === 'judge') {
      return stage === 'proposed'
        ? 'Checking the current parcel draft for issues before the next revision.'
        : 'Checking the current parcel draft and updating the latest issue report.';
    }
    if (action === 'bundle') {
      return stage === 'proposed'
        ? 'Preparing the current parcel results for the next mapping steps.'
        : 'Packaging the current parcel results for mapping and review.';
    }
    if (action === 'georeference') {
      return stage === 'proposed'
        ? 'Preparing to place the parcel on the map.'
        : 'Placing the parcel on the map and saving the result.';
    }
    if (action === 'validate') {
      return stage === 'proposed'
        ? 'Preparing to validate the mapped parcel result.'
        : 'Checking the mapped parcel result for issues and accuracy.';
    }
    if (action === 'declare_done' || outcome === 'executed') {
      return 'Updating the run status and saving the latest outputs.';
    }
    return 'Working on this deed...';
  };
  const standardAgentSecondary = (status: AgentTapeStatus | null | undefined): string | null => {
    if (!status) return null;
    if (typeof status.iteration === 'number') return `Step ${status.iteration}`;
    return null;
  };
  const formatTapeTime = (epochSeconds?: number) => {
    if (typeof epochSeconds !== 'number' || !Number.isFinite(epochSeconds)) return null;
    try {
      return new Date(epochSeconds * 1000).toLocaleTimeString();
    } catch {
      return null;
    }
  };

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
              <button
                type="button"
                onClick={() => setAgentActivityDebug(v => !v)}
                style={{
                  fontSize: 10,
                  padding: '2px 6px',
                  borderRadius: 999,
                  border: '1px solid rgba(255,255,255,0.18)',
                  background: agentActivityDebug ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.04)',
                  color: 'rgba(255,255,255,0.9)',
                  cursor: 'pointer',
                }}
                title={agentActivityDebug ? 'Switch to Standard activity view' : 'Show debug event details'}
              >
                {agentActivityDebug ? 'Debug' : 'Standard'}
              </button>
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
                {agentLoopLiveStatus.status_chip && (
                  <span
                    style={{
                      fontSize: 10,
                      letterSpacing: 0.35,
                      padding: '2px 7px',
                      borderRadius: 999,
                      background: 'rgba(76, 195, 255, 0.10)',
                      border: '1px solid rgba(76, 195, 255, 0.24)',
                      color: 'rgba(196, 238, 255, 0.98)',
                      fontWeight: 700,
                    }}
                  >
                    {agentLoopLiveStatus.status_chip}
                  </span>
                )}
                {typeof agentLoopLiveStatus.iteration === 'number' && (
                  <span style={{ fontSize: 11, opacity: 0.8 }}>iter {agentLoopLiveStatus.iteration}</span>
                )}
                {agentActivityDebug && agentLoopLiveStatus.stage && (
                  <span style={{ fontSize: 10, opacity: 0.8, textTransform: 'uppercase' }}>{agentLoopLiveStatus.stage}</span>
                )}
                {agentActivityDebug && agentLoopLiveStatus.phase && (
                  <span style={{ fontSize: 10, opacity: 0.78, textTransform: 'uppercase' }}>{agentLoopLiveStatus.phase}</span>
                )}
                {agentActivityDebug && agentLoopLiveStatus.action_type && (
                  <span style={{ fontSize: 10, opacity: 0.9 }}>{agentLoopLiveStatus.action_type}</span>
                )}
                {agentActivityDebug && agentLoopLiveStatus.outcome && (
                  <span style={{ fontSize: 10, opacity: 0.75 }}>{agentLoopLiveStatus.outcome}</span>
                )}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.35, fontWeight: 600 }}>
                {standardAgentMessage(agentLoopLiveStatus)}
              </div>
              {!agentActivityDebug && standardAgentSecondary(agentLoopLiveStatus) && (
                <div style={{ marginTop: 3, fontSize: 11, lineHeight: 1.35, opacity: 0.82 }}>
                  {standardAgentSecondary(agentLoopLiveStatus)}
                </div>
              )}
              {agentActivityDebug && (
                <>
                  {agentLoopLiveStatus.display_delta && (
                    <div style={{ marginTop: 3, fontSize: 10, lineHeight: 1.3, opacity: 0.9 }}>
                      Narration: {agentLoopLiveStatus.display_delta}
                    </div>
                  )}
                  {agentLoopLiveStatus.line1 && (
                    <div style={{ marginTop: 3, fontSize: 10, lineHeight: 1.3, opacity: 0.84 }}>
                      {agentLoopLiveStatus.line1}
                    </div>
                  )}
                  {agentLoopLiveStatus.line2 && (
                    <div style={{ marginTop: 2, fontSize: 10, lineHeight: 1.25, opacity: 0.76 }}>
                      {agentLoopLiveStatus.line2}
                    </div>
                  )}
                  {agentLoopLiveStatus.reason_code && (
                    <div style={{ marginTop: 2, fontSize: 10, lineHeight: 1.25, opacity: 0.7 }}>
                      reason: {agentLoopLiveStatus.reason_code}
                    </div>
                  )}
                  {agentLoopLiveStatus.artifact_refs && Object.keys(agentLoopLiveStatus.artifact_refs).length > 0 && (
                    <div style={{ marginTop: 2, fontSize: 10, lineHeight: 1.25, opacity: 0.7, wordBreak: 'break-word' }}>
                      refs: {Object.entries(agentLoopLiveStatus.artifact_refs).slice(0, 3).map(([k, v]) => `${k}=${v}`).join(' | ')}
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {tapeEvents.length > 0 && (
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {tapeEvents.slice(0, 5).map((evt, idx) => {
                const status = evt.status || {};
                const key = `${evt.seq ?? 'na'}-${idx}`;
                const tsLabel = formatTapeTime(evt.timestamp_epoch_seconds);
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
                      {status.status_chip && (
                        <span
                          style={{
                            fontSize: 10,
                            padding: '2px 6px',
                            borderRadius: 999,
                            background: 'rgba(76, 195, 255, 0.10)',
                            border: '1px solid rgba(76, 195, 255, 0.2)',
                            color: 'rgba(196, 238, 255, 0.95)',
                            fontWeight: 700,
                          }}
                        >
                          {status.status_chip}
                        </span>
                      )}
                      {typeof status.iteration === 'number' && (
                        <span style={{ fontSize: 10, opacity: 0.75 }}>#{status.iteration}</span>
                      )}
                      {agentActivityDebug && status.stage && (
                        <span style={{ fontSize: 10, opacity: 0.8, textTransform: 'uppercase' }}>{status.stage}</span>
                      )}
                      {agentActivityDebug && status.phase && (
                        <span style={{ fontSize: 10, opacity: 0.78, textTransform: 'uppercase' }}>{status.phase}</span>
                      )}
                      {agentActivityDebug && status.action_type && (
                        <span style={{ fontSize: 10, opacity: 0.9 }}>{status.action_type}</span>
                      )}
                      {agentActivityDebug && typeof evt.seq === 'number' && (
                        <span style={{ fontSize: 10, opacity: 0.65 }}>seq {evt.seq}</span>
                      )}
                      {agentActivityDebug && tsLabel && (
                        <span style={{ fontSize: 10, opacity: 0.65 }}>{tsLabel}</span>
                      )}
                    </div>
                    <div style={{ fontSize: 11, lineHeight: 1.3, marginTop: 2 }}>
                      {standardAgentMessage(status)}
                    </div>
                    {!agentActivityDebug && standardAgentSecondary(status) && (
                      <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.76, marginTop: 2 }}>
                        {standardAgentSecondary(status)}
                      </div>
                    )}
                    {agentActivityDebug && (
                      <>
                        {status.display_delta && (
                          <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.82, marginTop: 2 }}>
                            Narration: {status.display_delta}
                          </div>
                        )}
                        {status.line1 && (
                          <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.82, marginTop: 2 }}>
                            {status.line1}
                          </div>
                        )}
                        {status.line2 && (
                          <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.76, marginTop: 2 }}>
                            {status.line2}
                          </div>
                        )}
                        {(evt.source_event_type || status.reason_code || status.outcome) && (
                          <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.66, marginTop: 2 }}>
                            {[evt.source_event_type, status.outcome, status.reason_code].filter(Boolean).join(' | ')}
                          </div>
                        )}
                        {status.artifact_refs && Object.keys(status.artifact_refs).length > 0 && (
                          <div style={{ fontSize: 10, lineHeight: 1.25, opacity: 0.66, marginTop: 2, wordBreak: 'break-word' }}>
                            {Object.entries(status.artifact_refs).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(' | ')}
                          </div>
                        )}
                      </>
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

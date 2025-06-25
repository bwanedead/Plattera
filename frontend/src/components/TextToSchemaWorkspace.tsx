import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './ParcelTracerLoader';

// Real API call for text-to-schema processing
const processTextAPI = async (texts: string[], model: string) => {
  console.log(`Processing ${texts.length} text(s) with model: ${model}`);
  
  const results = [];
  
  for (let i = 0; i < texts.length; i++) {
    const text = texts[i];
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

      if (data.status === 'success') {
        results.push({
          input: `Text ${i + 1}`,
          status: 'completed' as const,
          result: {
            structured_data: data.structured_data,
            metadata: {
              model_used: data.model_used,
              service_type: data.service_type,
              tokens_used: data.tokens_used,
              confidence_score: data.confidence_score,
              ...data.metadata
            }
          }
        });
      } else {
        results.push({
          input: `Text ${i + 1}`,
          status: 'error' as const,
          result: null,
          error: data.error || 'Processing failed'
        });
      }
    } catch (error) {
      results.push({
        input: `Text ${i + 1}`,
        status: 'error' as const,
        result: null,
        error: error instanceof Error ? error.message : 'Unknown error'
      });
    }
  }
  
  return results;
};

// Real API call for fetching models
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
    // Fallback to default models suitable for structured output
    return {
      "gpt-4o": { name: "GPT-4o", provider: "openai" },
      "gpt-4": { name: "GPT-4", provider: "openai" },
    };
  }
};

// Fetch previously processed image-to-text results
const fetchImageToTextResults = async () => {
  // This would fetch from a session store or API
  // For now, return empty array - implement based on your session management
  return [];
};

interface TextToSchemaWorkspaceProps {
  onExit: () => void;
}

export const TextToSchemaWorkspace: React.FC<TextToSchemaWorkspaceProps> = ({ onExit }) => {
  const [stagedTexts, setStagedTexts] = useState<string[]>([]);
  const [manualText, setManualText] = useState('');
  const [sessionResults, setSessionResults] = useState<any[]>([]);
  const [selectedResult, setSelectedResult] = useState<any | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isHistoryVisible, setIsHistoryVisible] = useState(true);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [selectedModel, setSelectedModel] = useState('gpt-4o');
  const [activeTab, setActiveTab] = useState('json');
  const [imageToTextResults, setImageToTextResults] = useState<any[]>([]);

  // File drop for text files
  const onDrop = useCallback((acceptedFiles: File[]) => {
    acceptedFiles.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        if (text) {
          setStagedTexts(prev => [...prev, text]);
        }
      };
      reader.readAsText(file);
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: onDrop,
    accept: {
      'text/*': ['.txt', '.md', '.doc', '.docx']
    },
    multiple: true
  });

  const handleAddManualText = () => {
    if (manualText.trim()) {
      setStagedTexts(prev => [...prev, manualText.trim()]);
      setManualText('');
    }
  };

  const handleProcess = async () => {
    if (stagedTexts.length === 0) return;
    setIsProcessing(true);
    setSelectedResult(null);
    
    const newResults = await processTextAPI(stagedTexts, selectedModel);
    
    setSessionResults(prev => [...newResults, ...prev]);
    
    const firstSuccessful = newResults.find(r => r.status === 'completed') || newResults[0];
    if (firstSuccessful) {
      setSelectedResult(firstSuccessful);
    }
    
    setStagedTexts([]);
    setIsProcessing(false);
  };
  
  const removeStagedText = (index: number) => {
    setStagedTexts(prev => prev.filter((_, i) => i !== index));
  };

  const importFromImageToText = (result: any) => {
    if (result.result?.extracted_text) {
      setStagedTexts(prev => [...prev, result.result.extracted_text]);
    }
  };

  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
    fetchImageToTextResults().then(setImageToTextResults);
  }, []);

  return (
    <div className="text-to-schema-workspace">
      <div className="workspace-nav">
        <button className="nav-home" onClick={onExit}>
          Home
        </button>
        <button className="nav-prev" onClick={() => {/* TODO: Navigate to image-to-text */}}>
          Image to Text
        </button>
      </div>

      <Allotment defaultSizes={[300, 700]}>
        <Allotment.Pane minSize={250} maxSize={400}>
          <div className="control-panel">
            <h2>Text to Schema</h2>
            
            {/* Import from Image-to-Text Section */}
            {imageToTextResults.length > 0 && (
              <div className="import-section">
                <label>Import from Image-to-Text</label>
                <div className="image-to-text-results">
                  {imageToTextResults.map((result, index) => (
                    <div key={index} className="result-item">
                      <span className="result-name">{result.input}</span>
                      <button 
                        className="import-btn"
                        onClick={() => importFromImageToText(result)}
                      >
                        Import
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Manual Text Input Section */}
            <div className="import-section">
              <label>Manual Text Input</label>
              <textarea
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder="Paste your legal text here..."
                rows={6}
                className="manual-text-input"
              />
              <button 
                onClick={handleAddManualText}
                disabled={!manualText.trim()}
                className="add-text-btn"
              >
                Add Text
              </button>
            </div>

            {/* File Import Section */}
            <div className="import-section">
              <label>Import Text Files</label>
              <div 
                {...getRootProps()} 
                className={`file-drop-zone ${isDragActive ? 'drag-active' : ''}`}
              >
                <input {...getInputProps()} />
                <div className="drop-zone-content">
                  <div className="drop-icon">📝</div>
                  <div className="drop-text">
                    <strong>Click to select files</strong> or drag and drop
                  </div>
                  <div className="drop-hint">TXT, MD, DOC, DOCX</div>
                </div>
              </div>
            </div>

            {/* Staged Texts */}
            {stagedTexts.length > 0 && (
              <div className="staged-texts">
                <label>Staged Texts ({stagedTexts.length})</label>
                {stagedTexts.map((text, index) => (
                  <div key={index} className="staged-text">
                    <div className="text-preview">
                      {text.substring(0, 100)}...
                    </div>
                    <button 
                      className="remove-text"
                      onClick={() => removeStagedText(index)}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Model Selection */}
            <div className="model-section">
              <label>Model Selection</label>
              <select 
                value={selectedModel} 
                onChange={(e) => setSelectedModel(e.target.value)}
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
              onClick={handleProcess}
              disabled={stagedTexts.length === 0 || isProcessing}
              className="process-btn"
            >
              {isProcessing ? (
                <ParcelTracerLoader size="small" />
              ) : (
                `Process ${stagedTexts.length} Text${stagedTexts.length !== 1 ? 's' : ''}`
              )}
            </button>

            {/* Results History */}
            <div className="results-history">
              <div className="history-header">
                <h3>Session Results</h3>
                <button
                  onClick={() => setIsHistoryVisible(!isHistoryVisible)}
                  className="toggle-history"
                >
                  {isHistoryVisible ? '▼' : '▶'}
                </button>
              </div>
              
              {isHistoryVisible && (
                <div className="history-list">
                  {sessionResults.map((result, index) => (
                    <div 
                      key={index}
                      className={`history-item ${selectedResult === result ? 'selected' : ''} ${result.status}`}
                      onClick={() => setSelectedResult(result)}
                    >
                      <div className="result-info">
                        <span className="result-name">{result.input}</span>
                        <span className={`status-badge ${result.status}`}>
                          {result.status}
                        </span>
                      </div>
                      {result.error && (
                        <div className="error-message">{result.error}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Allotment.Pane>

        <Allotment.Pane>
          <div className="results-panel">
            {selectedResult ? (
              <>
                <div className="result-header">
                  <h3>{selectedResult.input}</h3>
                  <div className="result-tabs">
                    <button 
                      className={`tab ${activeTab === 'json' ? 'active' : ''}`}
                      onClick={() => setActiveTab('json')}
                    >
                      JSON Schema
                    </button>
                    <button 
                      className={`tab ${activeTab === 'metadata' ? 'active' : ''}`}
                      onClick={() => setActiveTab('metadata')}
                    >
                      Metadata
                    </button>
                  </div>
                </div>

                <div className="result-content">
                  {activeTab === 'json' && (
                    <div className="json-viewer">
                      {selectedResult.status === 'completed' ? (
                        <pre className="json-output">
                          {JSON.stringify(selectedResult.result.structured_data, null, 2)}
                        </pre>
                      ) : (
                        <div className="error-display">
                          <h4>Processing Error</h4>
                          <p>{selectedResult.error}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'metadata' && selectedResult.result?.metadata && (
                    <div className="metadata-viewer">
                      <div className="metadata-grid">
                        {Object.entries(selectedResult.result.metadata).map(([key, value]) => (
                          <div key={key} className="metadata-item">
                            <span className="metadata-key">{key.replace(/_/g, ' ')}</span>
                            <span className="metadata-value">
                              {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="no-selection">
                <div className="placeholder-content">
                  <h3>Text to Schema Processing</h3>
                  <p>
                    Convert legal descriptions and documents into structured JSON data.
                  </p>
                  <ul>
                    <li>Paste text directly or import from files</li>
                    <li>Pull results from Image-to-Text processing</li>
                    <li>Advanced AI models extract structured data</li>
                    <li>JSON output ready for mapping applications</li>
                  </ul>
                  <p className="start-hint">
                    Add some text and click "Process" to get started.
                  </p>
                </div>
              </div>
            )}
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  );
}; 
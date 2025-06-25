import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './ParcelTracerLoader';

// Enhancement settings interface
interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

// --- Real API Calls (replacing the simulated ones) ---
const processFilesAPI = async (files: File[], model: string, mode: string, enhancementSettings: EnhancementSettings) => {
  console.log(`Processing ${files.length} files with model: ${model} and mode: ${mode}`);
  
  const results = [];
  
  for (const file of files) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('content_type', 'image-to-text');
      formData.append('extraction_mode', mode);
      formData.append('model', model);
      formData.append('cleanup_after', 'true');
      
      // Add enhancement settings
      formData.append('contrast', enhancementSettings.contrast.toString());
      formData.append('sharpness', enhancementSettings.sharpness.toString());
      formData.append('brightness', enhancementSettings.brightness.toString());
      formData.append('color', enhancementSettings.color.toString());

      const response = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.status === 'success') {
        results.push({
          input: file.name,
          status: 'completed' as const,
          result: {
            extracted_text: data.extracted_text,
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
          input: file.name,
          status: 'error' as const,
          result: null,
          error: data.error || 'Processing failed'
        });
      }
    } catch (error) {
      results.push({
        input: file.name,
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
    // Fallback to default models
    return {
      "gpt-4o": { name: "GPT-4o", provider: "openai" },
      "o3": { name: "o3", provider: "openai" },
      "gpt-4": { name: "GPT-4", provider: "openai" },
    };
  }
};

// Enhancement settings interface
interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

interface ProcessingResult {
  success: boolean;
  extracted_text: string;
  model_used: string;
  service_type: string;
  tokens_used?: number;
  confidence_score?: number;
  metadata?: any;
}

// Define the type for the component's props, including the onExit callback
interface ImageProcessingWorkspaceProps {
  onExit: () => void;
}

// --- Main Component ---
export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ onExit }) => {
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [sessionResults, setSessionResults] = useState<any[]>([]);
  const [selectedResult, setSelectedResult] = useState<any | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isHistoryVisible, setIsHistoryVisible] = useState(true);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [selectedModel, setSelectedModel] = useState('gpt-o4-mini');
  const [extractionMode, setExtractionMode] = useState('legal_document');
  const [activeTab, setActiveTab] = useState('text');
  const [enhancementSettings, setEnhancementSettings] = useState<EnhancementSettings>({
    contrast: 1.3,
    sharpness: 1.2,
    brightness: 1.0,
    color: 1.0
  });

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setStagedFiles(prev => [...prev, ...acceptedFiles]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']
    },
    multiple: true
  });

  const handleProcess = async () => {
    if (stagedFiles.length === 0) return;
    setIsProcessing(true);
    setSelectedResult(null); // Clear previous selection
    
    // Process all files and get results with enhancement settings
    const newResults = await processFilesAPI(stagedFiles, selectedModel, extractionMode, enhancementSettings);
    
    // Add all results to session
    setSessionResults(prev => [...newResults, ...prev]);
    
    // Select the first successful result, or the first result if none succeeded
    const firstSuccessful = newResults.find(r => r.status === 'completed') || newResults[0];
    if (firstSuccessful) {
      setSelectedResult(firstSuccessful);
    }
    
    setStagedFiles([]);
    setIsProcessing(false);
  };
  
  const removeStagedFile = (fileName: string) => {
    setStagedFiles(prev => prev.filter(f => f.name !== fileName));
  };

  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
  }, []);

  const handleEnhancementChange = useCallback((setting: keyof EnhancementSettings, value: number) => {
    setEnhancementSettings(prev => ({
      ...prev,
      [setting]: value
    }));
  }, []);

  return (
    <div className="image-processing-workspace">
      <div className="workspace-nav">
        <button className="nav-home" onClick={onExit}>
          Home
        </button>
        <button className="nav-next" onClick={() => {/* TODO: Add text-to-schema navigation */}}>
          Text to Schema
        </button>
      </div>

      <Allotment defaultSizes={[300, 700]}>
        <Allotment.Pane minSize={250} maxSize={400}>
          <div className="control-panel">
            <div className="panel-header">
              <h2>Image to Text</h2>
            </div>
            
            <div className="import-section">
              <label>Import Files</label>
              <div 
                {...getRootProps()} 
                className={`file-drop-zone ${isDragActive ? 'drag-active' : ''} ${stagedFiles.length > 0 ? 'has-files' : ''}`}
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
                      <div className="files-count">{stagedFiles.length} file{stagedFiles.length > 1 ? 's' : ''} ready</div>
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
                        onClick={() => removeStagedFile(file.name)}
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
                onChange={(e) => setSelectedModel(e.target.value)}
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
                onChange={(e) => setExtractionMode(e.target.value)}
                className="extraction-selector"
              >
                <option value="legal_document">Legal Document</option>
                <option value="simple_ocr">Simple OCR</option>
                <option value="handwritten">Handwritten</option>
                <option value="property_deed">Property Deed</option>
                <option value="court_document">Court Document</option>
                <option value="contract">Contract</option>
              </select>
            </div>

            <div className="enhancement-section">
              <label>🎨 Image Enhancement</label>
              <div className="enhancement-controls">
                <div className="enhancement-sliders">
                  <div className="slider-group">
                    <label htmlFor="contrast-slider">
                      Contrast: {enhancementSettings.contrast.toFixed(1)}
                    </label>
                    <input
                      id="contrast-slider"
                      type="range"
                      min="0.5"
                      max="2.0"
                      step="0.1"
                      value={enhancementSettings.contrast}
                      onChange={(e) => handleEnhancementChange('contrast', parseFloat(e.target.value))}
                      disabled={isProcessing}
                    />
                  </div>

                  <div className="slider-group">
                    <label htmlFor="sharpness-slider">
                      Sharpness: {enhancementSettings.sharpness.toFixed(1)}
                    </label>
                    <input
                      id="sharpness-slider"
                      type="range"
                      min="0.5"
                      max="2.0"
                      step="0.1"
                      value={enhancementSettings.sharpness}
                      onChange={(e) => handleEnhancementChange('sharpness', parseFloat(e.target.value))}
                      disabled={isProcessing}
                    />
                  </div>

                  <div className="slider-group">
                    <label htmlFor="brightness-slider">
                      Brightness: {enhancementSettings.brightness.toFixed(1)}
                    </label>
                    <input
                      id="brightness-slider"
                      type="range"
                      min="0.5"
                      max="1.5"
                      step="0.1"
                      value={enhancementSettings.brightness}
                      onChange={(e) => handleEnhancementChange('brightness', parseFloat(e.target.value))}
                      disabled={isProcessing}
                    />
                  </div>

                  <div className="slider-group">
                    <label htmlFor="color-slider">
                      Color: {enhancementSettings.color.toFixed(1)}
                    </label>
                    <input
                      id="color-slider"
                      type="range"
                      min="0.0"
                      max="2.0"
                      step="0.1"
                      value={enhancementSettings.color}
                      onChange={(e) => handleEnhancementChange('color', parseFloat(e.target.value))}
                      disabled={isProcessing}
                    />
                  </div>
                </div>

                <div className="enhancement-presets">
                  <button 
                    onClick={() => setEnhancementSettings({ contrast: 1.3, sharpness: 1.2, brightness: 1.0, color: 1.0 })}
                    disabled={isProcessing}
                    className="preset-btn"
                  >
                    Restore Default
                  </button>
                </div>
              </div>
            </div>

            <div className="process-section">
              <button 
                className={`process-button ${isProcessing ? 'processing' : ''}`}
                onClick={handleProcess}
                disabled={stagedFiles.length === 0 || isProcessing}
              >
                {isProcessing ? 'Processing...' : `Process ${stagedFiles.length} File${stagedFiles.length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </Allotment.Pane>
        <Allotment.Pane>
          <div className="results-area">
            <Allotment defaultSizes={[300, 700]} vertical={false}>
              {isHistoryVisible && (
                <Allotment.Pane minSize={200} maxSize={500}>
                  <div className="results-history-panel visible">
                    <div className="history-header">
                      <h4>Session Log</h4>
                      <button onClick={() => setIsHistoryVisible(false)}>‹</button>
                    </div>
                    <div className="history-list-items">
                      {sessionResults.map((res, i) => (
                        <div key={i} className={`log-item ${selectedResult === res ? 'selected' : ''} ${res.status}`} onClick={() => setSelectedResult(res)}>
                          <span className={`log-item-status-dot ${res.status}`}></span>
                          {res.input}
                        </div>
                      ))}
                    </div>
                  </div>
                </Allotment.Pane>
              )}
              <Allotment.Pane>
                <div className="results-viewer-panel">
                  {!isHistoryVisible && <button className="history-toggle-button" onClick={() => setIsHistoryVisible(true)}>›</button>}
                  {isProcessing && (
                    <div className="loading-view">
                      <ParcelTracerLoader />
                      <h4>Tracing Parcels...</h4>
                      <p>Analyzing document geometry.</p>
                    </div>
                  )}
                  {!isProcessing && !selectedResult && (
                     <div className="placeholder-view">
                        <p>Your results will appear here.</p>
                    </div>
                  )}
                  {!isProcessing && selectedResult && (
                    <div className="result-display-area">
                        <div className="result-tabs">
                            <button className={activeTab === 'text' ? 'active' : ''} onClick={() => setActiveTab('text')}>Extracted Text</button>
                            <button className={activeTab === 'metadata' ? 'active' : ''} onClick={() => setActiveTab('metadata')}>Metadata</button>
                        </div>
                        <div className="result-tab-content">
                            {activeTab === 'text' && (
                              <pre>{selectedResult.status === 'completed' ? selectedResult.result.extracted_text : `Error: ${selectedResult.error}`}</pre>
                            )}
                            {activeTab === 'metadata' && (
                              <pre>{selectedResult.status === 'completed' ? JSON.stringify(selectedResult.result.metadata, null, 2) : 'No metadata available for failed processing.'}</pre>
                            )}
                        </div>
                    </div>
                  )}
                </div>
              </Allotment.Pane>
            </Allotment>
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  );
}; 
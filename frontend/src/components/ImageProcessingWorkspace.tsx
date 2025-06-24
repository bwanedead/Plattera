import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './ParcelTracerLoader';

// This is a placeholder for the actual API call logic
// We'll integrate the real API calls next.
const processFilesAPI = async (files: File[], model: string, mode: string) => {
  console.log(`Simulating API call for ${files.length} files with model: ${model} and mode: ${mode}`);
  await new Promise(resolve => setTimeout(resolve, 2500));
  // In a real app, you would map over files and return individual results
  return {
    input: files.map(f => f.name).join(', '),
    status: 'completed' as const,
    result: {
      extracted_text: `--- SIMULATED OUTPUT ---\nModel: ${model}\nMode: ${mode}\n\nThis is the simulated extracted text for the processed files. In a real scenario, the full text from the document would appear here.`,
      metadata: {
        file_count: files.length,
        model_used: model,
        extraction_mode: mode,
        processing_time_ms: 2451,
        total_tokens: 1842,
        confidence: 0.98
      }
    }
  };
};

// Placeholder for fetching models
const fetchModelsAPI = async () => {
    await new Promise(resolve => setTimeout(resolve, 500));
    return {
        "gpt-4o": { name: "GPT-4o", provider: "openai" },
        "o3": { name: "o3", provider: "openai" },
        "claude-3-opus": { name: "Claude 3 Opus", provider: "anthropic" },
    };
};

// Define the type for the component's props, including the onExit callback
interface ImageProcessingWorkspaceProps {
  onExit: () => void;
}

export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ onExit }) => {
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [sessionResults, setSessionResults] = useState<any[]>([]);
  const [selectedResult, setSelectedResult] = useState<any | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isHistoryVisible, setIsHistoryVisible] = useState(true);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [selectedModel, setSelectedModel] = useState('gpt-4o');
  const [extractionMode, setExtractionMode] = useState('legal_document');
  const [activeTab, setActiveTab] = useState('text');

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setStagedFiles(prev => [...prev, ...acceptedFiles]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, noClick: true });

  const handleProcess = async () => {
    if (stagedFiles.length === 0) return;
    setIsProcessing(true);
    setSelectedResult(null); // Clear previous selection
    const newResult = await processFilesAPI(stagedFiles, selectedModel, extractionMode);
    setSessionResults(prev => [newResult, ...prev]);
    setSelectedResult(newResult);
    setStagedFiles([]);
    setIsProcessing(false);
  };
  
  const removeStagedFile = (fileName: string) => {
    setStagedFiles(prev => prev.filter(f => f.name !== fileName));
  };

  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
  }, []);

  return (
    <Allotment defaultSizes={[400, 1000]}>
      <Allotment.Pane minSize={380} maxSize={550}>
        {/* --- Left Control Panel --- */}
        <div className="control-panel">
          <div className="panel-header">
            <button onClick={onExit} className="back-button">←</button>
            <h2>Image to Text Workspace</h2>
          </div>
          
          <div className="control-group">
            <h4>1. Select Model</h4>
            <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)}>
              {Object.entries(availableModels).map(([id, model]) => (
                  <option key={id} value={id}>{model.name}</option>
              ))}
            </select>
          </div>

          <div className="control-group">
            <h4>2. Set Extraction Mode</h4>
            <select value={extractionMode} onChange={e => setExtractionMode(e.target.value)}>
              <option value="legal_document">Legal Document</option>
              <option value="simple_ocr">Simple OCR</option>
              <option value="handwritten">Handwritten</option>
            </select>
          </div>
          
          <div className="control-group dropzone-group" {...getRootProps()}>
              <h4>3. Add Files</h4>
              <div className={`dropzone-interactive-area ${isDragActive ? 'active' : ''}`}>
                  <input {...getInputProps()} />
                  {stagedFiles.length === 0 ? (
                      <div className="dropzone-prompt">
                          <p>Drag & Drop Files Here</p>
                          <span>or <button onClick={(e) => { e.stopPropagation(); document.querySelector('input[type="file"]')?.click(); }}>browse</button></span>
                      </div>
                  ) : (
                      <div className="staged-files-list-integrated">
                          {stagedFiles.map(file => (
                              <div key={file.name} className="staged-file-chip">
                                  <span>{file.name}</span>
                                  <button onClick={(e) => { e.stopPropagation(); removeStagedFile(file.name); }}>×</button>
                              </div>
                          ))}
                      </div>
                  )}
              </div>
          </div>

          <button onClick={handleProcess} className="process-button" disabled={stagedFiles.length === 0 || isProcessing}>
            {isProcessing ? 'PROCESSING...' : 'RUN PIPELINE'}
          </button>
        </div>
      </Allotment.Pane>
      <Allotment.Pane>
        {/* --- Right Results Area --- */}
        <div className="results-area">
          <div className={`results-history-panel ${isHistoryVisible ? 'visible' : ''}`}>
              <div className="history-header">
                  <h4>Session Log</h4>
                  <button onClick={() => setIsHistoryVisible(false)}>‹</button>
              </div>
              <div className="history-list-items">
                  {sessionResults.map((res, i) => (
                      <div key={i} className={`log-item ${selectedResult === res ? 'selected' : ''}`} onClick={() => setSelectedResult(res)}>
                          <span className="log-item-status-dot"></span>
                          {res.input}
                      </div>
                  ))}
              </div>
          </div>
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
                      {activeTab === 'text' && <pre>{selectedResult.result.extracted_text}</pre>}
                      {activeTab === 'metadata' && <pre>{JSON.stringify(selectedResult.result.metadata, null, 2)}</pre>}
                  </div>
              </div>
            )}
          </div>
        </div>
      </Allotment.Pane>
    </Allotment>
  );
}; 
import React, { useState, useEffect } from 'react'

interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

interface ProcessingResult {
  id: string
  input: string
  result: any
  status: 'processing' | 'completed' | 'error'
  error?: string
}

interface ImageBatchProcessorProps {
  onResults: (results: ProcessingResult[]) => void
  enhancementSettings?: EnhancementSettings
}

interface ModelInfo {
  name: string
  description: string
  capabilities?: string[]
  cost_tier: string
  verification_required: boolean
}

const ImageBatchProcessor: React.FC<ImageBatchProcessorProps> = ({ 
  onResults, 
  enhancementSettings = { contrast: 1.3, sharpness: 1.2, brightness: 1.0, color: 1.0 } 
}) => {
  const [processing, setProcessing] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [selectedModel, setSelectedModel] = useState('gpt-4o')
  const [extractionMode, setExtractionMode] = useState('legal_document_plain')
  const [availableModels, setAvailableModels] = useState<Record<string, ModelInfo>>({})
  const [availableExtractionModes, setAvailableExtractionModes] = useState<Record<string, {name: string, description: string}>>({})
  const [loadingModels, setLoadingModels] = useState(true)
  const [loadingModes, setLoadingModes] = useState(true)
  const [apiError, setApiError] = useState<string | null>(null)

  // Default models in case API is not available
  const defaultModels: Record<string, ModelInfo> = {
    "gpt-4o": {
      name: "GPT-4o",
      description: "Fast, cost-effective vision model optimized for document OCR",
      cost_tier: "standard",
      verification_required: false
    },
    "o3": {
      name: "o3",
      description: "Most advanced reasoning model with highest accuracy",
      cost_tier: "premium",
      verification_required: true
    }
  }

  // Load available models and extraction modes on component mount
  useEffect(() => {
    const loadModels = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/models')
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        
        const data = await response.json()
        
        if (data.status === 'success' && data.models) {
          setAvailableModels(data.models)
          setApiError(null)
        } else {
          throw new Error(data.error || 'Invalid response format')
        }
      } catch (error) {
        console.warn('Failed to load models from API, using defaults:', error)
        setAvailableModels(defaultModels)
        setApiError(error instanceof Error ? error.message : 'Unknown error')
      } finally {
        setLoadingModels(false)
      }
    }
    
    const loadExtractionModes = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/process/types')
        const data = await response.json()
        
        if (data.status === 'success' && data.processing_types?.['image-to-text']?.extraction_modes) {
          console.log('Extraction modes API response:', data.processing_types['image-to-text'].extraction_modes)
          setAvailableExtractionModes(data.processing_types['image-to-text'].extraction_modes)
        } else {
          console.log('API response:', data)
          throw new Error(data.error || 'Invalid response format')
        }
      } catch (error) {
        console.warn('Failed to load extraction modes from API, using defaults:', error)
        // Fallback to default modes
        setAvailableExtractionModes({
          'legal_document_plain': { name: 'Legal Document Plain', description: 'Plain legal document transcription' },
          'legal_document_sectioned': { name: 'Legal Document Sectioned', description: 'With section markers' },
          'ultra_precise_legal': { name: 'Ultra Precise Legal', description: 'Maximum accuracy' },
          'legal_document_json': { name: 'Legal Document JSON', description: 'Structured JSON format' }
        })
      } finally {
        setLoadingModes(false)
      }
    }
    
    loadModels()
    loadExtractionModes()
  }, [])

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    setSelectedFiles(prev => [...prev, ...files])
  }

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const processImages = async () => {
    if (selectedFiles.length === 0) return

    setProcessing(true)
    const results: ProcessingResult[] = []

    for (const file of selectedFiles) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('content_type', 'image-to-text')
        formData.append('extraction_mode', extractionMode)
        formData.append('model', selectedModel)
        formData.append('cleanup_after', 'true')
        
        // Add enhancement settings
        formData.append('contrast', enhancementSettings.contrast.toString())
        formData.append('sharpness', enhancementSettings.sharpness.toString())
        formData.append('brightness', enhancementSettings.brightness.toString())
        formData.append('color', enhancementSettings.color.toString())

        const response = await fetch('http://localhost:8000/api/process', {
          method: 'POST',
          body: formData
        })

        const data = await response.json()

        if (data.status === 'success') {
          results.push({
            id: `img_${Date.now()}_${Math.random()}`,
            input: file.name,
            result: {
              extracted_text: data.extracted_text,
              file_info: data.file_info,
              processing_info: data.processing_info,
              pipeline_stats: data.pipeline_stats
            },
            status: 'completed'
          })
        } else {
          results.push({
            id: `img_${Date.now()}_${Math.random()}`,
            input: file.name,
            result: null,
            status: 'error',
            error: data.error || 'Processing failed'
          })
        }
      } catch (error) {
        results.push({
          id: `img_${Date.now()}_${Math.random()}`,
          input: file.name,
          result: null,
          status: 'error',
          error: error instanceof Error ? error.message : 'Unknown error'
        })
      }
    }

    onResults(results)
    setProcessing(false)
    setSelectedFiles([]) // Clear files after processing
  }

  return (
    <div className="image-batch-processor">
      <div className="processor-header">
        <h2>Image Processor</h2>
        <p>Upload handwritten or scanned legal descriptions</p>
        {apiError && (
          <div className="api-warning">
            ⚠️ Using default models (API: {apiError})
          </div>
        )}
      </div>

      {/* Model and Mode Selection */}
      <div className="processing-options">
        <div className="option-group">
          <label htmlFor="model-select">AI Model:</label>
          <select 
            id="model-select"
            value={selectedModel} 
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={processing || loadingModels}
            className="model-select"
          >
            {loadingModels ? (
              <option>Loading models...</option>
            ) : (
              Object.entries(availableModels).map(([modelId, modelInfo]) => (
                <option key={modelId} value={modelId}>
                  {modelInfo.name} - {modelInfo.description}
                  {modelInfo.verification_required ? ' (Verification Required)' : ''}
                </option>
              ))
            )}
          </select>
          {availableModels[selectedModel] && (
            <div className="model-info">
              <span className={`cost-tier ${availableModels[selectedModel].cost_tier}`}>
                {availableModels[selectedModel].cost_tier} cost
              </span>
              {availableModels[selectedModel].verification_required && (
                <span className="verification-required">⚠️ Requires verification</span>
              )}
            </div>
          )}
        </div>

        <div className="option-group">
          <label htmlFor="extraction-mode">Extraction Mode:</label>
          <select 
            id="extraction-mode"
            value={extractionMode} 
            onChange={(e) => setExtractionMode(e.target.value)}
            disabled={processing || loadingModes}
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
      </div>

      <div className="batch-controls">
        <input
          type="file"
          accept="image/*,.pdf"
          multiple
          onChange={handleFileSelect}
          disabled={processing}
          style={{ display: 'none' }}
          id="file-input"
        />
        <label htmlFor="file-input" className={`file-select-button ${processing ? 'disabled' : ''}`}>
          📁 Select Images/PDFs
        </label>
        <button 
          onClick={processImages}
          disabled={selectedFiles.length === 0 || processing}
          className="process-button"
        >
          {processing ? 'Processing...' : `Process ${selectedFiles.length} File${selectedFiles.length !== 1 ? 's' : ''}`}
        </button>
      </div>

      <div className="file-list">
        {selectedFiles.map((file, index) => (
          <div key={index} className="file-item">
            <div className="file-info">
              <span className="file-name">{file.name}</span>
              <span className="file-size">({(file.size / 1024 / 1024).toFixed(1)}MB)</span>
            </div>
            <button 
              onClick={() => removeFile(index)}
              className="remove-button"
              disabled={processing}
            >
              ✕
            </button>
          </div>
        ))}

        {selectedFiles.length === 0 && (
          <div className="empty-state">
            <p>No files selected. Click "Select Images/PDFs" to get started.</p>
            <p className="format-note">Supported formats: JPEG, PNG, WEBP, GIF, BMP, TIFF, PDF (up to 20MB each)</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default ImageBatchProcessor 
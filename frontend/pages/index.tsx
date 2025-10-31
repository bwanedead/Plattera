import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { ApiKeyModal } from '../src/components/ApiKeyModal'
import TextBatchProcessor from '../src/components/TextBatchProcessor'
import ImageBatchProcessor from '../src/components/ImageBatchProcessor'
import ResultsViewer from '../src/components/ResultsViewer'
import { ImageProcessingWorkspace } from '../src/components/image-processing/ImageProcessingWorkspace';
import { TextToSchemaWorkspace } from '../src/components/TextToSchemaWorkspace'
import { useWorkspaceNavigation } from '../src/hooks/useWorkspaceState'

type ProcessingMode = 'text' | 'image' | null

interface ProcessingResult {
  id: string
  name: string
  input: string
  result: any
  status: 'processing' | 'completed' | 'error'
  error?: string
}

type AppMode = 'home' | 'image-processing' | 'text-processing'

const App: React.FC = () => {
  const [mode, setMode] = useState<AppMode>('home')
  const [results, setResults] = useState<ProcessingResult[]>([])
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null)
  const [showKeyModal, setShowKeyModal] = useState(false)
  
  // Navigation state management
  const { lastActiveWorkspace, setActiveWorkspace } = useWorkspaceNavigation()

  const handleResults = (newResults: Omit<ProcessingResult, 'id' | 'name'>[]) => {
    const formattedResults = newResults.map(r => ({
      ...r,
      id: `res_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name: r.input,
    }))
    setResults(prev => [...prev, ...formattedResults])
    if (formattedResults.length > 0) {
      setSelectedResultId(formattedResults[0].id)
    }
    setMode('home')
  }
  
  const selectedResult = results.find(r => r.id === selectedResultId)

  // Restore last active workspace on mount
  useEffect(() => {
    if (lastActiveWorkspace) {
      setMode(lastActiveWorkspace === 'image-processing' ? 'image-processing' : 'text-processing')
    }
  }, [lastActiveWorkspace])

  const handleNavigateToImageProcessing = () => {
    setMode('image-processing')
    setActiveWorkspace('image-processing')
  }

  const handleNavigateToTextProcessing = () => {
    setMode('text-processing')
    setActiveWorkspace('text-processing')
  }

  const handleExitToHome = () => {
    setMode('home')
    setActiveWorkspace(null)
  }

  const renderContent = () => {
    switch (mode) {
      case 'image-processing':
        return <ImageProcessingWorkspace 
          onExit={handleExitToHome} 
          onNavigateToTextSchema={handleNavigateToTextProcessing}
        />
      case 'text-processing':
        return <TextToSchemaWorkspace 
          onExit={handleExitToHome} 
          onNavigateToImageText={handleNavigateToImageProcessing}
        />
      case 'home':
      default:
        return (
          <div className="home-view">
            <div className="home-header">
              <h1>Plattera<span>.</span></h1>
              <p>Professional Legal Description Processing Suite</p>
            </div>
            <div className="home-options">
              {/* Image to Text Card (Left) */}
              <div className="pipeline-card" onClick={handleNavigateToImageProcessing}>
                <h3>Image to Text</h3>
                <p>Extract text from scanned documents using advanced AI vision models.</p>
                <button>Launch Workspace</button>
              </div>

              {/* Text to Schema Card (Right) */}
              <div className="pipeline-card" onClick={handleNavigateToTextProcessing}>
                <h3>Text to Schema</h3>
                <p>Convert blocks of legal text into structured JSON for analysis.</p>
                <button>Launch Workspace</button>
              </div>

              {/* Mapping Card (New) */}
              <Link href="/mapping" passHref legacyBehavior>
                <a className="pipeline-card" style={{ textDecoration: 'none', color: 'inherit' }}>
                  <h3>Mapping</h3>
                  <p>View saved plots, load schemas, and georeference parcels.</p>
                  <button>Open Mapping</button>
                </a>
              </Link>
            </div>
            <div style={{ marginTop: '4rem', textAlign: 'center' }}>
              <button
                onClick={() => setShowKeyModal(true)}
                style={{
                  display: 'inline-block',
                  padding: '12px 24px',
                  backgroundColor: 'var(--accent-primary)',
                  color: 'white',
                  border: '1px solid var(--accent-primary)',
                  borderRadius: '4px',
                  textDecoration: 'none',
                  fontWeight: 600,
                  transition: 'all 0.2s ease'
                }}
              >
                Set / Update API Key
              </button>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="app-workspace">
      {renderContent()}
      <ApiKeyModal open={showKeyModal} onClose={() => setShowKeyModal(false)} onSaved={() => location.reload()} />
    </div>
  )
}

export default App 
import React, { useState, useEffect } from 'react'
import Link from 'next/link'
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
            </div>
            <div style={{ marginTop: '4rem', textAlign: 'center' }}>
              <Link href="/animation-tester" passHref legacyBehavior>
                <a style={{
                  display: 'inline-block',
                  padding: '8px 16px',
                  color: 'var(--text-secondary)',
                  textDecoration: 'none',
                  fontSize: '0.8rem',
                  transition: 'color 0.2s ease'
                }}
                onMouseOver={e => e.currentTarget.style.color = 'var(--accent-primary)'}
                onMouseOut={e => e.currentTarget.style.color = 'var(--text-secondary)'}
                >
                  Animation Tester
                </a>
              </Link>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="app-workspace">
      {renderContent()}
    </div>
  )
}

export default App 
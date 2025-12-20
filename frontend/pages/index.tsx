import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { invoke } from '@tauri-apps/api/core'
import { ApiKeyModal } from '../src/components/ApiKeyModal'
import TextBatchProcessor from '../src/components/TextBatchProcessor'
import ImageBatchProcessor from '../src/components/ImageBatchProcessor'
import { ImageProcessingWorkspace } from '../src/components/image-processing/ImageProcessingWorkspace';
import { TextToSchemaWorkspace } from '../src/components/TextToSchemaWorkspace'
import { useWorkspaceNavigation } from '../src/hooks/useWorkspaceState'
import { AppVersionBadge } from '../src/components/AppVersionBadge'

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
  const [updaterDialog, setUpdaterDialog] = useState<{
    open: boolean
    title: string
    message: string
    mode?: 'info' | 'update-available' | 'debug'
  }>({ open: false, title: '', message: '', mode: 'info' })
  // Track a pending update object and whether the user has an update available
  // so we can offer explicit "Update now / Later" control instead of
  // auto-downloading on check.
  const [pendingUpdate, setPendingUpdate] = useState<any | null>(null)
  const [hasUpdateAvailable, setHasUpdateAvailable] = useState(false)
  const [isCheckingUpdate, setIsCheckingUpdate] = useState(false)
  const [isDownloadingUpdate, setIsDownloadingUpdate] = useState(false)
  const [updateProgress, setUpdateProgress] = useState<{
    percent: number | null
    downloaded: number
    total: number | null
  } | null>(null)
  
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
    setActiveWorkspace('text-to-schema')
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
              <button
                onClick={async () => {
                  if (isCheckingUpdate || isDownloadingUpdate) return
                  try {
                    setIsCheckingUpdate(true)
                    const { check } = await import('@tauri-apps/plugin-updater')
                    const update = await check()
                    if (update?.available) {
                      // Remember that an update is available and show a confirmation dialog
                      setPendingUpdate(update)
                      setHasUpdateAvailable(true)

                      const version = update.version || 'unknown'
                      const body = (update.body as string | undefined) || ''
                      const messageLines = [
                        `A new version is available.`,
                        ``,
                        `Latest version: ${version}`,
                        body ? `\nRelease notes:\n${body}` : ''
                      ].join('\n')

                      setUpdaterDialog({
                        open: true,
                        title: 'Update available',
                        message: messageLines,
                        mode: 'update-available'
                      })
                    } else {
                      setPendingUpdate(null)
                      setHasUpdateAvailable(false)
                      setUpdaterDialog({
                        open: true,
                        title: 'No updates available',
                        message: 'You are up to date.',
                        mode: 'info'
                      })
                    }
                  } catch (e: any) {
                    // Surface the underlying updater error so we can diagnose configuration issues.
                    // NOTE: In plain browser dev (npm run dev), this will always fail because Tauri APIs are unavailable.
                    // We care primarily about Tauri dev and installed builds here.
                    // eslint-disable-next-line no-console
                    console.error('Updater error', e)
                    const message =
                      (e && (e.message || (typeof e.toString === 'function' && e.toString()))) ||
                      'Unknown updater error (see devtools console for details)'
                    setUpdaterDialog({
                      open: true,
                      title: 'Updater check failed',
                      message: `Updater check failed:\n${message}`,
                      mode: 'info'
                    })
                  } finally {
                    setIsCheckingUpdate(false)
                  }
                }}
                style={{
                  display: 'inline-block',
                  marginLeft: 12,
                  padding: '12px 24px',
                  backgroundColor: 'transparent',
                  color: 'var(--accent-primary)',
                  border: '1px solid var(--accent-primary)',
                  borderRadius: '4px',
                  textDecoration: 'none',
                  fontWeight: 600,
                  transition: 'all 0.2s ease'
                }}
                disabled={isCheckingUpdate || isDownloadingUpdate}
              >
                {hasUpdateAvailable
                  ? 'Check for Updates (update available)'
                  : isCheckingUpdate
                  ? 'Checking for Updates…'
                  : 'Check for Updates'}
              </button>
              <button
                onClick={async () => {
                  try {
                    // Call Tauri-side debug helper so we can see the raw updater
                    // manifest body and headers in the log file for EXE builds.
                    const result = await invoke<string>('debug_updater_endpoint', {
                      url: 'https://raw.githubusercontent.com/bwanedead/Plattera/main/releases/latest.json'
                    })
                    setUpdaterDialog({
                      open: true,
                      title: 'Updater debug result',
                       message: result,
                       mode: 'debug'
                    })
                  } catch (e: any) {
                    // eslint-disable-next-line no-console
                    console.error('Updater debug error', e)
                    const message =
                      (e && (e.message || (typeof e.toString === 'function' && e.toString()))) ||
                      'Unknown updater debug error (see devtools console for details)'
                    setUpdaterDialog({
                      open: true,
                      title: 'Updater debug failed',
                      message: message,
                      mode: 'debug'
                    })
                  }
                }}
                style={{
                  display: 'inline-block',
                  marginLeft: 12,
                  padding: '12px 24px',
                  backgroundColor: 'transparent',
                  color: 'var(--accent-primary)',
                  border: '1px dashed var(--accent-primary)',
                  borderRadius: '4px',
                  textDecoration: 'none',
                  fontWeight: 600,
                  transition: 'all 0.2s ease'
                }}
              >
                Debug updater endpoint
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
      {updaterDialog.open && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1100
          }}
        >
          <div
            style={{
              background: '#1e1e1e',
              color: '#fff',
              padding: 24,
              borderRadius: 8,
              width: 520,
              maxHeight: '70vh',
              boxShadow: '0 10px 20px rgba(0,0,0,0.4)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12
            }}
          >
            <h3 style={{ margin: 0 }}>{updaterDialog.title}</h3>
            <textarea
              readOnly
              value={updaterDialog.message}
              style={{
                width: '100%',
                flex: 1,
                minHeight: 140,
                resize: 'vertical',
                padding: 10,
                borderRadius: 4,
                border: '1px solid #333',
                background: '#111',
                color: '#fff',
                fontFamily: 'monospace',
                fontSize: 13,
                whiteSpace: 'pre-wrap'
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              {updaterDialog.mode === 'debug' && (
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(updaterDialog.message).catch(() => {})
                  }}
                  style={{ padding: '8px 14px' }}
                >
                  Copy text
                </button>
              )}

              {updaterDialog.mode === 'update-available' && pendingUpdate && (
                <>
                  <button
                    onClick={async () => {
                      try {
                        if (isDownloadingUpdate) return
                        setIsDownloadingUpdate(true)
                        setUpdateProgress(null)
                        // Kick off download/install and surface updater progress
                        // events into a simple percent display so users can see
                        // that the update is actively downloading.
                        await pendingUpdate.downloadAndInstall((event: any) => {
                          try {
                            const kind = event?.event
                            if (kind === 'Started') {
                              const rawTotal = Number(event?.data?.contentLength ?? 0)
                              const total = Number.isFinite(rawTotal) && rawTotal > 0 ? rawTotal : null
                              setUpdateProgress({ percent: total ? 0 : null, downloaded: 0, total })
                            } else if (kind === 'Progress') {
                              const rawChunk = Number(event?.data?.chunkLength ?? 0)
                              const chunk = Number.isFinite(rawChunk) && rawChunk > 0 ? rawChunk : 0
                              setUpdateProgress(prev => {
                                const prevDownloaded = prev?.downloaded ?? 0
                                const downloaded = prevDownloaded + chunk
                                let total = prev?.total ?? null

                                // If we didn't have a valid total yet, try to pick it up
                                // from this progress event (some implementations repeat
                                // contentLength on Progress).
                                if (!total) {
                                  const rawTotal = Number(event?.data?.contentLength ?? 0)
                                  if (Number.isFinite(rawTotal) && rawTotal > 0) {
                                    total = rawTotal
                                  }
                                }

                                let percent: number | null = null
                                if (total && total > 0) {
                                  percent = Math.min(100, Math.round((downloaded / total) * 100))
                                }

                                return { downloaded, total, percent }
                              })
                            } else if (kind === 'Finished') {
                              setUpdateProgress(prev => {
                                if (!prev) return { downloaded: 0, total: null, percent: 100 }
                                return { ...prev, percent: 100 }
                              })
                            }
                          } catch {
                            // Swallow progress parsing issues; they are non-fatal.
                          }
                        })
                        setUpdaterDialog({
                          open: true,
                          title: 'Update downloaded',
                          message: 'Update downloaded. Please restart the app to finish installing.',
                          mode: 'info'
                        })
                        setPendingUpdate(null)
                        setHasUpdateAvailable(false)
                      } catch (e: any) {
                        // eslint-disable-next-line no-console
                        console.error('Download/install failed', e)
                        const msg =
                          (e && (e.message || (typeof e.toString === 'function' && e.toString()))) ||
                          'Unknown updater install error'
                        setUpdaterDialog({
                          open: true,
                          title: 'Update failed',
                          message: msg,
                          mode: 'info'
                        })
                      } finally {
                        setIsDownloadingUpdate(false)
                        setUpdateProgress(null)
                      }
                    }}
                    disabled={isDownloadingUpdate}
                    style={{
                      padding: '8px 14px',
                      background: isDownloadingUpdate ? '#1f2937' : '#3b82f6',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 4,
                      opacity: isDownloadingUpdate ? 0.8 : 1,
                      cursor: isDownloadingUpdate ? 'default' : 'pointer'
                    }}
                  >
                    {isDownloadingUpdate
                      ? updateProgress && typeof updateProgress.percent === 'number'
                        ? `Downloading… (${updateProgress.percent}%)`
                        : 'Downloading…'
                      : 'Update now'}
                  </button>
                  <button
                    onClick={() => {
                      // Leave hasUpdateAvailable = true so the main button keeps its badge.
                      setUpdaterDialog({ open: false, title: '', message: '', mode: 'info' })
                    }}
                    disabled={isDownloadingUpdate}
                    style={{
                      padding: '8px 14px',
                      opacity: isDownloadingUpdate ? 0.6 : 1,
                      cursor: isDownloadingUpdate ? 'default' : 'pointer'
                    }}
                  >
                    Later
                  </button>
                </>
              )}

              {updaterDialog.mode !== 'update-available' && (
                <button
                  onClick={() => setUpdaterDialog({ open: false, title: '', message: '', mode: 'info' })}
                  style={{ padding: '8px 14px' }}
                >
                  Close
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      <AppVersionBadge />
    </div>
  )
}

export default App 
import type { AppProps } from 'next/app'
import { useEffect, useState } from 'react'
import { startDossierPreload } from '@/services/dossier/dossierPreload'
// import '../styles/globals.css'        // OLD (backup)
import '../styles/main.css'             // NEW (modular) - testing now!
import 'allotment/dist/style.css';      // Global split-pane styling (Allotment)
import '../src/components/mapping/CleanMap.css'  // Map overlay/loading CSS (global)
import '../src/components/visualization/backgrounds/CleanMapBackground.css' // Background placeholders
import '../src/styles/components/loaders.css' // Any global loaders referenced by components
import { BackendStatusBanner } from '../src/components/system/BackendStatusBanner'
import { PLSSDownloadBanner } from '../src/components/plss/PLSSDownloadBanner'
import { ToastProvider } from '../src/components/ui/ToastProvider'
import { ApiKeyModal } from '../src/components/ApiKeyModal'
import { LogsButton } from '../src/components/logs/LogsButton'
import { installGlobalLogCapture } from '../src/services/logging/logStore'

export default function App({ Component, pageProps }: AppProps) {
  const [showKeyModal, setShowKeyModal] = useState(false)
  useEffect(() => {
    // Fire-and-forget dossier prewarm on app mount (read-only)
    try { startDossierPreload(); } catch {}

    // Check for stored API key and prompt if absent (retry/backoff + focus recheck)
    const checkKeyStatus = async () => {
      const delays = [500, 1000, 1500, 2500, 4000, 6000]
      for (let i = 0; i < delays.length; i++) {
        try {
          const res = await fetch('http://127.0.0.1:8000/config/key-status')
          if (res.ok) {
            const data = await res.json().catch(() => ({}))
            if (!data?.hasKey) setShowKeyModal(true)
            break
          }
        } catch {}
        await new Promise(r => setTimeout(r, delays[i]))
      }
    }
    ;(async () => {
      try {
        if ((window as any).__TAURI__) {
          const { invoke } = await import('@tauri-apps/api/core')
          await invoke('start_backend')
        }
      } catch {}
      checkKeyStatus()
    })()

    // Cleanup PLSS cache on application shutdown/page unload
    const handleBeforeUnload = () => {
      try {
        // Dynamically import to avoid issues if service isn't available
        import('../src/services/plss').then(({ plssCache }) => {
          const statusBefore = plssCache.getCacheStatus();
          console.log(`📊 Cache status before cleanup: ${statusBefore.totalEntries} entries, ${statusBefore.totalSections} sections`);

          plssCache.clearCache();
          console.log('🧹 PLSS cache cleared on application shutdown');

          const statusAfter = plssCache.getCacheStatus();
          console.log(`✅ Cache cleanup complete: ${statusAfter.totalEntries} entries, ${statusAfter.totalSections} sections remaining`);
        }).catch(() => {
          // Silently ignore if service isn't available
        });
      } catch (error) {
        // Silently ignore cleanup errors
      }
    };

    // Enhanced cleanup for Tauri/desktop application
    const handleAppClose = () => {
      console.log('🔄 Application closing - clearing PLSS cache...');
      handleBeforeUnload();
    };

    // Global devtools hotkey: Cmd/Ctrl+Shift+I opens Tauri devtools
    const handleDevtoolsHotkey = (e: KeyboardEvent) => {
      try {
        if (!(window as any).__TAURI__) return
        const isMod = e.ctrlKey || e.metaKey
        const isShift = e.shiftKey
        const key = (e.key || '').toLowerCase()
        if (!isMod || !isShift || key !== 'i') return
        e.preventDefault()
        import('@tauri-apps/api/core')
          .then(({ invoke }) => {
            return invoke('open_devtools').catch(() => {})
          })
          .catch(() => {})
      } catch {
        // Swallow hotkey errors; devtools are a convenience, not critical path.
      }
    }

    // Add event listeners for different shutdown scenarios
    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('keydown', handleDevtoolsHotkey as any);

    // Add global cache status function for debugging (available in console)
    (window as any).checkPLSSCache = () => {
      import('../src/services/plss').then(({ plssCache }) => {
        const status = plssCache.getCacheStatus();
        console.log(`📊 PLSS Cache Status: ${status.totalEntries} entries, ${status.totalSections} sections`);
        return status;
      }).catch(() => {
        console.log('❌ PLSS cache service not available');
      });
    };

    // Additional cleanup for page visibility changes (app minimize/background)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        console.log('👁️ App hidden - cache will be cleared on full shutdown');
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    // Re-check key status when app gains focus (helps if backend finished starting later)
    const handleFocus = () => { if (!showKeyModal) { checkKeyStatus(); } };
    window.addEventListener('focus', handleFocus);

    // Cleanup function - handles React unmount and manual cleanup
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('keydown', handleDevtoolsHotkey as any);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
      handleAppClose(); // Clear cache on component unmount
    };
  }, []);

  // Install frontend logging capture and prevent default browser file-open on drops outside dropzones
  useEffect(() => {
    try { installGlobalLogCapture(); } catch {}

    const preventIfOutsideDropzone = (e: Event) => {
      try {
        // Allow drops when any element in the composed path is within the dropzone
        const path: any[] = (e as any).composedPath ? (e as any).composedPath() : [];
        if (Array.isArray(path)) {
          for (const node of path) {
            const el = node as any;
            if (!el) continue;
            if (el.classList && el.classList.contains('file-drop-zone')) {
              return; // inside a valid dropzone
            }
            if (el.getAttribute && el.getAttribute('data-allow-drop') === 'true') {
              return; // inside a valid dropzone
            }
          }
        }
        // Fallback: check target.closest when available
        const target = e.target as any;
        if (target && typeof target.closest === 'function' && (target.closest('.file-drop-zone') || target.closest('[data-allow-drop="true"]')) ) {
          return;
        }
      } catch {}
      e.preventDefault();
    };

    window.addEventListener('dragover', preventIfOutsideDropzone as any, { passive: false });
    window.addEventListener('drop', preventIfOutsideDropzone as any, { passive: false });

    // Tauri desktop: bridge OS file-drop to DOM event for our dropzone
    let unlisten: (() => void) | null = null;
    (async () => {
      try {
        if ((window as any).__TAURI__) {
          const { listen } = await import('@tauri-apps/api/event');
          const { convertFileSrc } = await import('@tauri-apps/api/core');
          unlisten = await (listen as any)('tauri://file-drop', async (evt: any) => {
            try {
              const payload = evt?.payload;
              let paths: string[] = [];
              if (Array.isArray(payload)) {
                paths = payload as string[];
              } else if (Array.isArray(payload?.paths)) {
                paths = payload.paths as string[];
              }
              if (!paths || paths.length === 0) return;

              const files: File[] = [];
              for (const p of paths) {
                try {
                  const url = (convertFileSrc as any)(p);
                  const resp = await fetch(url);
                  const blob = await resp.blob();
                  const name = (p.split(/[/\\]/).pop() || 'file');
                  const ext = name.toLowerCase().split('.').pop() || '';
                  const mime = ext === 'png' ? 'image/png'
                    : ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg'
                    : ext === 'gif' ? 'image/gif'
                    : ext === 'bmp' ? 'image/bmp'
                    : ext === 'webp' ? 'image/webp'
                    : blob.type || 'application/octet-stream';
                  files.push(new File([blob], name, { type: mime }));
                } catch {}
              }
              if (files.length) {
                document.dispatchEvent(new CustomEvent('files:dropped', { detail: { files } }));
              }
            } catch {}
          });
        }
      } catch {}
    })();

    return () => {
      window.removeEventListener('dragover', preventIfOutsideDropzone as any);
      window.removeEventListener('drop', preventIfOutsideDropzone as any);
      try { unlisten && unlisten(); } catch {}
    };
  }, []);

  return (
    <ToastProvider>
      <div className="App">
        <BackendStatusBanner />
        <PLSSDownloadBanner />
        <main>
          <Component {...pageProps} />
          <ApiKeyModal open={showKeyModal} onClose={() => setShowKeyModal(false)} onSaved={() => location.reload()} />
          <LogsButton />
        </main>
      </div>
    </ToastProvider>
  )
} 
import type { AppProps } from 'next/app'
import { useEffect, useState } from 'react'
import { startDossierPreload } from '@/services/dossier/dossierPreload'
// import '../styles/globals.css'        // OLD (backup)
import '../styles/main.css'             // NEW (modular) - testing now!
import '../src/components/mapping/CleanMap.css'  // Map overlay/loading CSS (global)
import '../src/components/visualization/backgrounds/CleanMapBackground.css' // Background placeholders
import '../src/styles/components/loaders.css' // Any global loaders referenced by components
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

    // Add event listeners for different shutdown scenarios
    window.addEventListener('beforeunload', handleBeforeUnload);

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
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
      handleAppClose(); // Clear cache on component unmount
    };
  }, []);

  // Install frontend logging capture and prevent default browser file-open on drops outside dropzones
  useEffect(() => {
    try { installGlobalLogCapture(); } catch {}

    const preventIfOutsideDropzone = (e: Event) => {
      const target = e.target as HTMLElement | null;
      // Allow drops inside our dropzones; block elsewhere to prevent browser hijacking
      if (target && typeof (target as any).closest === 'function' && (target as any).closest('.file-drop-zone')) {
        return;
      }
      e.preventDefault();
    };

    window.addEventListener('dragover', preventIfOutsideDropzone as any, { passive: false });
    window.addEventListener('drop', preventIfOutsideDropzone as any, { passive: false });

    return () => {
      window.removeEventListener('dragover', preventIfOutsideDropzone as any);
      window.removeEventListener('drop', preventIfOutsideDropzone as any);
    };
  }, []);

  return (
    <ToastProvider>
      <div className="App">
        <main>
          <Component {...pageProps} />
          <ApiKeyModal open={showKeyModal} onClose={() => setShowKeyModal(false)} onSaved={() => location.reload()} />
          <LogsButton />
        </main>
      </div>
    </ToastProvider>
  )
} 
import type { AppProps } from 'next/app'
import { useEffect } from 'react'
// import '../styles/globals.css'        // OLD (backup)
import '../styles/main.css'             // NEW (modular) - testing now!
import '../src/components/mapping/CleanMap.css'  // Map overlay/loading CSS (global)
import '../src/components/visualization/backgrounds/CleanMapBackground.css' // Background placeholders
import '../src/styles/components/loaders.css' // Any global loaders referenced by components

export default function App({ Component, pageProps }: AppProps) {
  useEffect(() => {
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

    // Cleanup function - handles React unmount and manual cleanup
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      handleAppClose(); // Clear cache on component unmount
    };
  }, []);

  return (
    <div className="App">
      <main>
        <Component {...pageProps} />
      </main>
    </div>
  )
} 
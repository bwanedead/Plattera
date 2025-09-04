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
          plssCache.clearCache();
          console.log('🧹 PLSS cache cleared on application shutdown');
        }).catch(() => {
          // Silently ignore if service isn't available
        });
      } catch (error) {
        // Silently ignore cleanup errors
      }
    };

    // Add event listener for page unload
    window.addEventListener('beforeunload', handleBeforeUnload);

    // Cleanup function
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      handleBeforeUnload(); // Also clear on component unmount
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
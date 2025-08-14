import type { AppProps } from 'next/app'
// import '../styles/globals.css'        // OLD (backup) 
import '../styles/main.css'             // NEW (modular) - testing now!
import '../src/components/mapping/CleanMap.css'  // Map overlay/loading CSS (global)
import '../src/components/visualization/backgrounds/CleanMapBackground.css' // Background placeholders
import '../src/styles/components/loaders.css' // Any global loaders referenced by components

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className="App">
      <main>
        <Component {...pageProps} />
      </main>
    </div>
  )
} 
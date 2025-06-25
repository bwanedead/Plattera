import type { AppProps } from 'next/app'
// import '../styles/globals.css'        // OLD (backup) 
import '../styles/main.css'             // NEW (modular) - testing now!

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className="App">
      <main>
        <Component {...pageProps} />
      </main>
    </div>
  )
} 
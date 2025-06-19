import type { AppProps } from 'next/app'
import Header from '../src/components/Header'
import '../styles/globals.css'

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className="App">
      <Header />
      <main>
        <Component {...pageProps} />
      </main>
    </div>
  )
} 
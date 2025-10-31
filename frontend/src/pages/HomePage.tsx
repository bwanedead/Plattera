import React, { useState } from 'react'
import { ApiKeyModal } from '../components/ApiKeyModal';

const HomePage: React.FC = () => {
  const [showKeyModal, setShowKeyModal] = useState(false)
  return (
    <div className="page">
      <div className="container">
        <h1>Welcome to Plattera</h1>
        <p>Convert legal property descriptions into visual boundaries</p>
        
        <div className="features">
          <div className="feature-card">
            <h3>Text Processing</h3>
            <p>Upload legal descriptions and let our LLM parse the complex language</p>
          </div>
          
          <div className="feature-card">
            <h3>Geometry Generation</h3>
            <p>Convert metes and bounds into accurate boundary shapes</p>
          </div>
          
          <div className="feature-card">
            <h3>Interactive Visualization</h3>
            <p>View and interact with your property boundaries on a map</p>
          </div>
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
            onMouseOver={e => {
              (e.currentTarget as HTMLButtonElement).style.opacity = '0.95';
            }}
            onMouseOut={e => {
              (e.currentTarget as HTMLButtonElement).style.opacity = '1';
            }}
          >
            Set / Update API Key
          </button>
        </div>

        <ApiKeyModal open={showKeyModal} onClose={() => setShowKeyModal(false)} onSaved={() => location.reload()} />

      </div>
    </div>
  )
}

export default HomePage 
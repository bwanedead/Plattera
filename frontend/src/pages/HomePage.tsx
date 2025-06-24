import React from 'react'
import Link from 'next/link';

const HomePage: React.FC = () => {
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
          <Link href="/animation-tester" passHref>
            <a style={{
              display: 'inline-block',
              padding: '12px 24px',
              backgroundColor: 'var(--surface-secondary)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: '4px',
              textDecoration: 'none',
              fontWeight: 600,
              transition: 'all 0.2s ease'
            }}
            onMouseOver={e => {
              e.currentTarget.style.backgroundColor = 'var(--accent-primary)';
              e.currentTarget.style.color = 'white';
              e.currentTarget.style.borderColor = 'var(--accent-primary)';
            }}
            onMouseOut={e => {
              e.currentTarget.style.backgroundColor = 'var(--surface-secondary)';
              e.currentTarget.style.color = 'var(--text-primary)';
              e.currentTarget.style.borderColor = 'var(--border-color)';
            }}>
              Animation Tester
            </a>
          </Link>
        </div>

      </div>
    </div>
  )
}

export default HomePage 
import React from 'react'

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
      </div>
    </div>
  )
}

export default HomePage 
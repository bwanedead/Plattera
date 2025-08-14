import React from 'react'
import dynamic from 'next/dynamic'

// Dynamically import CleanMap (MapLibre) to avoid SSR issues
const CleanMap = dynamic(() => import('../src/components/mapping/CleanMap').then(mod => ({ default: mod.CleanMap })), {
  ssr: false
})

const ViewerPage: React.FC = () => {
  return (
    <div className="page">
      <div className="container">
        <h1>Boundary Viewer</h1>
        <div style={{ height: '600px', width: '100%' }}>
          <CleanMap />
        </div>
      </div>
    </div>
  )
}

export default ViewerPage 
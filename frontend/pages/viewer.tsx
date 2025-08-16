import React from 'react'
import dynamic from 'next/dynamic'

// Dynamically import MapWorkspace (MapLibre) to avoid SSR issues
const MapWorkspace = dynamic(
  () => import('../src/components/mapping/MapWorkspace').then(mod => ({ default: mod.MapWorkspace })),
  { ssr: false }
)

const ViewerPage: React.FC = () => {
  return (
    <div className="page">
      <div className="container">
        <h1>Boundary Viewer</h1>
        <div style={{ height: '80vh', width: '100%' }}>
          <MapWorkspace standalone className="map-workspace" />
        </div>
      </div>
    </div>
  )
}

export default ViewerPage
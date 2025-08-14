import React from 'react'
import dynamic from 'next/dynamic'

// Dynamically import MapViewer (MapLibre) to avoid SSR issues
const MapViewer = dynamic(() => import('../src/components/mapping/MapViewer'), {
  ssr: false
})

const ViewerPage: React.FC = () => {
  return (
    <div className="page">
      <div className="container">
        <h1>Boundary Viewer</h1>
        <MapViewer />
      </div>
    </div>
  )
}

export default ViewerPage 
import React from 'react'
import dynamic from 'next/dynamic'

// Dynamically import MapViewer to avoid SSR issues with Leaflet
const MapViewer = dynamic(() => import('../src/components/MapViewer'), {
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
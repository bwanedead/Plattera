import React from 'react'
import MapViewer from '../components/MapViewer'

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
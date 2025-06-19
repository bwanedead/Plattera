import React from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

const MapViewer: React.FC = () => {
  // Default center (you can make this dynamic later)
  const position: [number, number] = [39.8283, -98.5795] // Geographic center of US

  return (
    <div className="map-viewer">
      <MapContainer center={position} zoom={4} style={{ height: '500px', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={position}>
          <Popup>
            Property boundaries will appear here
          </Popup>
        </Marker>
      </MapContainer>
    </div>
  )
}

export default MapViewer 
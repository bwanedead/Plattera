import React from 'react';

interface ParcelLeg {
  bearing_deg: number;
  distance: number;
  distance_units: string;
  distance_sigma?: number;
  raw_text: string;
  confidence: number;
}

interface ParcelOrigin {
  type: string;
  lat?: number;
  lon?: number;
  zone?: number;
  easting_m?: number;
  northing_m?: number;
  t?: number; // Township
  r?: number; // Range
  section?: number;
  corner?: string;
  offset_m?: number;
  offset_bearing_deg?: number;
  note?: string;
}

interface ParcelSchema {
  parcel_id: string;
  crs: string;
  origin: ParcelOrigin;
  legs: ParcelLeg[];
  close: boolean;
  stated_area_ac?: number;
  source?: string;
}

interface FieldViewTabProps {
  schemaData: ParcelSchema | null;
  isSuccess: boolean;
  error?: string;
}

export const FieldViewTab: React.FC<FieldViewTabProps> = ({ 
  schemaData, 
  isSuccess, 
  error 
}) => {
  if (!isSuccess && error) {
    return (
      <div className="field-view-tab">
        <div className="error-display">
          <h4>Processing Error</h4>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!schemaData) {
    return (
      <div className="field-view-tab">
        <div className="processing-placeholder">
          <p>Convert your text to see organized field data here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="field-view-tab">
      <div className="field-view">
        {/* PLSS Description Section */}
        <div className="field-section">
          <h4>📍 PLSS Description</h4>
          <div className="field-group">
            <div className="field-item">
              <span className="field-label">Township:</span>
              <span className="field-value">{schemaData.origin.t ? `${schemaData.origin.t}` : 'Not specified'}</span>
            </div>
            <div className="field-item">
              <span className="field-label">Range:</span>
              <span className="field-value">{schemaData.origin.r ? `${schemaData.origin.r}` : 'Not specified'}</span>
            </div>
            <div className="field-item">
              <span className="field-label">Section:</span>
              <span className="field-value">{schemaData.origin.section || 'Not specified'}</span>
            </div>
            <div className="field-item">
              <span className="field-label">Corner:</span>
              <span className="field-value">{schemaData.origin.corner || 'Not specified'}</span>
            </div>
            <div className="field-item">
              <span className="field-label">CRS:</span>
              <span className="field-value">{schemaData.crs}</span>
            </div>
          </div>
        </div>

        {/* Metes and Bounds Section */}
        <div className="field-section">
          <h4>🗺️ Metes and Bounds</h4>
          <div className="field-group">
            {schemaData.legs && schemaData.legs.length > 0 ? (
              schemaData.legs.map((leg, index) => (
                <div key={index} className="leg-item">
                  <div className="leg-header">
                    <span className="leg-number">Leg {index + 1}</span>
                    <span className="confidence-badge" style={{
                      backgroundColor: leg.confidence > 0.8 ? '#4ade80' : leg.confidence > 0.6 ? '#fbbf24' : '#f87171'
                    }}>
                      {Math.round(leg.confidence * 100)}% confidence
                    </span>
                  </div>
                  <div className="leg-details">
                    <div className="field-item">
                      <span className="field-label">Bearing:</span>
                      <span className="field-value">{leg.bearing_deg}°</span>
                    </div>
                    <div className="field-item">
                      <span className="field-label">Distance:</span>
                      <span className="field-value">{leg.distance} {leg.distance_units}</span>
                    </div>
                    <div className="field-item">
                      <span className="field-label">Raw Text:</span>
                      <span className="field-value raw-text">"{leg.raw_text}"</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <p>No boundary legs found</p>
            )}
          </div>
        </div>

        {/* Property Details Section */}
        <div className="field-section">
          <h4>📊 Property Details</h4>
          <div className="field-group">
            <div className="field-item">
              <span className="field-label">Parcel ID:</span>
              <span className="field-value">{schemaData.parcel_id}</span>
            </div>
            <div className="field-item">
              <span className="field-label">Area:</span>
              <span className="field-value">{schemaData.stated_area_ac ? `${schemaData.stated_area_ac} acres` : 'Not specified'}</span>
            </div>
            <div className="field-item">
              <span className="field-label">Closes:</span>
              <span className="field-value">{schemaData.close ? 'Yes' : 'No'}</span>
            </div>
            <div className="field-item">
              <span className="field-label">Source:</span>
              <span className="field-value">{schemaData.source || 'Not specified'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}; 
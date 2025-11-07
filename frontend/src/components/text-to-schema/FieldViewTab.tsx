import React, { useState, useMemo } from 'react';
import { PolygonDrawingControls } from '../polygon/PolygonDrawingControls';

interface FieldViewTabProps {
  schemaData: any;
  isSuccess: boolean;
  error?: string;
  dossierId?: string; // Optional dossier context for persistence
  onEditInJson?: () => void;
}

// Utility function to convert field names to human-readable labels
const formatFieldLabel = (fieldName: string): string => {
  return fieldName
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
    .trim();
};

// Utility function to get section icons based on field names
const getSectionIcon = (fieldName: string): string => {
  const iconMap: Record<string, string> = {
    'plss_description': '📍',
    'metes_and_bounds': '🗺️',
    'boundary_courses': '🧭',
    'starting_point': '📌',
    'parcel': '🏞️',
    'location': '🌍',
    'coordinates': '📐',
    'source': '📄',
    'metadata': 'ℹ️'
  };
  
  const lowerField = fieldName.toLowerCase();
  for (const [key, icon] of Object.entries(iconMap)) {
    if (lowerField.includes(key)) {
      return icon;
    }
  }
  return '📋';
};

// Component to render individual field values
const FieldValue: React.FC<{ value: any; fieldName: string }> = ({ value, fieldName }) => {
  if (value === null || value === undefined) {
    return <span className="field-value null-value">Not specified</span>;
  }
  
  if (typeof value === 'boolean') {
    return (
      <span className={`field-value boolean-value ${value ? 'true' : 'false'}`}>
        {value ? 'Yes' : 'No'}
      </span>
    );
  }
  
  if (typeof value === 'number') {
    // Special formatting for certain field types
    if (fieldName.toLowerCase().includes('confidence') && value <= 1) {
      return (
        <span 
          className="field-value confidence-value"
          style={{
            backgroundColor: value > 0.8 ? '#4ade80' : value > 0.6 ? '#fbbf24' : '#f87171',
            color: 'white',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '0.9em'
          }}
        >
          {Math.round(value * 100)}% confidence
        </span>
      );
    }
    
    if (fieldName.toLowerCase().includes('acres')) {
      return <span className="field-value number-value">{value} acres</span>;
    }
    
    if (fieldName.toLowerCase().includes('distance')) {
      return <span className="field-value number-value">{value}</span>;
    }
    
    return <span className="field-value number-value">{value}</span>;
  }
  
  if (typeof value === 'string') {
    // Special formatting for raw text
    if (fieldName.toLowerCase().includes('raw_text') || fieldName.toLowerCase().includes('description')) {
      return (
        <span className="field-value raw-text" style={{ fontStyle: 'italic', color: '#666' }}>
          "{value}"
        </span>
      );
    }
    
    return <span className="field-value string-value">{value}</span>;
  }
  
  return <span className="field-value unknown-value">{String(value)}</span>;
};

// Add near the top, after existing imports
interface QCAdvisory {
  type: string;
  severity: 'info' | 'warning';
  field: string;
  message: string;
  blocking: boolean;
}

// Add this component after the existing FieldValue component
const AdvisoryAlert: React.FC<{ advisory: QCAdvisory; onDismiss?: () => void }> = ({ 
  advisory, 
  onDismiss 
}) => {
  const getIcon = () => {
    switch (advisory.type) {
      case 'range_adjacent': return 'ℹ️';
      case 'range_mismatch': return '⚠️';
      default: return 'ℹ️';
    }
  };

  return (
    <div className={`advisory-alert ${advisory.type} ${onDismiss ? 'dismissible' : ''}`}>
      <div className="alert-title">
        <span className="alert-icon">{getIcon()}</span>
        Advisory Notice
      </div>
      <div className="alert-message">{advisory.message}</div>
      {onDismiss && (
        <button className="dismiss-btn" onClick={onDismiss} title="Dismiss">
          ×
        </button>
      )}
    </div>
  );
};

// Component to render object fields
const ObjectField: React.FC<{ data: any; title: string; level?: number }> = ({ 
  data, 
  title, 
  level = 0 
}) => {
  if (!data || typeof data !== 'object') {
    return null;
  }

  const isArray = Array.isArray(data);
  const icon = getSectionIcon(title);
  
  return (
    <div className={`field-section level-${level}`}>
      <h4 className="section-title">
        {icon} {formatFieldLabel(title)}
      </h4>
      
      {isArray ? (
        <div className="array-field">
          {data.length === 0 ? (
            <p className="empty-array">No items found</p>
          ) : (
            data.map((item, index) => (
              <div key={index} className="array-item">
                <div className="array-item-header">
                  <span className="array-item-number">
                    {formatFieldLabel(title).slice(0, -1)} {index + 1}
                  </span>
                </div>
                <div className="array-item-content">
                  {typeof item === 'object' ? (
                    <ObjectField data={item} title={`item_${index}`} level={level + 1} />
                  ) : (
                    <div className="field-item">
                      <span className="field-label">Value:</span>
                      <FieldValue value={item} fieldName={title} />
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="field-group">
          {Object.entries(data).map(([key, value]) => {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
              // Nested object - render as subsection
              return (
                <ObjectField 
                  key={key} 
                  data={value} 
                  title={key} 
                  level={level + 1}
                />
              );
            } else if (Array.isArray(value)) {
              // Array - render as subsection
              return (
                <ObjectField 
                  key={key} 
                  data={value} 
                  title={key} 
                  level={level + 1}
                />
              );
            } else {
              // Primitive value - render as field
              return (
                <div key={key} className="field-item">
                  <span className="field-label">{formatFieldLabel(key)}:</span>
                  <FieldValue value={value} fieldName={key} />
                </div>
              );
            }
          })}
        </div>
      )}
    </div>
  );
};

// Update the main component to include QC summary
export const FieldViewTab: React.FC<FieldViewTabProps> = ({ 
  schemaData, 
  isSuccess, 
  error,
  dossierId,
  onEditInJson
}) => {
  const [dismissedAdvisories, setDismissedAdvisories] = useState<Set<string>>(new Set());

  // Collect all advisories from schema data
  const allAdvisories = useMemo(() => {
    if (!schemaData?.descriptions) return [];
    
    const advisories: QCAdvisory[] = [];
    schemaData.descriptions.forEach((desc: any, index: number) => {
      if (desc.qc_advisories) {
        desc.qc_advisories.forEach((advisory: QCAdvisory) => {
          advisories.push({
            ...advisory,
            field: `descriptions.${index}.${advisory.field}`
          });
        });
      }
    });
    
    return advisories.filter(advisory => 
      !dismissedAdvisories.has(`${advisory.field}-${advisory.type}`)
    );
  }, [schemaData, dismissedAdvisories]);

  const handleDismissAdvisory = (advisory: QCAdvisory) => {
    setDismissedAdvisories(prev => 
      new Set([...prev, `${advisory.field}-${advisory.type}`])
    );
  };

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
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        {isSuccess && schemaData && (
          <button onClick={onEditInJson}>Edit in JSON</button>
        )}
      </div>
      {/* QC Summary */}
      <div className={`qc-summary ${allAdvisories.length > 0 ? 'has-advisories' : ''}`}>
        <h4>
          {allAdvisories.length > 0 ? 'ℹ️ Quality Check Advisories' : '✅ Data Quality Check'}
        </h4>
        {allAdvisories.length > 0 ? (
          <ul className="advisory-list">
            {allAdvisories.map((advisory, index) => (
              <li key={index}>{advisory.message}</li>
            ))}
          </ul>
        ) : (
          <div className="no-issues">
            <span>✅</span>
            <span>No data quality issues detected</span>
          </div>
        )}
      </div>

      {/* Individual Advisory Alerts */}
      {allAdvisories.map((advisory, index) => (
        <AdvisoryAlert 
          key={index}
          advisory={advisory}
          onDismiss={() => handleDismissAdvisory(advisory)}
        />
      ))}
      
      {/* ADD: Polygon Drawing Controls */}
      <PolygonDrawingControls 
        schemaData={schemaData}
        isVisible={isSuccess && !!schemaData}
        dossierId={dossierId || schemaData?.metadata?.dossierId || schemaData?.metadata?.dossier_id}
      />
      
      <div className="field-view">
        <ObjectField data={schemaData} title="parcel_data" />
      </div>
    </div>
  );
}; 
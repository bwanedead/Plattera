import React, { useState, useCallback } from 'react';

interface EditableFieldViewTabProps {
  schemaData: any;
  isSuccess: boolean;
  error?: string;
  onSchemaUpdate?: (updatedData: any) => void;
}

interface ValidationIssue {
  field: string;
  type: 'warning' | 'error';
  message: string;
}

// Validation function for detecting inconsistencies
const validateSchemaData = (data: any): ValidationIssue[] => {
  const issues: ValidationIssue[] = [];
  
  if (data?.descriptions) {
    data.descriptions.forEach((desc: any, index: number) => {
      if (desc?.plss) {
        const mainRange = desc.plss.range_number;
        const startingPoint = desc.plss.starting_point;
        
        // Check for range mismatch
        if (startingPoint?.tie_to_corner?.corner_label && mainRange) {
          const rangeMatch = startingPoint.tie_to_corner.corner_label.match(/R(\d+)W/);
          if (rangeMatch) {
            const tieRange = parseInt(rangeMatch[1]);
            if (tieRange !== mainRange) {
              issues.push({
                field: `descriptions.${index}.plss.starting_point`,
                type: 'warning',
                message: `Range mismatch: PLSS shows R${mainRange}W but tie corner shows R${tieRange}W`
              });
            }
          }
        }
        
        // Check POB completeness
        if (startingPoint?.pob_status === 'ambiguous') {
          issues.push({
            field: `descriptions.${index}.plss.starting_point.pob_status`,
            type: 'error',
            message: 'Point of Beginning is ambiguous and needs clarification'
          });
        }
      }
    });
  }
  
  return issues;
};

// Editable field component
const EditableFieldValue: React.FC<{
  value: any;
  fieldName: string;
  fieldPath: string;
  onValueChange: (path: string, newValue: any) => void;
  validationIssues: ValidationIssue[];
}> = ({ value, fieldName, fieldPath, onValueChange, validationIssues }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  
  const issues = validationIssues.filter(issue => issue.field === fieldPath);
  const hasWarning = issues.some(issue => issue.type === 'warning');
  const hasError = issues.some(issue => issue.type === 'error');
  
  const handleSave = () => {
    onValueChange(fieldPath, editValue);
    setIsEditing(false);
  };
  
  const handleCancel = () => {
    setEditValue(value);
    setIsEditing(false);
  };
  
  if (value === null || value === undefined) {
    return <span className="field-value null-value">Not specified</span>;
  }
  
  const getFieldStyle = () => {
    if (hasError) return { backgroundColor: '#fee2e2', borderLeft: '3px solid #ef4444' };
    if (hasWarning) return { backgroundColor: '#fef3c7', borderLeft: '3px solid #f59e0b' };
    return {};
  };
  
  if (typeof value === 'boolean') {
    return (
      <div style={getFieldStyle()}>
        <select
          value={value.toString()}
          onChange={(e) => onValueChange(fieldPath, e.target.value === 'true')}
          className="editable-boolean"
        >
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
        {issues.map((issue, i) => (
          <div key={i} className={`validation-message ${issue.type}`}>
            {issue.type === 'warning' ? '⚠️' : '❌'} {issue.message}
          </div>
        ))}
      </div>
    );
  }
  
  if (typeof value === 'number') {
    return (
      <div style={getFieldStyle()}>
        {isEditing ? (
          <div className="edit-controls">
            <input
              type="number"
              value={editValue}
              onChange={(e) => setEditValue(parseFloat(e.target.value) || 0)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave();
                if (e.key === 'Escape') handleCancel();
              }}
              autoFocus
            />
            <button onClick={handleSave} className="save-btn">✓</button>
            <button onClick={handleCancel} className="cancel-btn">✗</button>
          </div>
        ) : (
          <span 
            className="field-value number-value editable"
            onClick={() => setIsEditing(true)}
            title="Click to edit"
          >
            {value} {fieldName.toLowerCase().includes('acres') ? 'acres' : ''}
          </span>
        )}
        {issues.map((issue, i) => (
          <div key={i} className={`validation-message ${issue.type}`}>
            {issue.type === 'warning' ? '⚠️' : '❌'} {issue.message}
          </div>
        ))}
      </div>
    );
  }
  
  if (typeof value === 'string') {
    return (
      <div style={getFieldStyle()}>
        {isEditing ? (
          <div className="edit-controls">
            <input
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave();
                if (e.key === 'Escape') handleCancel();
              }}
              autoFocus
            />
            <button onClick={handleSave} className="save-btn">✓</button>
            <button onClick={handleCancel} className="cancel-btn">✗</button>
          </div>
        ) : (
          <span 
            className="field-value string-value editable"
            onClick={() => setIsEditing(true)}
            title="Click to edit"
          >
            {fieldName.toLowerCase().includes('raw_text') ? `"${value}"` : value}
          </span>
        )}
        {issues.map((issue, i) => (
          <div key={i} className={`validation-message ${issue.type}`}>
            {issue.type === 'warning' ? '⚠️' : '❌'} {issue.message}
          </div>
        ))}
      </div>
    );
  }
  
  return <span className="field-value">{String(value)}</span>;
};

export const EditableFieldViewTab: React.FC<EditableFieldViewTabProps> = ({ 
  schemaData, 
  isSuccess, 
  error,
  onSchemaUpdate
}) => {
  const [editedData, setEditedData] = useState(schemaData);
  const validationIssues = validateSchemaData(editedData);
  
  const handleValueChange = useCallback((path: string, newValue: any) => {
    const pathParts = path.split('.');
    const newData = JSON.parse(JSON.stringify(editedData));
    
    let current = newData;
    for (let i = 0; i < pathParts.length - 1; i++) {
      current = current[pathParts[i]];
    }
    current[pathParts[pathParts.length - 1]] = newValue;
    
    setEditedData(newData);
    onSchemaUpdate?.(newData);
  }, [editedData, onSchemaUpdate]);
  
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

  if (!editedData) {
    return (
      <div className="field-view-tab">
        <div className="processing-placeholder">
          <p>Convert your text to see organized field data here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="field-view-tab editable">
      {validationIssues.length > 0 && (
        <div className="validation-summary">
          <h4>⚠️ Data Quality Issues Found:</h4>
          <ul>
            {validationIssues.map((issue, i) => (
              <li key={i} className={issue.type}>
                <strong>{issue.field}:</strong> {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      
      <div className="field-view">
        {/* Render editable object fields here - simplified for brevity */}
        <pre style={{ fontSize: '12px', background: '#f5f5f5', padding: '10px' }}>
          {JSON.stringify(editedData, null, 2)}
        </pre>
      </div>
    </div>
  );
}; 
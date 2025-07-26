import React from 'react';
import { CopyButton } from '../CopyButton';

interface JsonSchemaTabProps {
  schemaData: any;
  isSuccess: boolean;
  error?: string;
}

export const JsonSchemaTab: React.FC<JsonSchemaTabProps> = ({ 
  schemaData, 
  isSuccess, 
  error 
}) => {
  if (!isSuccess && error) {
    return (
      <div className="json-schema-tab">
        <div className="error-display">
          <h4>Processing Error</h4>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!schemaData) {
    return (
      <div className="json-schema-tab">
        <div className="processing-placeholder">
          <p>Convert your text to see the JSON schema here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="json-schema-tab">
      <div className="tab-header">
        <h4>JSON Schema</h4>
        <CopyButton
          onCopy={() => navigator.clipboard.writeText(JSON.stringify(schemaData, null, 2))}
          title="Copy schema JSON"
        />
      </div>
      <div className="json-content">
        <pre className="json-schema">
          {JSON.stringify(schemaData, null, 2)}
        </pre>
      </div>
    </div>
  );
}; 
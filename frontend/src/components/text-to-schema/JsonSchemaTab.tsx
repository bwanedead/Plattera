import React from 'react';
import { CopyButton } from '../CopyButton';
import { saveSchemaForDossier } from '../../services/textToSchemaApi';

interface JsonSchemaTabProps {
  schemaData: any;
  isSuccess: boolean;
  error?: string;
  dossierId?: string;
  originalText?: string;
  currentSchemaId?: string;
  startEditToken?: number; // toggling this will force edit mode on (must be > 0)
  onSaved?: (artifact: any) => void;
}

export const JsonSchemaTab: React.FC<JsonSchemaTabProps> = ({ 
  schemaData, 
  isSuccess, 
  error,
  dossierId,
  originalText,
  currentSchemaId,
  startEditToken,
  onSaved
}) => {
  const [editMode, setEditMode] = React.useState(false);
  const [buffer, setBuffer] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    // Only enter edit mode when an explicit token > 0 is provided (Field View "Edit in JSON")
    if (startEditToken && Number.isFinite(startEditToken)) {
      setEditMode(true);
      if (schemaData) setBuffer(JSON.stringify(schemaData, null, 2));
      setErr(null);
    }
  }, [startEditToken, schemaData]);

  // Ensure selecting a schema or switching to JSON tab defaults to preview mode
  React.useEffect(() => {
    if (!startEditToken) {
      setEditMode(false);
      setErr(null);
    }
  }, [schemaData]); 
  React.useEffect(() => {
    if (!editMode) return;
    if (schemaData) setBuffer(JSON.stringify(schemaData, null, 2));
  }, [schemaData, editMode]);

  const handleSave = async () => {
    try {
      setErr(null);
      const parsed = JSON.parse(buffer);
      if (!dossierId) throw new Error('Missing dossier context');
      const ot = originalText ?? '';
      const res = await saveSchemaForDossier({
        dossier_id: String(dossierId),
        model_used: 'manual_edit',
        structured_data: parsed,
        original_text: ot,
        metadata: {
          parent_schema_id: currentSchemaId || (schemaData?.schema_id),
          version_label: 'v2',
          edited: true
        }
      });
      try { onSaved?.(res); } catch {}
      setEditMode(false);
    } catch (e: any) {
      setErr(e?.message || 'Failed to save schema');
    }
  };
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
        <div className="header-actions">
          <CopyButton
            onCopy={() => {
              const text = editMode ? buffer : JSON.stringify(schemaData, null, 2);
              navigator.clipboard.writeText(text);
            }}
            title="Copy schema JSON"
          />
          {!editMode ? (
            <button
              onClick={() => { setEditMode(true); setBuffer(JSON.stringify(schemaData, null, 2)); }}
              className="final-draft-button"
              title="Enable Edit Mode"
            >
              Edit
            </button>
          ) : (
            <>
              <button onClick={handleSave} className="final-draft-button" title="Save as v2">
                Save (v2)
              </button>
              <button onClick={() => setEditMode(false)} className="final-draft-button" title="Cancel edits">
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      <div className="json-content">
        {editMode ? (
          <>
            {err && (
              <div className="error-display" style={{ marginBottom: 8 }}>
                {err}
              </div>
            )}
            <textarea
              value={buffer}
              onChange={(e) => setBuffer(e.target.value)}
              rows={24}
              style={{ width: '100%' }}
            />
          </>
        ) : (
          <pre className="json-schema">
            {JSON.stringify(schemaData, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}; 
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
  rootSchemaId?: string;
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
  rootSchemaId,
  startEditToken,
  onSaved
}) => {
  const [editMode, setEditMode] = React.useState(false);
  const [buffer, setBuffer] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const [localPreview, setLocalPreview] = React.useState<string | null>(null);
  const lastTokenRef = React.useRef<number>(0);
  // Keep scroll parity between preview and editor
  const contentRef = React.useRef<HTMLDivElement | null>(null);
  const lastScrollRef = React.useRef<number>(0);

  React.useEffect(() => {
    // Only enter edit mode when token changes (one-shot trigger from Field View)
    if (startEditToken && Number.isFinite(startEditToken) && startEditToken !== lastTokenRef.current) {
      lastTokenRef.current = startEditToken;
      lastScrollRef.current = contentRef.current?.scrollTop || 0;
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
    // restore previous scroll position after switching into edit
    requestAnimationFrame(() => {
      if (contentRef.current) contentRef.current.scrollTop = lastScrollRef.current;
    });
  }, [schemaData, editMode]);

  // Clear optimistic preview when the parent updates schemaData
  React.useEffect(() => {
    if (!editMode && localPreview) {
      try {
        // If parent schemaData now matches our preview, clear the override
        const s = JSON.stringify(schemaData, null, 2);
        if (s === localPreview) setLocalPreview(null);
      } catch {}
    }
  }, [schemaData, editMode, localPreview]);

  // Clear optimistic preview when switching between artifacts (schema id changes)
  React.useEffect(() => {
    try {
      const idFromData = (schemaData as any)?.schema_id;
      // Any change in effective id should reset local preview so we don't stick to prior edits
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      idFromData || currentSchemaId; // reference to satisfy linter in dependency calc
      setLocalPreview(null);
    } catch {
      setLocalPreview(null);
    }
    // Depend on the id and currentSchemaId to reset when selection changes
  }, [(schemaData as any)?.schema_id, currentSchemaId]);

  const handleSave = async () => {
    try {
      setErr(null);
      const parsed = JSON.parse(buffer);
      // Resolve dossier context from props or embedded metadata
      const effectiveDossier =
        dossierId ||
        (schemaData as any)?.metadata?.dossierId ||
        (schemaData as any)?.metadata?.dossier_id;
      if (!effectiveDossier) throw new Error('Missing dossier context');
      const ot = originalText ?? '';
      const parentBase = String(rootSchemaId || currentSchemaId || (schemaData?.schema_id || ''));
      const parentForSave = parentBase.endsWith('_v2') ? parentBase.replace(/_v2$/, '') : parentBase;
      const res = await saveSchemaForDossier({
        dossier_id: String(effectiveDossier),
        model_used: 'manual_edit',
        structured_data: parsed,
        original_text: ot,
        metadata: {
          // Always group under the root v1 so we only have v1/v2 (no v3+)
          parent_schema_id: parentForSave,
          version_label: 'v2',
          edited: true
        }
      });
      // Optimistically show the just-saved content
      setLocalPreview(JSON.stringify(parsed, null, 2));
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

  // Derive schema identity for display (user-facing)
  const schemaLabel =
    (schemaData as any)?.metadata?.schema_label ||
    (schemaData as any)?.metadata?.dossierTitle ||
    'Schema';
  const versionLabel: string | undefined =
    ((schemaData as any)?.metadata?.version_label as string | undefined) ||
    ((schemaData as any)?.lineage?.version_label as string | undefined);

  return (
    <div className="json-schema-tab">
      <div className="tab-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h4>{schemaLabel}</h4>
          {versionLabel && (
            <span
              className="version-tag"
              style={{
                fontSize: '0.75rem',
                padding: '2px 8px',
                borderRadius: '12px',
                background: '#111827',
                color: '#e5e7eb',
                border: '1px solid #374151',
              }}
              title={`Schema version: ${versionLabel}`}
            >
              {String(versionLabel).toUpperCase()}
            </span>
          )}
        </div>
        <div className="header-actions">
          <CopyButton
            onCopy={() => {
              const text = editMode ? buffer : (localPreview || JSON.stringify(schemaData, null, 2));
              navigator.clipboard.writeText(text);
            }}
            title="Copy schema JSON"
          />
          {!editMode ? (
            <button
              onClick={() => { 
                lastScrollRef.current = contentRef.current?.scrollTop || 0;
                setEditMode(true); 
                setBuffer(JSON.stringify(schemaData, null, 2)); 
              }}
              className="final-draft-button compact"
              title="Enable Edit Mode"
            >
              Edit
            </button>
          ) : (
            <>
              <button onClick={handleSave} className="final-draft-button compact" title="Save as v2">
                Save (v2)
              </button>
              <button onClick={() => setEditMode(false)} className="final-draft-button compact" title="Cancel edits">
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      <div className="json-content" ref={contentRef}>
        {editMode ? (
          <>
            {err && (
              <div className="error-display" style={{ marginBottom: 8 }}>
                {err}
              </div>
            )}
            <textarea
              className="json-editor"
              value={buffer}
              onChange={(e) => setBuffer(e.target.value)}
              rows={24}
            />
          </>
        ) : (
          <pre className="json-schema">
            {localPreview || JSON.stringify(schemaData, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}; 
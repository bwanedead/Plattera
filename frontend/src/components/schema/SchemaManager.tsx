import React, { useCallback } from 'react';
import { useSchemaManager } from '../../hooks/useSchemaManager';
import { schemaApi } from '../../services/schema/schemaApi';

interface SchemaManagerProps {
  dossierId: string | null;
  onSelectionChange?: (schema: { schema_id: string; dossier_id: string }) => void;
  className?: string;
}

export const SchemaManager: React.FC<SchemaManagerProps> = ({ dossierId, onSelectionChange, className = '' }) => {
  const mgr = useSchemaManager(dossierId);
  const { state } = mgr;

  const handleSelect = useCallback(async (schemaId: string) => {
    mgr.selectSchema(schemaId);
    if (dossierId && onSelectionChange) {
      onSelectionChange({ schema_id: schemaId, dossier_id: dossierId });
    }
  }, [mgr, dossierId, onSelectionChange]);

  return (
    <div className={`schema-manager ${className}`} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="schema-manager-header" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <h4 style={{ margin: 0, flex: 1 }}>Schemas</h4>
        <button onClick={mgr.refresh} disabled={state.loading}>Refresh</button>
      </div>

      <div className="schema-manager-search" style={{ marginBottom: 8 }}>
        <input
          type="text"
          placeholder="Search schemas..."
          value={state.searchQuery}
          onChange={(e) => mgr.setSearchQuery(e.target.value)}
          style={{ width: '100%' }}
        />
      </div>

      <div className="schema-list" style={{ flex: 1, overflow: 'auto', border: '1px solid #333', borderRadius: 4 }}>
        {state.loading && <div style={{ padding: 8 }}>Loading...</div>}
        {!state.loading && mgr.filteredSchemas.length === 0 && (
          <div style={{ padding: 8, opacity: 0.7 }}>{dossierId ? 'No schemas for this dossier.' : 'Select a dossier to view schemas.'}</div>
        )}
        {mgr.filteredSchemas.map(item => {
          const selected = state.selectedSchemaId === item.schema_id;
          return (
            <div
              key={item.schema_id}
              onClick={() => handleSelect(item.schema_id)}
              className={`schema-list-item ${selected ? 'selected' : ''}`}
              style={{
                padding: '8px 10px',
                cursor: 'pointer',
                background: selected ? '#1f2937' : 'transparent',
                borderBottom: '1px solid #2d2d2d'
              }}
              title={item.schema_id}
            >
              <div style={{ fontWeight: 600 }}>{item.dossier_title_snapshot || item.dossier_id}</div>
              <div style={{ fontSize: 12, opacity: 0.8 }}>
                {item.saved_at ? new Date(item.saved_at).toLocaleString() : 'Unknown date'}
              </div>
              <div style={{ fontSize: 11, opacity: 0.6, wordBreak: 'break-all' }}>{item.schema_id}</div>
              {selected && dossierId && (
                <div style={{ marginTop: 6 }}>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!confirm('Delete this schema artifact?')) return;
                      try { await mgr.deleteSchema(item.schema_id); } catch {}
                    }}
                  >
                    Delete
                  </button>
                  <button
                    style={{ marginLeft: 8 }}
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (!confirm('Purge this schema and any dependent georeferences?')) return;
                      try {
                        await schemaApi.purgeSchema(dossierId, item.schema_id);
                        mgr.refresh();
                      } catch {}
                    }}
                  >
                    Delete + Purge Georefs
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};



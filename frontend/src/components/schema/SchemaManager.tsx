import React, { useCallback, useMemo, useState } from 'react';
import { useSchemaManager } from '../../hooks/useSchemaManager';
import { schemaApi } from '../../services/schema/schemaApi';
import { ConfirmDeleteModal } from '../dossier/modals/ConfirmDeleteModal';

interface SchemaManagerProps {
  dossierId: string | null;
  onSelectionChange?: (schema: { schema_id: string; dossier_id: string }) => void;
  className?: string;
}

export const SchemaManager: React.FC<SchemaManagerProps> = ({ dossierId, onSelectionChange, className = '' }) => {
  const mgr = useSchemaManager(dossierId);
  const { state, metaById } = mgr;
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ schemaId: string; dossierId: string; title: string } | null>(null);
  const [renameTarget, setRenameTarget] = useState<{ schemaId: string; dossierId: string; title: string } | null>(null);
  const [renameValue, setRenameValue] = useState<string>('');
  const [renameBusy, setRenameBusy] = useState(false);

  // Track optimistic/pending schemas created on the frontend (e.g., direct-text runs)
  const [pending, setPending] = useState<
    Array<{ tempId: string; label: string; dossier_id: string; created_at: string }>
  >([]);

  // Auto-refresh on global schema events
  React.useEffect(() => {
    const handler = () => mgr.refresh();
    document.addEventListener('schemas:refresh', handler as any);
    return () => document.removeEventListener('schemas:refresh', handler as any);
  }, [mgr]);

  // Listen for pending schema add/remove events
  React.useEffect(() => {
    const onAdd = (ev: Event) => {
      try {
        const detail: any = (ev as CustomEvent)?.detail || {};
        if (!detail?.tempId) return;
        const tempId = String(detail.tempId);
        const label = String(detail.label || 'New schema (processing…)');
        const dossier_id = String(detail.dossier_id || '');
        const created_at = String(detail.created_at || new Date().toISOString());
        setPending((prev) => {
          // Avoid duplicates for same tempId
          if (prev.some((p) => p.tempId === tempId)) return prev;
          return [...prev, { tempId, label, dossier_id, created_at }];
        });
      } catch {}
    };

    const onRemove = (ev: Event) => {
      try {
        const detail: any = (ev as CustomEvent)?.detail || {};
        const tempId = String(detail?.tempId || '');
        if (!tempId) return;
        setPending((prev) => prev.filter((p) => p.tempId !== tempId));
      } catch {}
    };

    document.addEventListener('schemas:pending-add', onAdd as any);
    document.addEventListener('schemas:pending-remove', onRemove as any);
    return () => {
      document.removeEventListener('schemas:pending-add', onAdd as any);
      document.removeEventListener('schemas:pending-remove', onRemove as any);
    };
  }, []);
  // Precompute version groups so pills show consistently for both v1 and v2 rows
  const versionGroups = useMemo(() => {
    const groups = new Map<string, { v1?: any; v2?: any }>();
    const items = state.items || [];
    for (const it of items) {
      const meta = metaById?.[it.schema_id] || {};
      let rootId = meta.parent_schema_id || it.schema_id;
      // Fallback: if metadata is not loaded yet, use suffix heuristic
      if (!meta.parent_schema_id && it.schema_id && String(it.schema_id).endsWith('_v2')) {
        rootId = String(it.schema_id).replace(/_v2$/, '');
      }
      if (!groups.has(rootId)) groups.set(rootId, {});
      const g = groups.get(rootId)!;
      if (it.schema_id === rootId) g.v1 = it;
      if (meta.parent_schema_id || String(it.schema_id).endsWith('_v2')) g.v2 = it;
    }
    return groups;
  }, [state.items, metaById]);

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
        {!state.loading && mgr.filteredSchemas.length === 0 && pending.length === 0 && (
          <div style={{ padding: 8, opacity: 0.7 }}>No schemas found.</div>
        )}

        {/* Pending / in-flight schemas (e.g., direct-text) */}
        {pending.map((p) => (
          <div
            key={p.tempId}
            className="schema-list-item pending"
            style={{
              padding: '8px 10px',
              borderBottom: '1px solid #2d2d2d',
              background: '#111827',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
            }}
            title={p.label}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
              <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {p.label}
              </div>
              <div style={{ fontSize: 11, opacity: 0.7 }}>
                {p.dossier_id || 'Direct text'} • In progress…
              </div>
            </div>
          </div>
        ))}

    {(() => {
      // Build display groups from filtered list (dedupe per root)
      const seen = new Set<string>();
      const groups: Array<{ rootId: string; v1?: any; v2?: any; representative: any }> = [];
      for (const item of mgr.filteredSchemas) {
        const meta = metaById?.[item.schema_id] || {};
        let rootId = meta.parent_schema_id || item.schema_id;
        if (!meta.parent_schema_id && item.schema_id && String(item.schema_id).endsWith('_v2')) {
          rootId = String(item.schema_id).replace(/_v2$/, '');
        }
        if (seen.has(rootId)) continue;
        seen.add(rootId);
        const g = versionGroups.get(rootId) || {};
        groups.push({ rootId, v1: g.v1, v2: g.v2, representative: g.v1 || g.v2 || item });
      }
      return groups;
    })().map(group => {
      const item = group.representative;
      const v1 = group.v1 || null;
      const v2 = group.v2 || null;
      const isSelected =
        !!state.selectedSchemaId &&
        (state.selectedSchemaId === (v1 && v1.schema_id) ||
          state.selectedSchemaId === (v2 && v2.schema_id));
      return (
        <div
          key={group.rootId}
          onClick={() => handleSelect(v1?.schema_id || item.schema_id)}
          className={`schema-list-item ${isSelected ? 'selected' : ''}`}
          style={{
            padding: '8px 10px',
            cursor: 'pointer',
            background: isSelected ? '#1f2937' : 'transparent',
            borderBottom: '1px solid #2d2d2d',
            position: 'relative'
          }}
          title={group.rootId}
          onMouseEnter={() => setHoveredId(item.schema_id)}
          onMouseLeave={() => setHoveredId(null)}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {((item as any).schema_label || item.dossier_title_snapshot || item.dossier_id)}
              </div>
              {/* version pills (only show when a v2 exists; show both v1 and v2) */}
              {v2 ? (
                <>
                  {v1 && (
                  <button
                      className="dossier-action-btn"
                      style={{
                        fontSize: 11,
                        padding: '2px 6px',
                        borderRadius: 10,
                        backgroundColor:
                          state.selectedSchemaId === v1.schema_id ? '#3b82f6' : undefined,
                        color:
                          state.selectedSchemaId === v1.schema_id ? '#fff' : undefined,
                        border:
                          state.selectedSchemaId === v1.schema_id
                            ? '1px solid #2563eb'
                            : undefined,
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelect(v1.schema_id);
                        onSelectionChange?.({
                          schema_id: v1.schema_id,
                          dossier_id: v1.dossier_id,
                        });
                      }}
                      title="View v1"
                    >
                      v1
                    </button>
                  )}
                <button
                    className="dossier-action-btn"
                    style={{
                      fontSize: 11,
                      padding: '2px 6px',
                      borderRadius: 10,
                      backgroundColor:
                        state.selectedSchemaId === v2.schema_id ? '#3b82f6' : undefined,
                      color:
                        state.selectedSchemaId === v2.schema_id ? '#fff' : undefined,
                      border:
                        state.selectedSchemaId === v2.schema_id
                          ? '1px solid #2563eb'
                          : undefined,
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (v2) {
                        handleSelect(v2.schema_id);
                        onSelectionChange?.({
                          schema_id: v2.schema_id,
                          dossier_id: v2.dossier_id,
                        });
                      }
                    }}
                    title="View v2"
                  >
                    v2
                  </button>
                </>
              ) : null}
            </div>
            <div className="dossier-actions" style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              <button
                className="dossier-action-btn"
                onClick={async (e) => {
                  e.stopPropagation();
                  // Prefer the active selection for this group if it matches;
                  // otherwise default to v2 or v1.
                  const current = state.selectedSchemaId;
                  const target =
                    current === (v1 && v1.schema_id) || current === (v2 && v2.schema_id)
                      ? current
                      : v2?.schema_id || v1?.schema_id || item.schema_id;

                  if (target) {
                    await handleSelect(target);
                  onSelectionChange?.({ schema_id: target, dossier_id: item.dossier_id });
                  }
                }}
                title="View schema"
              >
                View
              </button>
              <button
                className="dossier-action-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  const baseLabel =
                    (item as any).schema_label ||
                    item.dossier_title_snapshot ||
                    group.rootId;
                  setRenameTarget({
                    schemaId: group.rootId,
                    dossierId: item.dossier_id,
                    title: baseLabel,
                  });
                  setRenameValue(baseLabel);
                }}
                title="Rename schema"
              >
                Rename
              </button>
              <button
                className="dossier-action-btn danger"
                onClick={async (e) => {
                  e.stopPropagation();
                  // Always purge by root id to remove v1 + v2 + dependent georefs
                  setDeleteTarget({ schemaId: group.rootId, dossierId: item.dossier_id, title: item.dossier_title_snapshot || item.schema_id });
                }}
                title="Delete schema and purge dependents"
              >
                Delete
              </button>
            </div>
          </div>
          <div style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>
            {item.saved_at ? new Date(item.saved_at).toLocaleString() : 'Unknown date'}
          </div>
        </div>
      );
    })}
      {deleteTarget && (
        <ConfirmDeleteModal
          itemName={deleteTarget.title}
          itemType="schema"
          onConfirm={async () => {
            try {
              await schemaApi.purgeSchema(deleteTarget.dossierId, deleteTarget.schemaId);
              setDeleteTarget(null);
              mgr.refresh();
            } catch (e) {
              setDeleteTarget(null);
            }
          }}
          onCancel={() => setDeleteTarget(null)}
          busyText="Deleting…"
          allowBackgroundClose={false}
          showProgressBar={false}
        />
      )}

      {renameTarget && (
        <div
          className="schema-rename-modal-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            className="schema-rename-modal"
            style={{
              background: '#111827',
              padding: 16,
              borderRadius: 8,
              minWidth: 320,
              border: '1px solid #374151',
              boxShadow: '0 10px 30px rgba(0,0,0,0.6)',
            }}
          >
            <h4 style={{ marginTop: 0, marginBottom: 8 }}>Rename schema</h4>
            <p style={{ fontSize: 12, opacity: 0.8, marginBottom: 8 }}>
              Dossier: {renameTarget.dossierId}
            </p>
            <input
              type="text"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              style={{ width: '100%', marginBottom: 12 }}
              autoFocus
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                className="dossier-action-btn"
                onClick={() => {
                  if (renameBusy) return;
                  setRenameTarget(null);
                  setRenameValue('');
                }}
              >
                Cancel
              </button>
              <button
                className="dossier-action-btn"
                disabled={renameBusy || !renameValue.trim()}
                onClick={async () => {
                  if (!renameTarget || !renameValue.trim()) return;
                  setRenameBusy(true);
                  try {
                    await schemaApi.renameSchema(
                      renameTarget.dossierId,
                      renameTarget.schemaId,
                      renameValue.trim(),
                    );
                    setRenameBusy(false);
                    setRenameTarget(null);
                    setRenameValue('');
                    mgr.refresh();
                    try {
                      document.dispatchEvent(new Event('schemas:refresh'));
                    } catch {}
                  } catch (e) {
                    console.error('Failed to rename schema', e);
                    setRenameBusy(false);
                  }
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
};


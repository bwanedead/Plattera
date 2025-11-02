import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { CleanMapBackground } from '../../components/visualization/backgrounds/CleanMapBackground';
import { dossierApi } from '../../services/dossier/dossierApi';
import { listSchemas, getSchema } from '../../services/textToSchemaApi';
import { listGeoreferences, getGeoreference } from '../../services/georeferenceApi';

type DossierSummary = { id: string; title?: string; name?: string };
type SchemaSummary = { dossier_id: string; schema_id: string; saved_at?: string };
type GeorefSummary = { dossier_id: string; georef_id: string; saved_at?: string; bounds?: any };

const ControlBar: React.FC<{
  dossiers: DossierSummary[];
  selectedDossierId: string | null;
  onSelectDossier: (id: string | null) => void;
  schemaSummaries: SchemaSummary[];
  selectedSchemaId: string | null;
  onSelectSchema: (schemaId: string | null) => void;
  georefSummaries: GeorefSummary[];
  selectedGeorefId: string | null;
  onSelectGeoref: (georefId: string | null) => void;
}> = ({
  dossiers,
  selectedDossierId,
  onSelectDossier,
  schemaSummaries,
  selectedSchemaId,
  onSelectSchema,
  georefSummaries,
  selectedGeorefId,
  onSelectGeoref,
}) => {
  return (
    <div className="mapping-controls" style={{ display: 'flex', gap: 12, padding: 12, alignItems: 'center' }}>
      <div>
        <label style={{ display: 'block', fontSize: 12, color: '#666', marginBottom: 4 }}>Dossier</label>
        <select
          value={selectedDossierId || ''}
          onChange={(e) => onSelectDossier(e.target.value || null)}
          style={{ padding: '6px 8px', minWidth: 260 }}
        >
          <option value="">Select dossier…</option>
          {dossiers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title || d.name || d.id}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, color: '#666', marginBottom: 4 }}>Schema</label>
        <select
          value={selectedSchemaId || ''}
          onChange={(e) => onSelectSchema(e.target.value || null)}
          disabled={!selectedDossierId}
          style={{ padding: '6px 8px', minWidth: 280 }}
        >
          <option value="">Select saved schema…</option>
          {schemaSummaries.map((s) => (
            <option key={s.schema_id} value={s.schema_id}>
              {s.schema_id.slice(0, 8)}… {s.saved_at ? `(${new Date(s.saved_at).toLocaleString()})` : ''}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, color: '#666', marginBottom: 4 }}>Saved Plot</label>
        <select
          value={selectedGeorefId || ''}
          onChange={(e) => onSelectGeoref(e.target.value || null)}
          disabled={!selectedDossierId}
          style={{ padding: '6px 8px', minWidth: 280 }}
        >
          <option value="">Select saved plot…</option>
          {georefSummaries.map((g) => (
            <option key={g.georef_id} value={g.georef_id}>
              {g.georef_id.slice(0, 8)}… {g.saved_at ? `(${new Date(g.saved_at).toLocaleString()})` : ''}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};

export default function MappingPage() {
  const router = useRouter();

  // Page-level state
  const [dossiers, setDossiers] = useState<DossierSummary[]>([]);
  const [selectedDossierId, setSelectedDossierId] = useState<string | null>(null);
  const [schemaSummaries, setSchemaSummaries] = useState<SchemaSummary[]>([]);
  const [selectedSchemaId, setSelectedSchemaId] = useState<string | null>(null);
  const [georefSummaries, setGeorefSummaries] = useState<GeorefSummary[]>([]);
  const [selectedGeorefId, setSelectedGeorefId] = useState<string | null>(null);
  const [schemaData, setSchemaData] = useState<any | null>(null);
  const [georefArtifact, setGeorefArtifact] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Parse deep-link query params
  useEffect(() => {
    const q = router.query;
    const dossierId = (q.dossierId as string) || null;
    const schemaId = (q.schemaId as string) || null;
    const georefId = (q.georefId as string) || null;
    if (dossierId) setSelectedDossierId(dossierId);
    if (schemaId) setSelectedSchemaId(schemaId);
    if (georefId) setSelectedGeorefId(georefId);
  }, [router.query]);

  // Load dossiers on mount with light retry/backoff
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setError(null);
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          const ok = await dossierApi.health(800);
          if (!ok) throw new Error('backend not healthy');
          const list = await dossierApi.getDossiers({ limit: 200, offset: 0 });
          if (cancelled) return;
          const summaries = (list || []).map((d: any) => ({ id: String(d.id), title: d.title, name: d.name })) as DossierSummary[];
          setDossiers(summaries);
          break;
        } catch (e: any) {
          if (attempt === 3) {
            if (cancelled) return;
            setError('Failed to load dossiers');
          } else {
            await new Promise(r => setTimeout(r, attempt * 400));
          }
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // When dossier changes, refresh schema/georef summaries
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!selectedDossierId) {
        setSchemaSummaries([]);
        setGeorefSummaries([]);
        setSelectedSchemaId(null);
        setSelectedGeorefId(null);
        setSchemaData(null);
        setGeorefArtifact(null);
        return;
      }
      try {
        const [schemasRes, georefsRes] = await Promise.all([
          listSchemas(selectedDossierId),
          listGeoreferences(selectedDossierId)
        ]);
        if (cancelled) return;
        const schemas = (schemasRes?.schemas || []) as SchemaSummary[];
        const georefs = (georefsRes?.georefs || []) as GeorefSummary[];
        setSchemaSummaries(schemas);
        setGeorefSummaries(georefs);
      } catch (e) {
        if (!cancelled) setError('Failed to load schema/georef lists');
      }
    })();
    return () => { cancelled = true; };
  }, [selectedDossierId]);

  // When selected schema changes, load artifact
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!selectedDossierId || !selectedSchemaId) {
        setSchemaData(null);
        return;
      }
      setLoading(true);
      try {
        const res = await getSchema(selectedDossierId, selectedSchemaId);
        if (cancelled) return;
        const artifact = (res?.artifact || res) as any;
        const enriched = {
          ...(artifact?.structured_data || {}),
          schema_id: artifact?.schema_id || selectedSchemaId,
          metadata: {
            ...((artifact && artifact.metadata) || {}),
            dossierId: String(selectedDossierId)
          }
        };
        setSchemaData(enriched);
      } catch (e) {
        if (!cancelled) setError('Failed to load schema');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedDossierId, selectedSchemaId]);

  // When selected georef changes, load artifact
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!selectedDossierId || !selectedGeorefId) {
        setGeorefArtifact(null);
        return;
      }
      setLoading(true);
      try {
        const res = await getGeoreference(selectedDossierId, selectedGeorefId);
        if (cancelled) return;
        const artifact = res?.artifact || res;
        setGeorefArtifact(artifact);
      } catch (e) {
        if (!cancelled) setError('Failed to load saved plot');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedDossierId, selectedGeorefId]);

  const polygonData = useMemo(() => {
    // If a saved georef is selected, show it as the current polygon
    if (georefArtifact && georefArtifact.geographic_polygon) {
      return georefArtifact;
    }
    return null;
  }, [georefArtifact]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100vh' }}>
      <div style={{ borderBottom: '1px solid #eee' }}>
        <ControlBar
          dossiers={dossiers}
          selectedDossierId={selectedDossierId}
          onSelectDossier={(id) => setSelectedDossierId(id)}
          schemaSummaries={schemaSummaries}
          selectedSchemaId={selectedSchemaId}
          onSelectSchema={(id) => setSelectedSchemaId(id)}
          georefSummaries={georefSummaries}
          selectedGeorefId={selectedGeorefId}
          onSelectGeoref={(id) => setSelectedGeorefId(id)}
        />
      </div>

      {error && (
        <div style={{ padding: 12, color: '#b91c1c', background: '#fee2e2' }}>{error}</div>
      )}

      <div style={{ flex: 1, minHeight: 0 }}>
        <CleanMapBackground
          schemaData={schemaData || undefined}
          polygonData={polygonData || undefined}
          dossierId={selectedDossierId || undefined}
        />
      </div>
    </div>
  );
}



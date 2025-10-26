import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/router';
import { CleanMapBackground } from '../../src/components/visualization/backgrounds/CleanMapBackground';
import Link from 'next/link';
import { dossierApi } from '../../src/services/dossier/dossierApi';
import { listSchemas, getSchema } from '../../src/services/textToSchemaApi';
import { listGeoreferences, getGeoreference } from '../../src/services/georeferenceApi';

type DossierSummary = { id: string; title?: string; name?: string };
type SchemaSummary = { dossier_id: string; schema_id: string; saved_at?: string };
type GeorefSummary = { dossier_id: string; georef_id: string; saved_at?: string; bounds?: any };

const ControlBar: React.FC = () => {
  return (
    <div className="mapping-controls" style={{ height: 48, display: 'flex', alignItems: 'center' }} />
  );
};

export default function MappingPage() {
  const router = useRouter();

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
  const [multiPlots, setMultiPlots] = useState<Record<string, any>>({}); // georef_id -> artifact
  const dossierIdToTitle = useMemo(() => Object.fromEntries(dossiers.map(d => [d.id, d.title || d.name || d.id])), [dossiers]);
  const [showSavedPlots, setShowSavedPlots] = useState<boolean>(false);

  useEffect(() => {
    const q = router.query;
    const dossierId = (q.dossierId as string) || null;
    const schemaId = (q.schemaId as string) || null;
    const georefId = (q.georefId as string) || null;
    if (dossierId) setSelectedDossierId(dossierId);
    if (schemaId) setSelectedSchemaId(schemaId);
    if (georefId) setSelectedGeorefId(georefId);
  }, [router.query]);

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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Aggregate all dossiers' georefs into a single list
      try {
        const all: GeorefSummary[] = [];
        for (const d of dossiers) {
          try {
            const res = await listGeoreferences(d.id);
            const items = (res?.georefs || []) as GeorefSummary[];
            all.push(...items);
          } catch {}
        }
        if (!cancelled) setGeorefSummaries(all);
      } catch (e) {
        if (!cancelled) setError('Failed to load saved plots');
      }
    })();
    return () => { cancelled = true; };
  }, [dossiers]);

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
        setMultiPlots(prev => ({ ...prev, [selectedGeorefId]: artifact }));
      } catch (e) {
        if (!cancelled) setError('Failed to load saved plot');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedDossierId, selectedGeorefId]);

  const polygonData = useMemo(() => {
    if (georefArtifact && georefArtifact.geographic_polygon) {
      return georefArtifact;
    }
    return null;
  }, [georefArtifact]);

  const extraParcels = useMemo(() => Object.values(multiPlots), [multiPlots]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100vh' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #222', background: '#0f172a', color: '#e5e7eb' }}>
        <div style={{ paddingLeft: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link href="/" legacyBehavior>
            <a style={{ textDecoration: 'none', color: '#93c5fd', fontWeight: 600 }}>← Home</a>
          </Link>
          <span style={{ fontWeight: 600 }}>
            {(() => {
              const keys = Object.keys(multiPlots);
              if (keys.length === 1) {
                const g = georefSummaries.find(s => s.georef_id === keys[0]);
                if (g) return dossierIdToTitle[g.dossier_id] || g.dossier_id;
              }
              return 'Mapping';
            })()}
          </span>
        </div>
        <div style={{ paddingRight: 12 }}>
          <button
            onClick={() => setShowSavedPlots(prev => !prev)}
            style={{ background: '#111827', color: '#e5e7eb', border: '1px solid #374151', padding: '6px 10px', borderRadius: 6 }}
          >
            Saved Plots ▾
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 12, color: '#fca5a5', background: '#7f1d1d' }}>{error}</div>
      )}

      <div style={{ flex: 1, minHeight: 0 }}>
        <CleanMapBackground
          schemaData={schemaData || undefined}
          polygonData={polygonData || undefined}
          dossierId={selectedDossierId || undefined}
          extraParcels={extraParcels as any[]}
        />
      </div>

      {/* Multi-plot toggles (checkbox list) */}
      {showSavedPlots && georefSummaries.length > 0 && (
        <div style={{ position: 'absolute', right: 16, top: 56, background: '#0b1220', border: '1px solid #1f2937', borderRadius: 8, padding: 8, maxHeight: '60vh', overflow: 'auto', minWidth: 360, color: '#e5e7eb' }}>
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>Saved Plots</div>
          {georefSummaries.map((g) => {
            const checked = !!multiPlots[g.georef_id];
            return (
              <label key={g.georef_id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0' }}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={async (e) => {
                    if (e.target.checked) {
                      try {
                        const res = await getGeoreference(g.dossier_id, g.georef_id);
                        const artifact = res?.artifact || res;
                        setMultiPlots(prev => ({ ...prev, [g.georef_id]: artifact }));
                        // Load corresponding schema for PLSS overlays
                        const lineageSchemaId = artifact?.lineage?.schema_id || artifact?.schema_id;
                        if (lineageSchemaId) {
                          try {
                            const sres = await getSchema(g.dossier_id, lineageSchemaId);
                            const sart = sres?.artifact || sres;
                            const enriched = {
                              ...(sart?.structured_data || {}),
                              schema_id: sart?.schema_id || lineageSchemaId,
                              metadata: { ...((sart && sart.metadata) || {}), dossierId: String(g.dossier_id) }
                            };
                            setSchemaData(enriched);
                          } catch {}
                        }
                      } catch {}
                    } else {
                      setMultiPlots(prev => {
                        const next = { ...prev };
                        delete next[g.georef_id];
                        return next;
                      });
                    }
                  }}
                />
                <span style={{ fontSize: 12 }}>
                  {(dossierIdToTitle[g.dossier_id] || g.dossier_id)} — {(g.georef_id || '').slice(0, 8)}… {g.saved_at ? new Date(g.saved_at).toLocaleString() : ''}
                </span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}



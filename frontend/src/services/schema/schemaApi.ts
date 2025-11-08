const API_BASE = (typeof process !== 'undefined' && process.env && (process.env.NEXT_PUBLIC_API_BASE as string)) || 'http://localhost:8000';
const API_BASE_URL = `${API_BASE}/api/text-to-schema`;

export interface SchemaListItem {
  dossier_id: string;
  schema_id: string;
  latest_path?: string;
  saved_at?: string;
  dossier_title_snapshot?: string;
}

export interface SchemaArtifact {
  artifact_type: 'schema';
  schema_id: string;
  dossier_id: string;
  saved_at: string;
  model_used?: string;
  original_text?: string;
  structured_data: any;
  metadata?: any;
  lineage?: any;
}

class SchemaApiClient {
  async listSchemas(dossierId: string): Promise<SchemaListItem[]> {
    const url = `${API_BASE_URL}/list?dossier_id=${encodeURIComponent(dossierId)}&t=${Date.now()}`;
    const res = await fetch(url, { cache: 'no-store' as RequestCache });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to list schemas');
    return data?.schemas || [];
  }

  async listAllSchemas(): Promise<SchemaListItem[]> {
    const res = await fetch(`${API_BASE_URL}/list-all?t=${Date.now()}`, { cache: 'no-store' as RequestCache });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to list schemas');
    return data?.schemas || [];
  }

  async getSchema(dossierId: string, schemaId: string): Promise<SchemaArtifact> {
    const url = `${API_BASE_URL}/get?dossier_id=${encodeURIComponent(dossierId)}&schema_id=${encodeURIComponent(schemaId)}&t=${Date.now()}`;
    const res = await fetch(url, { cache: 'no-store' as RequestCache });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to get schema');
    return (data?.artifact || data);
  }

  async deleteSchema(dossierId: string, schemaId: string): Promise<{ status: string; success?: boolean }> {
    const url = `${API_BASE_URL}/delete?dossier_id=${encodeURIComponent(dossierId)}&schema_id=${encodeURIComponent(schemaId)}`;
    const res = await fetch(url, { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to delete schema');
    return data;
  }

  async purgeSchema(dossierId: string, schemaId: string): Promise<{ status: string; purged_georefs?: string[] }> {
    const url = `${API_BASE_URL}/purge-schema`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dossier_id: dossierId, schema_id: schemaId })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to purge schema');
    return data;
  }
}

export const schemaApi = new SchemaApiClient();




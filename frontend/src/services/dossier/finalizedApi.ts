const API_BASE = (typeof process !== 'undefined' && process.env && (process.env.NEXT_PUBLIC_API_BASE as string)) || 'http://localhost:8000';
const API_BASE_URL = `${API_BASE}/api`;

class FinalizedApiClient {

  async listFinalized(): Promise<Array<{ dossier_id: string; title?: string; latest_generated_at?: string; text_length?: number; section_count?: number; has_errors?: boolean }>> {
    const res = await fetch(`${API_BASE_URL}/dossier/finalized/list?t=${Date.now()}`, { cache: 'no-store' as RequestCache });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to list finalized dossiers');
    return data?.finalized || [];
  }

  async getFinal(dossierId: string): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/dossier/final/${encodeURIComponent(dossierId)}?t=${Date.now()}`, { cache: 'no-store' as RequestCache });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to get final snapshot');
    return (data?.data || data);
  }

  async getFinalLive(dossierId: string): Promise<any> {
    const res = await fetch(`${API_BASE_URL}/dossier/final/live/${encodeURIComponent(dossierId)}?t=${Date.now()}`, { cache: 'no-store' as RequestCache });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to get live final');
    return (data?.data || data);
  }
}

export const finalizedApi = new FinalizedApiClient();





class FinalizedApiClient {
  private baseUrl = 'http://localhost:8000/api';

  async listFinalized(): Promise<Array<{ dossier_id: string; title?: string; latest_generated_at?: string; text_length?: number; section_count?: number; has_errors?: boolean }>> {
    const res = await fetch(`${this.baseUrl}/dossier/finalized/list`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to list finalized dossiers');
    return data?.finalized || [];
  }

  async getFinal(dossierId: string): Promise<any> {
    const res = await fetch(`${this.baseUrl}/dossier/final/${encodeURIComponent(dossierId)}`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || 'Failed to get final snapshot');
    return (data?.data || data);
  }
}

export const finalizedApi = new FinalizedApiClient();





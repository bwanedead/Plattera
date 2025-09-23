// ============================================================================
// TEXT API CLIENT - FETCH DRAFT CONTENT BY ID
// ============================================================================

const BASE_URL = 'http://localhost:8000/api';

export class TextApiError extends Error {
  constructor(message: string, public statusCode?: number, public details?: any) {
    super(message);
    this.name = 'TextApiError';
  }
}

export const textApi = {
  async getDraftText(transcriptionId: string, draftId: string, dossierId?: string): Promise<string> {
    const url = `${BASE_URL}/dossier-management/drafts/${encodeURIComponent(draftId)}${dossierId ? `?dossier_id=${encodeURIComponent(dossierId)}` : ''}`;
    console.info(`textApi.getDraftText -> draftId=${draftId} dossierId=${dossierId} url=${url}`);
    const json = await this.getDraftJson(transcriptionId, draftId, dossierId);
    try {
      if (draftId.endsWith('_consensus_llm') && json && typeof json === 'object' && 'text' in json) {
        return String((json as any).text || '');
      }
      // Common JSON schema path
      if (json && typeof json === 'object') {
        const maybeSections = (json as any).sections;
        if (Array.isArray(maybeSections)) {
          const text = maybeSections.map((s: any) => s?.body ?? '').join('\n\n').trim();
          return text;
        }
      }
      return typeof json === 'string' ? json : JSON.stringify(json);
    } catch (e) {
      throw new TextApiError('Failed to parse draft text', undefined, e);
    }
  },

  async getDraftJson(transcriptionId: string, draftId: string, dossierId?: string): Promise<any> {
    const primary = `${BASE_URL}/dossier-management/drafts/${encodeURIComponent(draftId)}${dossierId ? `?dossier_id=${encodeURIComponent(dossierId)}` : ''}`;
    console.info(`textApi.getDraftJson -> draftId=${draftId} dossierId=${dossierId} url=${primary}`);
    const res = await fetch(primary);
    const data = await res.json().catch(() => null);
    const summary = data && typeof data === 'object' ? `{keys:[${Object.keys(data).slice(0,6).join(',')}], hasData:${'data' in data}}` : String(typeof data);
    console.info(`textApi.getDraftJson <- draftId=${draftId} dossierId=${dossierId} type=${typeof data} summary=${summary}`);
    if (!res.ok) {
      throw new TextApiError(`HTTP ${res.status} loading draft`, res.status, data);
    }
    return data?.data ?? data;
  }
};



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
  async getDraftText(transcriptionId: string, draftId: string): Promise<string> {
    const url = `${BASE_URL}/transcriptions/${encodeURIComponent(transcriptionId)}/drafts/${encodeURIComponent(draftId)}/text`;
    try {
      const res = await fetch(url);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new TextApiError(data?.error || `HTTP ${res.status}`, res.status, data);
      }
      return data?.text ?? '';
    } catch (err: any) {
      // Graceful fallback to avoid breaking viewer
      console.warn('textApi.getDraftText failed; returning empty text fallback', err);
      return '';
    }
  }
};



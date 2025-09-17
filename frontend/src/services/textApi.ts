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
    // Prefer the specific draft JSON so each draft shows its own content
    const primary = `${BASE_URL}/dossier-management/drafts/${encodeURIComponent(draftId)}`;
    const fallbacks = [
      `${BASE_URL}/dossier-views/transcription/${encodeURIComponent(transcriptionId)}/text`,
    ];
    const tryFetch = async (url: string) => {
      const res = await fetch(url);
      const ok = res.ok;
      const contentType = res.headers.get('content-type') || '';
      let text = '';
      if (contentType.includes('application/json')) {
        const data = await res.json().catch(() => ({}));
        if (!ok) {
          throw new TextApiError(data?.error || `HTTP ${res.status}`, res.status, data);
        }
        // Our API returns { success, draft_id, data: payload }
        const payload = (data && typeof data === 'object' && 'data' in data) ? (data as any).data : data;

        // Special handling for LLM consensus drafts
        if (payload?.type === 'llm_consensus') {
          console.log('🔍 Detected LLM consensus draft, extracting text field', { hasText: !!payload?.text });
          if (payload?.text) {
            return payload.text;
          }
        }

        text = payload?.text ?? '';
        if (text) return text;
        // If JSON without text and we fetched the draft JSON, try deriving text from sections
        const sections = payload?.sections || data?.sections;
        if (Array.isArray(sections)) {
          const parts: string[] = [];
          for (const s of sections) {
            const header = s?.header;
            const body = s?.body;
            if (header) parts.push(`[${header}]`);
            parts.push(body || '');
            parts.push('');
          }
          return parts.join('\n');
        }
        const raw = await res.clone().text().catch(() => '');
        if (raw) return raw;
        return '';
      } else {
        // Plain text or other types - this might be the fallback endpoint
        const raw = await res.text().catch(() => '');
        if (!ok) {
          throw new TextApiError(raw || `HTTP ${res.status}`, res.status, raw);
        }
        console.log('📄 Got plain text response, length:', raw.length);
        return raw;
      }
    };
    try {
      console.log('🔄 Trying primary URL:', primary);
      return await tryFetch(primary);
    } catch (err: any) {
      console.warn('⚠️ Primary URL failed, trying fallbacks', err);
      for (const fb of fallbacks) {
        try {
          console.log('🔄 Trying fallback URL:', fb);
          return await tryFetch(fb);
        } catch (fbErr) {
          console.warn('⚠️ Fallback URL failed:', fb, fbErr);
        }
      }
      console.warn('textApi.getDraftText failed; returning empty text fallback', err);
      return '';
    }
  },

  async getDraftJson(draftId: string): Promise<string> {
    console.log('🛰️ textApi.getDraftJson request:', { draftId });
    const url = `${BASE_URL}/dossier-management/drafts/${encodeURIComponent(draftId)}`;
    try {
      const res = await fetch(url);
      if (!res.ok) {
        const msg = await res.text().catch(() => '');
        throw new TextApiError(msg || `HTTP ${res.status}`, res.status, msg);
      }
      const data = await res.json().catch(() => ({}));
      // Return the prettified raw JSON of the draft
      const payload = data?.data ?? data;
      console.log('🛰️ textApi.getDraftJson response:', { draftId, hasData: !!payload, keys: payload ? Object.keys(payload) : [] });
      return JSON.stringify(payload, null, 2);
    } catch (err) {
      console.warn('textApi.getDraftJson failed', err);
      return '';
    }
  }
};



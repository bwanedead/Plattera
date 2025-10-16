// ============================================================================
// DOSSIER API CLIENT - MODULAR SERVICE LAYER
// ============================================================================
// Handles all API communication for dossier management
// Designed for maximum modularity and error resilience
// ============================================================================

import { Dossier, Segment, Run, Draft, DossierApiResponse, CreateDossierData, UpdateDossierData, CreateSegmentData, BulkAction } from '../../types/dossier';

class DossierApiError extends Error {
  constructor(message: string, public statusCode?: number, public details?: any) {
    super(message);
    this.name = 'DossierApiError';
  }
}

class DossierApiClient {
  private baseUrl = 'http://localhost:8000/api';
  private retryAttempts = 5; // trimmed for quicker feedback
  private retryDelay = 400;  // slightly lower base delay
  private warmedUp = false;  // mark after first success

  // ============================================================================
  // CORE CRUD OPERATIONS
  // ============================================================================

  async getDossiers(params?: { limit?: number; offset?: number }): Promise<Dossier[]> {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const endpoint = qs.toString() ? `/dossier-management/list?${qs.toString()}` : '/dossier-management/list';
    const response = await this.request<any>(endpoint);
    return response.dossiers || [];
  }

  async getDossier(dossierId: string): Promise<Dossier> {
    const response = await this.request<any>(`/dossier-management/${dossierId}/details`);
    if (!response.dossier) {
      throw new DossierApiError('Dossier not found');
    }
    return response.dossier;
  }

  async createDossier(data: CreateDossierData): Promise<Dossier> {
    console.log('📡 API: Creating dossier with payload:', data);
    console.log('📡 API: Full request details:', {
      url: '/dossier-management/create',
      method: 'POST',
      body: JSON.stringify(data),
      contentType: 'application/json'
    });
    const response = await this.request<any>('/dossier-management/create', {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.dossier) {
      throw new DossierApiError('Failed to create dossier');
    }
    // Notify other views to refresh (e.g., Image-to-Text workspace Control Panel)
    try {
      const newId = response.dossier.id;
      document.dispatchEvent(new Event('dossiers:refresh'));
      if (newId) {
        document.dispatchEvent(new CustomEvent('dossier:refreshOne', { detail: { dossierId: newId } }));
      }
    } catch {}
    return response.dossier;
  }

  async updateDossier(dossierId: string, data: UpdateDossierData): Promise<Dossier> {
    console.log('📡 updateDossier: Calling API with data:', data);
    const response = await this.request<any>(`/dossier-management/${dossierId}/update`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
    console.log('📡 updateDossier: API response:', response);
    if (!response.dossier) {
      console.error('❌ updateDossier: No dossier in response:', response);
      throw new DossierApiError('Failed to update dossier');
    }
    console.log('✅ updateDossier: Returning dossier:', response.dossier);
    return response.dossier;
  }

  async deleteDossier(dossierId: string): Promise<void> {
    await this.request(`/dossier-management/${dossierId}/delete`, {
      method: 'DELETE',
      timeoutMs: 60000
    });
  }

  // ============================================================================
  // SEGMENT OPERATIONS
  // ============================================================================

  async createSegment(dossierId: string, data: CreateSegmentData): Promise<Segment> {
    const response = await this.request<any>(`/dossier-management/${dossierId}/segments`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.data) {
      throw new DossierApiError('Failed to create segment');
    }
    return response.data;
  }

  async updateSegment(segmentId: string, data: Partial<Segment>): Promise<Segment> {
    const response = await this.request<any>(`/dossier-management/segments/${segmentId}`, {
      method: 'PUT',
      body: JSON.stringify({ name: data.name })
    });
    if (!response.data) {
      // API returns only success; treat as OK if success true
      if (!response.success) {
        throw new DossierApiError('Failed to update segment');
      }
      return { ...(data as any), id: segmentId } as any;
    }
    return response.data;
  }

  async deleteSegment(segmentId: string): Promise<void> {
    try {
      await this.request(`/dossier-management/segments/${segmentId}`, {
        method: 'DELETE'
      });
    } catch (e: any) {
      // If the segment doesn't exist anymore (404), refresh and return cleanly
      if (e?.statusCode === 404) {
        try { await this.getDossiers(); } catch {}
        return;
      }
      throw e;
    }
  }

  // ============================================================================
  // ASSOCIATION OPERATIONS
  // ============================================================================

  async associateTranscription(dossierId: string, transcriptionId: string, segmentId?: string): Promise<void> {
    await this.request('/transcription-association/add', {
      method: 'POST',
      body: JSON.stringify({
        dossierId,
        transcriptionId,
        segmentId
      })
    });
  }

  async moveTranscription(transcriptionId: string, targetDossierId: string, targetSegmentId?: string): Promise<void> {
    await this.request('/transcription-association/move', {
      method: 'POST',
      body: JSON.stringify({
        transcriptionId,
        targetDossierId,
        targetSegmentId
      })
    });
  }

  async removeTranscription(transcriptionId: string): Promise<void> {
    await this.request('/transcription-association/remove', {
      method: 'DELETE',
      body: JSON.stringify({ transcriptionId })
    });
  }

  // ============================================================================
  // BULK OPERATIONS
  // ============================================================================

  async bulkAction(action: BulkAction): Promise<void> {
    await this.request('/dossier-management/bulk', {
      method: 'POST',
      body: JSON.stringify(action),
      timeoutMs: 120000
    });
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  private async request<T>(endpoint: string, options: (RequestInit & { timeoutMs?: number }) = {}): Promise<DossierApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultOptions: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
      },
      ...options
    };

    let lastError: Error | null = null;

    const maxAttempts = this.warmedUp ? this.retryAttempts : 4;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        // Add a bounded timeout on all attempts to avoid indefinite hangs
        const controller = new AbortController();
        const attemptTimeoutMs = options.timeoutMs ?? (this.warmedUp ? 12000 : 6000);
        let timeoutHandle: number | undefined;
        if (attemptTimeoutMs) {
          timeoutHandle = window.setTimeout(() => controller.abort(), attemptTimeoutMs);
        }
        const response = await fetch(url, { ...defaultOptions, signal: controller.signal } as RequestInit);
        if (timeoutHandle) window.clearTimeout(timeoutHandle);
        const data: DossierApiResponse<T> = await response.json();

        if (!response.ok) {
          throw new DossierApiError(
            data.error || `HTTP ${response.status}`,
            response.status,
            data
          );
        }
        this.warmedUp = true;
        return data;
      } catch (error) {
        lastError = error as Error;

        if (attempt < maxAttempts && this.isRetryableError(error)) {
          const exp = Math.pow(2, attempt - 1);
          const jitter = Math.floor(Math.random() * 200);
          const cap = this.warmedUp ? 12000 : 8000;
          const delayMs = Math.min(cap, this.retryDelay * exp + jitter);
          await this.delay(delayMs);
          continue;
        }

        break;
      }
    }

    throw lastError || new DossierApiError('Unknown error occurred');
  }

  // Fast health probe (1s timeout) to gate initial contact
  async health(timeoutMs = 1000): Promise<boolean> {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}/health`, { signal: controller.signal } as RequestInit);
      if (!res.ok) return false;
      await res.json().catch(() => ({}));
      this.warmedUp = true;
      return true;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timer);
    }
  }

  private isRetryableError(error: any): boolean {
    // Retry on network errors, 5xx server errors
    if (error instanceof DossierApiError) {
      return !!(error.statusCode && error.statusCode >= 500);
    }

    // Retry on network/fetch errors and aborts/timeouts
    if (error?.name === 'AbortError') return true;
    return error.name === 'TypeError' || error.name === 'NetworkError';
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ============================================================================
  // RUN INITIALIZATION
  // ============================================================================

  async initRun(payload: {
    dossierId?: string;
    fileName?: string;
    transcriptionId?: string;
    model: string;
    extractionMode: string;
    redundancyCount: number;
    autoLlmConsensus: boolean;
    llmConsensusModel?: string;
    consensusStrategy?: string;
  }): Promise<{ success: boolean; dossier_id: string; transcription_id: string; data: any }> {
    const response = await this.request<any>('/dossier-runs/init-run', {
      method: 'POST',
      body: JSON.stringify({
        dossier_id: payload.dossierId,
        file_name: payload.fileName,
        transcription_id: payload.transcriptionId,
        model: payload.model,
        extraction_mode: payload.extractionMode,
        redundancy_count: payload.redundancyCount,
        auto_llm_consensus: payload.autoLlmConsensus,
        llm_consensus_model: payload.llmConsensusModel,
        consensus_strategy: payload.consensusStrategy
      })
    });

    if (!response.success) {
      throw new DossierApiError('Failed to initialize run');
    }

    return response;
  }

  // Reconcile stuck runs by asking the backend to mark runs completed
  async reconcileRuns(dossierId: string): Promise<{ success: boolean; dossier_id: string; reconciled: number }>{
    const response = await this.request<any>(`/dossier-runs/reconcile/${encodeURIComponent(dossierId)}`, {
      method: 'POST'
    });
    return response as any;
  }

  // ============================================================================
  // FUTURE EXTENSIBILITY HOOKS
  // ============================================================================

  // Placeholder for AI consensus features
  async generateConsensus(dossierId: string): Promise<any> {
    // Future implementation for AI consensus generation
    throw new DossierApiError('AI consensus not yet implemented');
  }

  // Placeholder for auto-naming features
  async suggestNames(dossierId: string): Promise<any> {
    // Future implementation for AI-powered naming suggestions
    throw new DossierApiError('Auto-naming not yet implemented');
  }

  // ============================================================================
  // FINAL SELECTION (per-segment/run)
  // ============================================================================

  // New registry-backed finals endpoints (segment-scoped)
  async getAllSegmentFinals(dossierId: string): Promise<Record<string, { transcription_id: string; draft_id: string; set_at?: string; set_by?: string }>> {
    const res = await fetch(`${this.baseUrl}/dossier/${encodeURIComponent(dossierId)}/finals`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to get finals map', res.status, data);
    }
    return (data?.segments || {}) as any;
  }

  async getSegmentFinal(dossierId: string, segmentId: string): Promise<{ transcription_id: string; draft_id: string } | null> {
    const res = await fetch(`${this.baseUrl}/dossier/${encodeURIComponent(dossierId)}/segments/${encodeURIComponent(segmentId)}/final`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // Treat as unset
      return null;
    }
    return data?.final ?? null;
  }

  async setSegmentFinal(dossierId: string, segmentId: string, transcriptionId: string, draftId: string, setBy?: string): Promise<{ success: boolean; final: any }> {
    const res = await fetch(`${this.baseUrl}/dossier/${encodeURIComponent(dossierId)}/segments/${encodeURIComponent(segmentId)}/final`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcription_id: transcriptionId, draft_id: draftId, set_by: setBy })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to set segment final', res.status, data);
    }
    try {
      document.dispatchEvent(new Event('dossiers:refresh'));
      document.dispatchEvent(new CustomEvent('dossier:refreshOne', { detail: { dossierId } }));
      document.dispatchEvent(new CustomEvent('dossier:final-set', { detail: { dossierId, segmentId, transcriptionId, draftId } }));
    } catch {}
    return data;
  }

  async clearSegmentFinal(dossierId: string, segmentId: string): Promise<{ success: boolean; removed: boolean }> {
    const res = await fetch(`${this.baseUrl}/dossier/${encodeURIComponent(dossierId)}/segments/${encodeURIComponent(segmentId)}/final`, { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to clear segment final', res.status, data);
    }
    try {
      document.dispatchEvent(new Event('dossiers:refresh'));
      document.dispatchEvent(new CustomEvent('dossier:refreshOne', { detail: { dossierId } }));
      document.dispatchEvent(new CustomEvent('dossier:final-set', { detail: { dossierId, segmentId, transcriptionId: null, draftId: null } }));
    } catch {}
    return data;
  }

  async setFinalSelection(dossierId: string, transcriptionId: string, draftId: string): Promise<{ success: boolean; draft_id: string }> {
    const form = new FormData();
    form.append('dossier_id', dossierId);
    form.append('transcription_id', transcriptionId);
    form.append('draft_id', draftId);
    const res = await fetch(`${this.baseUrl}/dossier/final-selection/set`, { method: 'POST', body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to set final selection', res.status, data);
    }
    // Nudge caches and refresh dossier UI quickly
    try {
      document.dispatchEvent(new Event('dossiers:refresh'));
      document.dispatchEvent(new CustomEvent('dossier:refreshOne', { detail: { dossierId } }));
      document.dispatchEvent(new CustomEvent('dossier:final-set', { detail: { dossierId, transcriptionId, draftId } }));
    } catch {}
    return data;
  }

  async clearFinalSelection(dossierId: string, transcriptionId: string): Promise<{ success: boolean }> {
    const form = new FormData();
    form.append('dossier_id', dossierId);
    form.append('transcription_id', transcriptionId);
    const res = await fetch(`${this.baseUrl}/dossier/final-selection/clear`, { method: 'POST', body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to clear final selection', res.status, data);
    }
    try { document.dispatchEvent(new CustomEvent('dossier:final-set', { detail: { dossierId, transcriptionId, draftId: null } })); } catch {}
    return data;
  }

  async getFinalSelection(dossierId: string, transcriptionId: string): Promise<string | null> {
    const url = `${this.baseUrl}/dossier/final-selection/get?dossier_id=${encodeURIComponent(dossierId)}&transcription_id=${encodeURIComponent(transcriptionId)}`;
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to get final selection', res.status, data);
    }
    return data?.draft_id ?? null;
  }

  async finalizeDossier(dossierId: string): Promise<any> {
    const res = await fetch(`${this.baseUrl}/dossier/finalize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dossier_id: dossierId })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new DossierApiError(data?.detail || 'Failed to finalize dossier', res.status, data);
    }
    try { document.dispatchEvent(new CustomEvent('dossier:finalized', { detail: { dossierId } })); } catch {}
    return data;
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

export const dossierApi = new DossierApiClient();
export { DossierApiError };

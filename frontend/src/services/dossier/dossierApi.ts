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
  private retryAttempts = 8; // more resilient during backend startup
  private retryDelay = 500;  // base delay (ms) for exponential backoff

  // ============================================================================
  // CORE CRUD OPERATIONS
  // ============================================================================

  async getDossiers(): Promise<Dossier[]> {
    const t0 = Date.now();
    const response = await this.request<any>('/dossier-management/list');
    const count = (response.dossiers || []).length;
    console.info(`DM_API_LIST ok count=${count} dt_ms=${Date.now()-t0}`);
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
      method: 'DELETE'
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
      body: JSON.stringify(action)
    });
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<DossierApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultOptions: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
      },
      ...options
    };

    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
      try {
        const response = await fetch(url, defaultOptions);
        const data: DossierApiResponse<T> = await response.json();

        if (!response.ok) {
          throw new DossierApiError(
            data.error || `HTTP ${response.status}`,
            response.status,
            data
          );
        }

        return data;
      } catch (error) {
        lastError = error as Error;

        if (attempt < this.retryAttempts && this.isRetryableError(error)) {
          // Exponential backoff with jitter
          const exp = Math.pow(2, attempt - 1);
          const jitter = Math.floor(Math.random() * 250);
          const delayMs = Math.min(15000, this.retryDelay * exp + jitter);
          await this.delay(delayMs);
          continue;
        }

        break;
      }
    }

    throw lastError || new DossierApiError('Unknown error occurred');
  }

  private isRetryableError(error: any): boolean {
    // Retry on network errors, 5xx server errors
    if (error instanceof DossierApiError) {
      return error.statusCode && error.statusCode >= 500;
    }

    // Retry on network/fetch errors
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
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

export const dossierApi = new DossierApiClient();
export { DossierApiError };

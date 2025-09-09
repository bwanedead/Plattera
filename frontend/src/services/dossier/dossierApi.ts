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
  private retryAttempts = 3;
  private retryDelay = 1000;

  // ============================================================================
  // CORE CRUD OPERATIONS
  // ============================================================================

  async getDossiers(): Promise<Dossier[]> {
    const response = await this.request<any>('/dossier-management/list');
    console.log('📡 getDossiers response:', response);
    // Backend returns { success, dossiers, total_count } directly
    return response.dossiers || [];
  }

  async getDossier(dossierId: string): Promise<Dossier> {
    const response = await this.request<any>(`/dossier-management/${dossierId}`);
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
    const response = await this.request<any>(`/dossier-management/${dossierId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
    if (!response.dossier) {
      throw new DossierApiError('Failed to update dossier');
    }
    return response.dossier;
  }

  async deleteDossier(dossierId: string): Promise<void> {
    await this.request(`/dossier-management/${dossierId}`, {
      method: 'DELETE'
    });
  }

  // ============================================================================
  // SEGMENT OPERATIONS
  // ============================================================================

  async createSegment(dossierId: string, data: CreateSegmentData): Promise<Segment> {
    const response = await this.request<Segment>(`/dossier-management/${dossierId}/segments`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!response.data) {
      throw new DossierApiError('Failed to create segment');
    }
    return response.data;
  }

  async updateSegment(segmentId: string, data: Partial<Segment>): Promise<Segment> {
    const response = await this.request<Segment>(`/dossier-management/segments/${segmentId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
    if (!response.data) {
      throw new DossierApiError('Failed to update segment');
    }
    return response.data;
  }

  async deleteSegment(segmentId: string): Promise<void> {
    await this.request(`/dossier-management/segments/${segmentId}`, {
      method: 'DELETE'
    });
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
          await this.delay(this.retryDelay * attempt);
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

// ============================================================================
// RETRIEVAL API CLIENT - INDEX MAINTENANCE
// ============================================================================
// Handles all API communication for RAG index maintenance
// ============================================================================

import {
  BootstrapIndexRequest,
  BootstrapIndexResponse,
  DiagnoseResponse,
  ExecuteIndexRequest,
  ExecuteIndexResponse,
  IndexJob,
  PoolIdentifier
} from '../../types/retrieval';

class RetrievalApiError extends Error {
  constructor(message: string, public statusCode?: number, public details?: any) {
    super(message);
    this.name = 'RetrievalApiError';
  }
}

class RetrievalApiClient {
  private baseUrl = 'http://localhost:8000/api';

  // ============================================================================
  // DIAGNOSE & EXECUTE
  // ============================================================================

  async diagnoseIndex(
    poolIdentifier: PoolIdentifier,
    includeSlices = false,
    limitSlices = 200,
    dossierId?: string
  ): Promise<DiagnoseResponse> {
    const qs = new URLSearchParams({
      pool_identifier: poolIdentifier,
      include_slices: String(includeSlices),
      limit_slices: String(limitSlices)
    });
    if (dossierId) {
      qs.set('dossier_id', dossierId);
    }

    const response = await this.request<DiagnoseResponse>(`/index/diagnose?${qs.toString()}`);
    return response;
  }

  async executeIndex(request: ExecuteIndexRequest): Promise<ExecuteIndexResponse> {
    const response = await this.request<ExecuteIndexResponse>('/index/execute', {
      method: 'POST',
      body: JSON.stringify(request)
    });
    return response;
  }

  async bootstrapIndex(request: BootstrapIndexRequest = {}): Promise<BootstrapIndexResponse> {
    const response = await this.request<BootstrapIndexResponse>('/index/bootstrap', {
      method: 'POST',
      body: JSON.stringify(request)
    });
    return response;
  }

  // ============================================================================
  // JOB MANAGEMENT
  // ============================================================================

  async getIndexJob(jobId: string, limitResults = 200): Promise<IndexJob> {
    const qs = new URLSearchParams({
      limit_results: String(limitResults)
    });

    const response = await this.request<IndexJob>(`/index/jobs/${jobId}?${qs.toString()}`);
    return response;
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultOptions: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
      },
      ...options
    };

    const response = await fetch(url, defaultOptions);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new RetrievalApiError(
        data.detail || data.error || `HTTP ${response.status}`,
        response.status,
        data
      );
    }

    return data as T;
  }
}

// ============================================================================
// SINGLETON EXPORT
// ============================================================================

export const indexMaintenanceApi = new RetrievalApiClient();
export { RetrievalApiError };

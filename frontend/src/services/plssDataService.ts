/**
 * PLSS Data Service - Pure data operations
 * Handles all PLSS data management without UI concerns
 */

export type PLSSDataStatus = 'unknown' | 'checking' | 'missing' | 'downloading' | 'ready' | 'error';

export interface PLSSDataState {
  status: PLSSDataStatus;
  state: string | null;
  error: string | null;
  progress: string | null;
}

export class PLSSDataService {
  private apiBase = '/api/mapping';

  async checkDataStatus(state: string): Promise<{ available: boolean; error?: string }> {
    try {
      const response = await fetch(`${this.apiBase}/ensure-plss/${state}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      
      const data = await response.json();
      return { available: data.data_status === 'ready' };
    } catch (error) {
      return { 
        available: false, 
        error: error instanceof Error ? error.message : 'Unknown error' 
      };
    }
  }

  async ensureData(state: string): Promise<{ success: boolean; error?: string }> {
    try {
      const response = await fetch(`${this.apiBase}/ensure-plss/${state}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }
      return { success: true };
    } catch (error) {
      return { 
        success: false, 
        error: error instanceof Error ? error.message : 'Unknown error' 
      };
    }
  }

  async extractStateFromSchema(schemaData: any): Promise<string | null> {
    try {
      // Use the new backend endpoint to extract PLSS info
      const response = await fetch(`${this.apiBase}/extract-plss-info`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(schemaData)
      });
      
      if (!response.ok) {
        console.error('PLSS extraction failed:', response.status);
        return null;
      }
      
      const result = await response.json();
      if (result.success && result.plss_info?.state) {
        return result.plss_info.state;
      }
      
      return null;
    } catch (error) {
      console.error('PLSS extraction error:', error);
      return null;
    }
  }

  // Keep the old method for backward compatibility
  extractStateFromPolygon(polygonResult: any): string | null {
    // State extraction logic (extracted from business logic)
    const origin = polygonResult?.origin;
    if (origin?.plss_data?.state) return origin.plss_data.state;
    
    const descriptions = polygonResult?.schema_data?.descriptions;
    if (descriptions) {
      for (const desc of descriptions) {
        if (desc.plss?.state) return desc.plss.state;
      }
    }
    
    return null;
  }
}

export const plssDataService = new PLSSDataService(); 
/**
 * PLSS Data Service - Core Data Operations
 *
 * Handles all PLSS data management without UI concerns.
 * Pure business logic for data fetching, validation, and state extraction.
 *
 * Domain: PLSS (Public Land Survey System)
 * Responsibility: Data operations only - no UI state management
 */

// Note: we explicitly track a "canceled" status in the frontend hook so that
// UX and logs can distinguish "never downloaded" from "user canceled an
// in-flight job". This is important for restart semantics and diagnosis.
export type PLSSDataStatus =
  | 'unknown'
  | 'checking'
  | 'missing'
  | 'downloading'
  | 'ready'
  | 'error'
  | 'canceled';

export interface PLSSDataState {
  status: PLSSDataStatus;
  state: string | null;
  error: string | null;
  progress: string | null;
}

export interface PLSSDataCheckResult {
  available: boolean;
  error?: string;
}

export interface PLSSDataDownloadResult {
  success: boolean;
  error?: string;
}

/**
 * Core PLSS Data Service
 * 
 * Provides methods for:
 * - Checking data availability
 * - Downloading PLSS data
 * - Extracting state information from various data sources
 */
export class PLSSDataService {
  private readonly apiBase = 'http://localhost:8000/api/mapping';

  /**
   * Check if PLSS data is available locally for a given state
   */
  async checkDataStatus(state: string): Promise<PLSSDataCheckResult> {
    try {
      const response = await fetch(`${this.apiBase}/check-plss/${state}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      return { available: data.available, error: data.error };
    } catch (error) {
      console.error('❌ PLSS Data Check Error:', error);
      return { 
        available: false, 
        error: error instanceof Error ? error.message : 'Unknown error' 
      };
    }
  }

  /**
   * Download PLSS data for a given state
   */
  async downloadData(state: string, plssHint?: {
    township_number: number;
    township_direction: string;
    range_number: number;
    range_direction: string;
  }): Promise<PLSSDataDownloadResult> {
    try {
      const response = await fetch(`${this.apiBase}/download-plss/${state}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(plssHint ? { plss_hint: plssHint } : {})
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      return { success: data.success, error: data.error };
    } catch (error) {
      console.error('❌ PLSS Data Download Error:', error);
      return { 
        success: false, 
        error: error instanceof Error ? error.message : 'Unknown error' 
      };
    }
  }

  /** Start background download for state */
  async startBackgroundDownload(state: string): Promise<{ success: boolean; error?: string }> {
    try {
      const res = await fetch(`${this.apiBase}/download-plss/${state}/start`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e: any) {
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }

  /** Poll progress for current download */
  async getDownloadProgress(state: string): Promise<{ success: boolean; stage?: string; overall?: { downloaded: number; total: number; percent: number }; error?: string }>{
    try {
      const res = await fetch(`${this.apiBase}/download-plss/${state}/progress`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e: any) {
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }

  /** Request cancel of current download */
  async cancelDownload(state: string): Promise<{ success: boolean; error?: string }>{
    try {
      const res = await fetch(`${this.apiBase}/download-plss/${state}/cancel`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e: any) {
      return { success: false, error: e?.message || 'Unknown error' };
    }
  }

  /** Check if download/parquet building is currently active */
  async checkDownloadActive(state: string): Promise<{ active: boolean; stage?: string; error?: string }> {
    try {
      const res = await fetch(`${this.apiBase}/download-plss/${state}/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      
      return {
        active: data.download_active || false,
        stage: data.current_stage,
        error: data.error
      };
    } catch (e: any) {
      return { 
        active: false, // Default to false if we can't check
        error: e?.message || 'Unknown error' 
      };
    }
  }

  /**
   * Extract state information from schema data
   * 
   * Looks for state in various schema locations:
   * - PLSS description objects
   * - Location metadata
   * - Fallback text analysis
   */
  async extractStateFromSchema(schemaData: any): Promise<string | null> {
    try {
      console.log('🔍 PLSS: Extracting state from schema');
      
      // Primary: Look in structured PLSS data
      if (schemaData?.descriptions) {
        for (const desc of schemaData.descriptions) {
          const state = desc?.plss?.state || 
                       desc?.plss?.location?.state ||
                       desc?.plss_description?.state;
          
          if (state) {
            console.log('✅ PLSS: Found state in structured data:', state);
            return state;
          }
        }
      }
      
      // Fallback: Text analysis for common states
      const stateMap = this.getStateDetectionMap();
      const textToCheck = JSON.stringify(schemaData).toLowerCase();
      
      for (const [keyword, state] of stateMap) {
        if (textToCheck.includes(keyword)) {
          console.log('✅ PLSS: Found state via text analysis:', state);
          return state;
        }
      }
      
      console.log('❌ PLSS: No state found in schema');
      return null;
      
    } catch (error) {
      console.error('❌ PLSS: State extraction error:', error);
      return null;
    }
  }

  /**
   * Extract state from polygon processing result (backward compatibility)
   */
  extractStateFromPolygon(polygonResult: any): string | null {
    try {
      // Check origin data
      const origin = polygonResult?.origin;
      if (origin?.plss_data?.state) {
        return origin.plss_data.state;
      }
      
      // Check schema descriptions
      const descriptions = polygonResult?.schema_data?.descriptions;
      if (descriptions) {
        for (const desc of descriptions) {
          if (desc.plss?.state) {
            return desc.plss.state;
          }
        }
      }
      
      return null;
    } catch (error) {
      console.error('❌ PLSS: Error extracting state from polygon:', error);
      return null;
    }
  }

  /**
   * Get map of keywords to state names for text detection
   * 
   * Easily extensible for new states
   */
  private getStateDetectionMap(): Map<string, string> {
    return new Map([
      ['wyoming', 'Wyoming'],
      ['colorado', 'Colorado'],
      ['utah', 'Utah'],
      ['montana', 'Montana'],
      ['idaho', 'Idaho'],
      ['nevada', 'Nevada'],
      ['arizona', 'Arizona'],
      ['new mexico', 'New Mexico'],
      ['north dakota', 'North Dakota'],
      ['south dakota', 'South Dakota'],
      ['nebraska', 'Nebraska'],
      ['kansas', 'Kansas'],
      ['oklahoma', 'Oklahoma'],
      ['texas', 'Texas'],
      // Add more as needed
    ]);
  }

  /**
   * Legacy method for backward compatibility
   * @deprecated Use checkDataStatus instead
   */
  async ensureData(state: string): Promise<PLSSDataDownloadResult> {
    console.warn('⚠️ PLSSDataService.ensureData is deprecated. Use checkDataStatus + downloadData instead.');
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
}

// Singleton instance for app-wide use
export const plssDataService = new PLSSDataService();
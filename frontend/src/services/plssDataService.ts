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
  private apiBase = 'http://localhost:8000/api/mapping'; // Fix: Use direct backend URL

  async checkDataStatus(state: string): Promise<{ available: boolean; error?: string }> {
    try {
      console.log(`🔍 Checking if ${state} PLSS data exists locally...`);
      
      // Use the new check-only endpoint
      const response = await fetch(`${this.apiBase}/check-plss/${state}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      
      const data = await response.json();
      
      console.log(`📁 ${state} PLSS data:`, data.data_available ? 'Available' : 'Missing');
      
      return { 
        available: data.success && data.data_available === true 
      };
    } catch (error) {
      console.error(`❌ Failed to check ${state} PLSS data:`, error);
      return { 
        available: false, 
        error: error instanceof Error ? error.message : 'Unknown error' 
      };
    }
  }

  async downloadData(state: string): Promise<{ success: boolean; error?: string }> {
    try {
      console.log(`⬇️ Starting download of ${state} PLSS data...`);
      
      // Use the new download endpoint (POST request)
      const response = await fetch(`${this.apiBase}/download-plss/${state}`, {
        method: 'POST'
      });
      
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      
      const data = await response.json();
      
      console.log(`✅ ${state} PLSS data download completed`);
      
      return { success: data.success };
    } catch (error) {
      console.error(`❌ Failed to download ${state} PLSS data:`, error);
      return { 
        success: false, 
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
      console.log('🔍 Extracting state from schema:', schemaData);
      
      // Simple direct extraction - look for state in PLSS description
      if (schemaData?.descriptions) {
        for (const desc of schemaData.descriptions) {
          // Look in different possible locations for state
          const state = desc?.plss?.state || 
                       desc?.plss?.location?.state ||
                       desc?.plss_description?.state;
          
          if (state) {
            console.log('✅ Found state:', state);
            return state;
          }
        }
      }
      
      // Fallback: look for "Wyoming" in the raw text
      const textToCheck = JSON.stringify(schemaData).toLowerCase();
      if (textToCheck.includes('wyoming')) return 'Wyoming';
      if (textToCheck.includes('colorado')) return 'Colorado';
      if (textToCheck.includes('utah')) return 'Utah';
      // Add more states as needed
      
      console.log('❌ No state found in schema');
      return null;
      
    } catch (error) {
      console.error('❌ State extraction error:', error);
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
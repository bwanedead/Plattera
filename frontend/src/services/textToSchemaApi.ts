/**
 * Text-to-Schema API Service
 * Handles all API calls related to text-to-schema conversion
 */

export interface TextToSchemaRequest {
  text: string;
  parcel_id?: string;
  model?: string;
}

export interface TextToSchemaResponse {
  status: string;
  structured_data?: any;
  original_text?: string;
  model_used?: string;
  service_type?: string;
  tokens_used?: number;
  confidence_score?: number;
  validation_warnings?: string[];
  metadata?: any;
}

export interface SchemaModelsResponse {
  status: string;
  models?: Record<string, any>;
}

// Prefer environment-configured API base, fallback to localhost dev
const API_BASE = (typeof process !== 'undefined' && process.env && (process.env.NEXT_PUBLIC_API_BASE as string)) || 'http://localhost:8000';
const API_BASE_URL = `${API_BASE}/api/text-to-schema`;

/**
 * Convert text to structured parcel schema
 */
export const convertTextToSchema = async (request: TextToSchemaRequest): Promise<TextToSchemaResponse> => {
  const attempt = async () => {
    const response = await fetch(`${API_BASE_URL}/convert`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request)
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  };
  try {
    console.log('📝 Converting text to schema:', { textLength: request.text.length, model: request.model });
    try {
      const data = await attempt();
      console.log('📊 Schema conversion response:', data);
      return data;
    } catch (e) {
      await new Promise(r => setTimeout(r, 300));
      const data = await attempt();
      console.log('📊 Schema conversion response (retry):', data);
      return data;
    }
  } catch (error) {
    console.error('❌ Schema conversion error:', error);
    // Optional retry against same-origin if BASE is external and first call failed due to CORS/network
    try {
      const fallbackUrl = `/api/text-to-schema/convert`;
      const res = await fetch(fallbackUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      return data;
    } catch (_) {
      throw error;
    }
  }
};

/**
 * Get available models for text-to-schema conversion
 */
export const getTextToSchemaModels = async (): Promise<SchemaModelsResponse> => {
  try {
    const response = await fetch(`${API_BASE_URL}/models`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.warn('Failed to load text-to-schema models:', error);
    // Try same-origin fallback
    try {
      const res = await fetch(`http://localhost:8000/api/text-to-schema/models`);
      if (res.ok) {
        return await res.json();
      }
    } catch {}
    // Return fallback models
    return {
      status: 'success',
      models: {
        "gpt-5-mini": { name: "GPT-5 Mini", provider: "openai" },
        "gpt-5": { name: "GPT-5", provider: "openai" },
        "gpt-4o": { name: "GPT-4o", provider: "openai" }
      }
    };
  }
};

/**
 * Get the parcel schema template
 */
export const getParcelSchema = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/schema`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Failed to load parcel schema:', error);
    throw error;
  }
}; 
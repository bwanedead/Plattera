import { EnhancementSettings, ProcessingResult, RedundancySettings, ConsensusSettings, AlignmentDraft, AlignmentResult } from '../types/imageProcessing';

// --- API Calls for Image Processing Feature ---

export const processFilesAPI = async (files: File[], model: string, mode: string, enhancementSettings: EnhancementSettings, redundancySettings: RedundancySettings, consensusSettings: ConsensusSettings, dossierId?: string, segmentId?: string, transcriptionId?: string): Promise<ProcessingResult[]> => {
  console.log(`Processing ${files.length} files with model: ${model} and mode: ${mode}`);
  
  const results: ProcessingResult[] = [];
  
  for (const file of files) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('content_type', 'image-to-text');
      formData.append('extraction_mode', mode);
      formData.append('model', model);
      formData.append('cleanup_after', 'true');
      
      // Add enhancement settings
      formData.append('contrast', enhancementSettings.contrast.toString());
      formData.append('sharpness', enhancementSettings.sharpness.toString());
      formData.append('brightness', enhancementSettings.brightness.toString());
      formData.append('color', enhancementSettings.color.toString());
      
      // Add redundancy setting
      formData.append('redundancy', redundancySettings.enabled ? redundancySettings.count.toString() : '1');
      
      // Consensus strategy (only relevant when redundancy is enabled)
      if (redundancySettings.enabled) {
        formData.append('consensus_strategy', redundancySettings.consensusStrategy);
      }

      // LLM consensus settings
      formData.append('auto_llm_consensus', consensusSettings.enabled ? 'true' : 'false');
      formData.append('llm_consensus_model', consensusSettings.model);

      // Add dossier ID if provided
      console.log(`📁 Dossier ID parameter received: ${dossierId}`);
      console.log(`📁 Dossier ID type: ${typeof dossierId}`);
      console.log(`📁 Dossier ID truthy check: ${!!dossierId}`);

      if (dossierId) {
        formData.append('dossier_id', dossierId);
        console.log(`📁 Including dossier_id in FormData: ${dossierId}`);
        console.log(`📁 FormData dossier_id value: ${formData.get('dossier_id')}`);
      } else {
        console.log('📁 No dossier_id provided - will auto-create');
      }

      if (segmentId) {
        formData.append('segment_id', segmentId);
        console.log(`📁 Including segment_id in FormData: ${segmentId}`);
      }

      if (transcriptionId) {
        formData.append('transcription_id', transcriptionId);
        console.log(`📁 Including transcription_id in FormData: ${transcriptionId}`);
      }

      // Use dossier-specific endpoint if dossier_id is provided for progressive saving
      const endpoint = dossierId ? 'http://localhost:8000/api/dossier/process' : 'http://localhost:8000/api/process';
      console.log(`🔗 Using endpoint: ${endpoint} (progressive saving: ${!!dossierId})`);

      const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      console.log("API response data:", data);

      if (data.status === 'success') {
        results.push({
          input: file.name,
          status: 'completed' as const,
          result: {
            extracted_text: data.extracted_text,
            metadata: { ...data.metadata }
          }
        });
      } else {
        results.push({
          input: file.name,
          status: 'error' as const,
          result: null,
          error: data.error || 'Processing failed'
        });
      }
    } catch (error) {
      results.push({
        input: file.name,
        status: 'error' as const,
        result: null,
        error: error instanceof Error ? error.message : 'Unknown error'
      });
    }
  }
  
  return results;
};

export const fetchModelsAPI = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/models');
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    if (data.status === 'success' && data.models) {
      return data.models;
    } else {
      throw new Error(data.error || 'Invalid response format');
    }
  } catch (error) {
    console.warn('Failed to load models from API, using defaults:', error);
    // Fallback to default models
    return {
      "gpt-4o": { name: "GPT-4o", provider: "openai" },
      "o3": { name: "o3", provider: "openai" },
      "gpt-4": { name: "GPT-4", provider: "openai" },
    };
  }
};

// --- LLM Consensus Retry API ---
export const retryLlmConsensusAPI = async (params: {
  drafts: string[];
  model: string; // gpt-5-consensus | gpt-5-mini-consensus | gpt-5-nano-consensus
  maxTokens?: number;
  temperature?: number;
  dossierId?: string;
  transcriptionId?: string;
}): Promise<{ success: boolean; consensus_text?: string; consensus_title?: string; error?: string }> => {
  const response = await fetch('http://localhost:8000/api/llm-consensus/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      drafts: params.drafts,
      model: params.model,
      max_tokens: params.maxTokens ?? 6000,
      temperature: params.temperature ?? 0.2
    })
  });
  const data = await response.json();
  return data;
};

// --- Alignment Engine API ---

export const alignDraftsAPI = async (
  drafts: AlignmentDraft[],
  consensusStrategy: string = 'highest_confidence',
  opts?: { transcriptionId?: string; consensusDraftId?: string; dossierId?: string }
): Promise<AlignmentResult> => {
  try {
    console.log(`Aligning ${drafts.length} drafts with strategy: ${consensusStrategy}`);
    
    const attempt = async () => {
      const response = await fetch('http://localhost:8000/api/alignment/align-drafts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          drafts,
          generate_visualization: true,
          consensus_strategy: consensusStrategy,
          transcription_id: opts?.transcriptionId,
          dossier_id: opts?.dossierId,
          consensus_draft_id: opts?.consensusDraftId
        })
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return response.json();
    };

    let data;
    try {
      data = await attempt();
    } catch (e) {
      // brief backoff and retry once
      await new Promise(r => setTimeout(r, 300));
      data = await attempt();
    }
    console.log("Alignment API response:", data);

    return data;
  } catch (error) {
    console.error('Alignment API error:', error);
    // Fix the property name in the fallback object
    return {
      success: false,
      processing_time: 0,
      summary: {
        total_positions_analyzed: 0,  // ← Fix: Change from total_positions to total_positions_analyzed
        total_differences_found: 0,   // ← Fix: Change from total_differences to total_differences_found
        average_confidence_score: 0,  // ← Fix: Change from average_confidence to average_confidence_score
        quality_assessment: 'Failed',
        confidence_distribution: {     // ← Fix: Use the correct structure
          high: 0,
          medium: 0,
          low: 0
        }
      },
      error: error instanceof Error ? error.message : 'Unknown alignment error'
    };
  }
}; 

// Update the API call to use the new endpoint

export const selectFinalDraftAPI = async (
  redundancyAnalysis: any,
  selectedDraft: number | 'consensus' | 'best',
  alignmentResult?: any,
  editedDraftContent?: string,
  editedFromDraft?: number | 'consensus' | 'best' | null  // Add null here
): Promise<any> => {
  console.log('🎯 Calling selectFinalDraftAPI with:', {
    selectedDraft,
    hasAlignmentResult: !!alignmentResult,
    hasEditedContent: !!editedDraftContent,
    editedFromDraft
  });

  const formData = new FormData();
  formData.append('redundancy_analysis', JSON.stringify(redundancyAnalysis));
  formData.append('selected_draft', selectedDraft.toString());
  
  if (alignmentResult) {
    formData.append('alignment_result', JSON.stringify(alignmentResult));
  }
  if (editedDraftContent) {
    formData.append('edited_draft_content', editedDraftContent);
  }
  if (editedFromDraft !== null && editedFromDraft !== undefined) {  // Check for null explicitly
    formData.append('edited_from_draft', editedFromDraft.toString());
  }

  console.log('📤 Sending FormData with keys:', Array.from(formData.keys()));

  const response = await fetch('http://localhost:8000/api/final-draft/select-final-draft', {
    method: 'POST',
    body: formData
  });

  console.log(' Response status:', response.status, response.statusText);

  if (!response.ok) {
    const errorText = await response.text();
    console.error('❌ API Error Response:', errorText);
    throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  console.log('✅ API Response:', data);
  return data;
}; 

// --- Dossier Edit Save API ---
export const saveDossierEditAPI = async (params: {
  dossierId: string;
  transcriptionId: string;
  editedText?: string;
  editedSections?: Array<{ id: number | string; body: string }>;
}): Promise<{ success: boolean; raw_head: string }> => {
  const formData = new FormData();
  formData.append('dossier_id', params.dossierId);
  formData.append('transcription_id', params.transcriptionId);
  if (params.editedSections && params.editedSections.length > 0) {
    formData.append('edited_sections', JSON.stringify(params.editedSections));
  } else {
    formData.append('edited_text', params.editedText || '');
  }

  const response = await fetch('http://localhost:8000/api/dossier/edits/save', {
    method: 'POST',
    body: formData
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`HTTP ${response.status}: ${errorText}`);
  }
  return response.json();
};
/**
 * Draft Storage Utility
 * Manages saving and loading of transcription drafts to/from localStorage
 * for testing alignment functionality without API calls
 */

export interface SavedDraft {
  draft_id: string;
  model_name: string;
  content: string;
  saved_at: string;
  metadata?: any;
}

export interface DraftSession {
  id: string;
  input: string;
  status: 'completed';
  result: {
    extracted_text: string;
    model_used: string;
    service_type: string;
    tokens_used: number;
    confidence_score: number;
    metadata: any;
  };
}

const STORAGE_KEY = 'plattera_saved_drafts';

/**
 * Get all saved drafts from localStorage
 */
export const getSavedDrafts = (): SavedDraft[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch (error) {
    console.error('Error loading saved drafts:', error);
    return [];
  }
};

/**
 * Save a new draft to localStorage
 */
export const saveDraft = (
  content: string, 
  modelName: string, 
  metadata?: any
): SavedDraft => {
  const draft: SavedDraft = {
    draft_id: `draft-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    model_name: modelName,
    content: content,
    saved_at: new Date().toISOString(),
    metadata: metadata
  };

  try {
    const existingDrafts = getSavedDrafts();
    const updatedDrafts = [...existingDrafts, draft];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedDrafts));
    return draft;
  } catch (error) {
    console.error('Error saving draft:', error);
    throw new Error('Failed to save draft to localStorage');
  }
};

/**
 * Delete a draft by ID
 */
export const deleteDraft = (draftId: string): void => {
  try {
    const existingDrafts = getSavedDrafts();
    const updatedDrafts = existingDrafts.filter(draft => draft.draft_id !== draftId);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedDrafts));
  } catch (error) {
    console.error('Error deleting draft:', error);
    throw new Error('Failed to delete draft');
  }
};

/**
 * Convert saved drafts to session results format for seamless integration
 */
export const createSessionFromDrafts = (
  selectedDrafts: SavedDraft[], 
  baseFilename: string = 'imported-drafts'
): DraftSession[] => {
  return selectedDrafts.map((draft, index) => ({
    id: `imported-${Date.now()}-${index}`,
    input: `${baseFilename} (${draft.model_name})`,
    status: 'completed' as const,
    result: {
      extracted_text: draft.content,
      model_used: draft.model_name,
      service_type: 'imported-draft',
      tokens_used: 0,
      confidence_score: 1.0,
      metadata: {
        ...draft.metadata,
        imported_at: new Date().toISOString(),
        original_draft_id: draft.draft_id,
        saved_at: draft.saved_at,
        is_imported_draft: true
      }
    }
  }));
};

/**
 * Get total count of saved drafts
 */
export const getDraftCount = (): number => {
  return getSavedDrafts().length;
};

/**
 * Clear all saved drafts (utility function)
 */
export const clearAllDrafts = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Error clearing drafts:', error);
    throw new Error('Failed to clear drafts');
  }
}; 
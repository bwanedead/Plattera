/**
 * DraftLoader Component
 * Modal interface for selecting and loading previously saved transcription drafts
 * Integrates seamlessly with existing session management
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  getSavedDrafts,
  SavedDraft,
  createSessionFromDrafts,
  DraftSession,
  deleteDraft
} from '../../utils/draftStorage';

interface DraftLoaderProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadDrafts: (results: DraftSession[]) => void;
}

export const DraftLoader: React.FC<DraftLoaderProps> = ({
  isOpen,
  onClose,
  onLoadDrafts
}) => {
  const [savedDrafts, setSavedDrafts] = useState<SavedDraft[]>([]);
  const [selectedDrafts, setSelectedDrafts] = useState<Set<string>>(new Set());
  const [loadCount, setLoadCount] = useState(3);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  // Load drafts when modal opens
  useEffect(() => {
    if (isOpen) {
      loadDrafts();
    }
  }, [isOpen]);

  // Auto-select drafts when count changes
  useEffect(() => {
    if (savedDrafts.length > 0) {
      const autoSelect = new Set(
        savedDrafts
          .slice(0, Math.min(loadCount, savedDrafts.length))
          .map(d => d.draft_id)
      );
      setSelectedDrafts(autoSelect);
    }
  }, [savedDrafts, loadCount]);

  const loadDrafts = useCallback(() => {
    const drafts = getSavedDrafts();
    setSavedDrafts(drafts);
  }, []);

  const handleDraftToggle = useCallback((draftId: string) => {
    setSelectedDrafts(prev => {
      const newSelected = new Set(prev);
      if (newSelected.has(draftId)) {
        newSelected.delete(draftId);
      } else {
        newSelected.add(draftId);
      }
      return newSelected;
    });
  }, []);

  const handleLoadSelected = useCallback(() => {
    const draftsToLoad = savedDrafts.filter(draft =>
      selectedDrafts.has(draft.draft_id)
    );

    if (draftsToLoad.length === 0) {
      alert('Please select at least one draft to load');
      return;
    }

    const results = createSessionFromDrafts(draftsToLoad);
    onLoadDrafts(results);
    onClose();
  }, [savedDrafts, selectedDrafts, onLoadDrafts, onClose]);

  const handleDeleteDraft = useCallback(async (draftId: string, event: React.MouseEvent) => {
    event.stopPropagation();

    if (!confirm('Are you sure you want to delete this draft?')) {
      return;
    }

    setIsDeleting(draftId);
    try {
      deleteDraft(draftId);
      loadDrafts(); // Refresh the list

      // Remove from selection if it was selected
      setSelectedDrafts(prev => {
        const newSelected = new Set(prev);
        newSelected.delete(draftId);
        return newSelected;
      });
    } catch (error) {
      alert('Failed to delete draft: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      setIsDeleting(null);
    }
  }, [loadDrafts]);

  const formatDate = useCallback((dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    });
  }, []);

  const getContentPreview = useCallback((content: string) => {
    try {
      // If it's JSON, try to extract a readable preview
      const parsed = JSON.parse(content);
      if (parsed.title) return parsed.title;
      if (parsed.sections?.[0]?.body) {
        return parsed.sections[0].body.substring(0, 100) + '...';
      }
      if (typeof parsed === 'string') {
        return parsed.substring(0, 100) + '...';
      }
      return JSON.stringify(parsed).substring(0, 100) + '...';
    } catch {
      // If not JSON, just return a preview
      return content.substring(0, 100) + '...';
    }
  }, []);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content draft-loader-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Load Saved Drafts</h3>
          <button onClick={onClose} className="close-button">✕</button>
        </div>

        <div className="modal-body">
          {savedDrafts.length === 0 ? (
            <div className="no-drafts">
              <div className="no-drafts-icon">📭</div>
              <h4>No Saved Drafts</h4>
              <p>
                Save some transcription drafts first to use this feature.<br/>
                Process documents and use the "Save Draft" button in the JSON tab.
              </p>
            </div>
          ) : (
            <>
              <div className="load-count-section">
                <label htmlFor="load-count">
                  Number of drafts to load (max {savedDrafts.length}):
                </label>
                <input
                  id="load-count"
                  type="number"
                  min="1"
                  max={savedDrafts.length}
                  value={loadCount}
                  onChange={(e) => setLoadCount(
                    Math.max(1, Math.min(savedDrafts.length, parseInt(e.target.value) || 1))
                  )}
                  className="load-count-input"
                />
              </div>

              <div className="drafts-list">
                <div className="drafts-header">
                  <span className="selected-count">
                    Selected: {selectedDrafts.size} of {savedDrafts.length} drafts
                  </span>
                  <small className="drafts-hint">
                    Select drafts to load for alignment testing
                  </small>
                </div>

                <div className="drafts-container">
                  {savedDrafts.map((draft) => (
                    <div
                      key={draft.draft_id}
                      className={`draft-item ${selectedDrafts.has(draft.draft_id) ? 'selected' : ''}`}
                      onClick={() => handleDraftToggle(draft.draft_id)}
                    >
                      <input
                        type="checkbox"
                        checked={selectedDrafts.has(draft.draft_id)}
                        onChange={() => handleDraftToggle(draft.draft_id)}
                        className="draft-checkbox"
                        onClick={(e) => e.stopPropagation()}
                      />

                      <div className="draft-info">
                        <div className="draft-header-row">
                          <div className="draft-model">{draft.model_name}</div>
                          <div className="draft-actions">
                            <button
                              className="delete-draft-button"
                              onClick={(e) => handleDeleteDraft(draft.draft_id, e)}
                              disabled={isDeleting === draft.draft_id}
                              title="Delete this draft"
                            >
                              {isDeleting === draft.draft_id ? '⏳' : '🗑️'}
                            </button>
                          </div>
                        </div>
                        <div className="draft-preview">{getContentPreview(draft.content)}</div>
                        <div className="draft-date">{formatDate(draft.saved_at)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="modal-actions">
                <button onClick={onClose} className="cancel-button">
                  Cancel
                </button>
                <button
                  onClick={handleLoadSelected}
                  disabled={selectedDrafts.size === 0}
                  className="load-button"
                >
                  Load {selectedDrafts.size} Draft{selectedDrafts.size !== 1 ? 's' : ''}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}; 
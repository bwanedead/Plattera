// ============================================================================
// CREATE DOSSIER MODAL COMPONENT
// ============================================================================
// Modal for creating new dossiers with name and description
// ============================================================================

import React, { useState, useCallback, useEffect } from 'react';

interface CreateDossierModalProps {
  onCreate: (data: { title: string; description?: string }) => void;
  onCancel: () => void;
}

export const CreateDossierModal: React.FC<CreateDossierModalProps> = ({
  onCreate,
  onCancel
}) => {
  // ============================================================================
  // LOCAL STATE
  // ============================================================================

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // ============================================================================
  // COMPUTED VALUES
  // ============================================================================

  const canSubmit = name.trim().length > 0 && !isSubmitting;

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();

    if (!canSubmit) return;

    setIsSubmitting(true);

    try {
      console.log('📝 Creating dossier with data:', {
        title: name.trim(),
        description: description.trim() || undefined
      });
      await onCreate({
        title: name.trim(),
        description: description.trim() || undefined
      });
    } catch (error) {
      console.error('Failed to create dossier:', error);
      setIsSubmitting(false);
    }
  }, [name, description, canSubmit, onCreate]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onCancel();
    }
  }, [onCancel]);

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Focus name input when modal opens
  useEffect(() => {
    const nameInput = document.getElementById('dossier-name-input');
    if (nameInput) {
      nameInput.focus();
    }
  }, []);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        {/* Modal header */}
        <div className="modal-header">
          <h2 className="modal-title">Create New Dossier</h2>
          <button
            className="modal-close-btn"
            onClick={() => onCancel()}
            title="Close"
            disabled={isSubmitting}
          >
            ✕
          </button>
        </div>

        {/* Modal body */}
        <form className="modal-body" onSubmit={handleSubmit} onKeyDown={handleKeyDown}>
          {/* Name field */}
          <div className="form-group">
            <label htmlFor="dossier-name-input" className="form-label">
              Dossier Name *
            </label>
            <input
              id="dossier-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Legal Document - 2024-09-09"
              className="form-input"
              required
              maxLength={100}
            />
            <div className="form-hint">
              {name.length}/100 characters
            </div>
          </div>

          {/* Description field */}
          <div className="form-group">
            <label htmlFor="dossier-description-input" className="form-label">
              Description (Optional)
            </label>
            <textarea
              id="dossier-description-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this dossier..."
              className="form-textarea"
              rows={3}
              maxLength={500}
            />
            <div className="form-hint">
              {description.length}/500 characters
            </div>
          </div>

          {/* Auto-generated name suggestion */}
          {name.trim() === '' && (
            <div className="name-suggestion">
              <span className="suggestion-icon">💡</span>
              <span className="suggestion-text">
                Auto-generated: "Document - {new Date().toLocaleDateString()}"
              </span>
            </div>
          )}
        </form>

        {/* Modal footer */}
        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </button>

          <button
            type="submit"
            className="btn-primary"
            onSubmit={handleSubmit}
            disabled={!canSubmit}
          >
            {isSubmitting ? 'Creating...' : 'Create Dossier'}
          </button>
        </div>
      </div>
    </div>
  );
};

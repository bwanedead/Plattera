// ============================================================================
// DOSSIER SEARCH COMPONENT
// ============================================================================
// Provides search and filtering capabilities for the dossier list
// ============================================================================

import React, { useState, useCallback } from 'react';
import { SortOption } from '../../types/dossier';

interface DossierSearchProps {
  query: string;
  onQueryChange: (query: string) => void;
  sortBy: SortOption;
  onSortChange: (sortBy: SortOption) => void;
  isFocused: boolean;
  onFocusChange: (focused: boolean) => void;
}

export const DossierSearch: React.FC<DossierSearchProps> = ({
  query,
  onQueryChange,
  sortBy,
  onSortChange,
  isFocused,
  onFocusChange
}) => {
  // ============================================================================
  // LOCAL STATE
  // ============================================================================

  const [localQuery, setLocalQuery] = useState(query);

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  const handleQueryChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newQuery = e.target.value;
    setLocalQuery(newQuery);
    onQueryChange(newQuery);
  }, [onQueryChange]);

  const handleClearSearch = useCallback(() => {
    setLocalQuery('');
    onQueryChange('');
  }, [onQueryChange]);

  const handleSortChange = useCallback((newSortBy: SortOption) => {
    onSortChange(newSortBy);
  }, [onSortChange]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="dossier-search">
      {/* Search input */}
      <div className="search-input-container">
        <input
          type="text"
          value={localQuery}
          onChange={handleQueryChange}
          onFocus={() => onFocusChange(true)}
          onBlur={() => onFocusChange(false)}
          placeholder="Search dossiers, segments, runs..."
          className="dossier-search-input"
        />
        {localQuery && (
          <button
            className="search-clear-btn"
            onClick={handleClearSearch}
            title="Clear search"
          >
            Clear
          </button>
        )}
      </div>

      {/* Sort options */}
      <div className="sort-options">
        <label className="sort-label">Sort by:</label>
        <select
          value={sortBy}
          onChange={(e) => handleSortChange(e.target.value as SortOption)}
          className="sort-select"
        >
          <option value="name">Name</option>
          <option value="date">Date Modified</option>
          <option value="size">Size</option>
          <option value="activity">Last Activity</option>
        </select>
      </div>
    </div>
  );
};

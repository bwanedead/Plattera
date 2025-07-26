import React from 'react';
import { CopyButton } from '../CopyButton';

interface SchemaResultsTabsProps {
  selectedTab: 'original' | 'json' | 'fields';
  onTabChange: (tab: 'original' | 'json' | 'fields') => void;
  hasResults: boolean;
}

export const SchemaResultsTabs: React.FC<SchemaResultsTabsProps> = ({
  selectedTab,
  onTabChange,
  hasResults
}) => {
  return (
    <div className="schema-tabs">
      <button 
        className={`tab ${selectedTab === 'original' ? 'active' : ''}`}
        onClick={() => onTabChange('original')}
      >
        📄 Original Text
      </button>
      <button 
        className={`tab ${selectedTab === 'json' ? 'active' : ''}`}
        onClick={() => onTabChange('json')}
        disabled={!hasResults}
      >
        📋 JSON Schema
      </button>
      <button 
        className={`tab ${selectedTab === 'fields' ? 'active' : ''}`}
        onClick={() => onTabChange('fields')}
        disabled={!hasResults}
      >
        🗂️ Field View
      </button>
    </div>
  );
}; 
import React from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

interface AlignmentTableViewerProps {
  alignmentResult: AlignmentResult;
  onClose: () => void;
}

// Helper function to apply individual token formatting without changing position structure
const formatIndividualToken = (token: string, position: number, allTokens: string[]): string => {
  if (!token || token === '-') {
    return token;
  }
  
  // Get context tokens
  const prevToken = position > 0 ? allTokens[position - 1] : '';
  const nextToken = position < allTokens.length - 1 ? allTokens[position + 1] : '';
  const nextNextToken = position < allTokens.length - 2 ? allTokens[position + 2] : '';
  
  // Apply individual token formatting (never combine tokens)
  
  // Format degrees: number + number + direction = first number gets °
  if (token.match(/^\d+$/) && nextToken && nextToken.match(/^\d+$/) && 
      nextNextToken && nextNextToken.toLowerCase().match(/^[nsew]$/)) {
    return `${token}°`;
  }
  
  // Format minutes: previous was number, current is number, next is direction = current gets '
  if (token.match(/^\d+$/) && prevToken && prevToken.match(/^\d+$/) && 
      nextToken && nextToken.toLowerCase().match(/^[nsew]$/)) {
    return `${token}'`;
  }
  
  // Format directions: after numbers, add period
  if (token.toLowerCase().match(/^[nsew]$/) && prevToken && prevToken.match(/^\d+$/)) {
    return `${token.toUpperCase()}.`;
  }
  
  // Format large numbers with commas
  if (token.match(/^\d{4,}$/)) {
    return token.replace(/(\d)(?=(\d{3})+$)/g, '$1,');
  }
  
  // Return original token (no combining)
  return token;
};

// Helper function to get properly formatted token at position using original formatted tokens
const getTokenAtPosition = (seq: any, position: number): string => {
  // Use original_formatted_tokens if available (these preserve exact formatting from source)
  // Otherwise fall back to original_tokens (normalized) or tokens as last resort
  const formattedTokens = seq.original_formatted_tokens;
  const originalTokens = seq.original_tokens || seq.tokens || [];
  
  if (formattedTokens && formattedTokens[position] !== undefined) {
    // Use the exact formatting from the original text (e.g., "68°", "30'", "E.")
    return formattedTokens[position] || '';
  }
  
  // Fallback to old pattern matching if original formatted tokens not available
  const token = originalTokens[position];
  if (!token) {
    return '';
  }
  
  // Apply individual formatting without changing position structure
  return formatIndividualToken(token, position, originalTokens);
};

export const AlignmentTableViewer: React.FC<AlignmentTableViewerProps> = ({
  alignmentResult,
  onClose,
}) => {
  if (!alignmentResult?.success) {
    return null;
  }

  const alignmentBlocks = alignmentResult.alignment_results?.blocks;

  if (!alignmentBlocks || Object.keys(alignmentBlocks).length === 0) {
    return (
      <div className="alignment-table-modal-backdrop">
        <div className="alignment-table-modal">
          <div className="alignment-table-header">
            <h3>Raw Alignment Table</h3>
            <button className="panel-close-btn" onClick={onClose}>×</button>
          </div>
          <div className="alignment-table-container">
            <p>No alignment data available to display.</p>
          </div>
        </div>
      </div>
    );
  }

  const blockIds = Object.keys(alignmentBlocks).sort(); // Sort to ensure consistent order

  const handleExport = (format: 'copy' | 'download') => {
    const csvRows: string[] = [];
    
    // Assume all blocks have the same drafts and get headers from the first one.
    const firstBlock = alignmentBlocks[blockIds[0]];
    const draftIds = firstBlock.aligned_sequences.map((seq: any) => seq.draft_id);
    const headers = ['Position', ...draftIds];
    
    // Process each block into the CSV
    blockIds.forEach(blockId => {
      const blockData = alignmentBlocks[blockId];
      const { aligned_sequences } = blockData;
      // ALWAYS use original_tokens length for position structure
      const alignmentLength = aligned_sequences[0]?.original_tokens?.length || aligned_sequences[0]?.tokens.length || 0;

      // Add a header for the block
      csvRows.push(''); // Spacer row
      csvRows.push(`"${blockId.replace(/_/g, ' ')}"`);
      csvRows.push(headers.join(','));

      // Add the data rows for this block
      for (let i = 0; i < alignmentLength; i++) {
        const rowData = [i.toString()];
        aligned_sequences.forEach((seq: any) => {
          const token = getTokenAtPosition(seq, i);
          // Sanitize token for CSV (handle quotes)
          const sanitizedToken = `"${String(token).replace(/"/g, '""')}"`;
          rowData.push(sanitizedToken);
        });
        csvRows.push(rowData.join(','));
      }
    });

    const csvContent = csvRows.join('\n');

    if (format === 'copy') {
      navigator.clipboard.writeText(csvContent).then(() => {
        alert('Alignment data copied to clipboard!');
      });
    } else {
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', 'alignment_export.csv');
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  return (
    <div className="alignment-table-modal-backdrop">
      <div className="alignment-table-modal">
        <div className="alignment-table-header">
          <h3>Raw Alignment Table</h3>
          <div className="header-actions">
            <button className="export-btn" onClick={() => handleExport('copy')}>Copy as CSV</button>
            <button className="export-btn" onClick={() => handleExport('download')}>Download CSV</button>
            <button className="panel-close-btn" onClick={onClose}>×</button>
          </div>
        </div>
        <div className="alignment-table-container">
          {blockIds.map(blockId => {
            const blockData = alignmentBlocks[blockId];
            const { aligned_sequences } = blockData;
            const draftIds = aligned_sequences.map((seq: any) => seq.draft_id);
            // ALWAYS use original_tokens length for position structure
            const alignmentLength = aligned_sequences[0]?.original_tokens?.length || aligned_sequences[0]?.tokens.length || 0;

            const hasDifference = (position: number): boolean => {
              const tokensAtPosition = new Set();
              for (const seq of aligned_sequences) {
                const token = getTokenAtPosition(seq, position);
                if (token !== '-') {
                  tokensAtPosition.add(token);
                }
              }
              return tokensAtPosition.size > 1;
            };

            return (
              <div key={blockId} className="table-block-wrapper">
                <h4 className="table-block-header">Alignment for: {blockId.replace('_', ' ')}</h4>
                <table>
                  <thead>
                    <tr>
                      <th>Position</th>
                      {draftIds.map((id: string) => <th key={id}>{id.replace('_', ' ')}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: alignmentLength }).map((_, index) => (
                      <tr key={index} className={hasDifference(index) ? 'difference-row' : ''}>
                        <td>{index}</td>
                        {aligned_sequences.map((seq: any) => {
                          const token = getTokenAtPosition(seq, index);
                          return (
                            <td key={seq.draft_id} className={token === '-' ? 'gap-cell' : ''}>
                              {token}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}; 
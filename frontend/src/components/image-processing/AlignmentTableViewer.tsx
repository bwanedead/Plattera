import React from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

interface AlignmentTableViewerProps {
  alignmentResult: AlignmentResult;
  onClose: () => void;
}

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
      const alignmentLength = aligned_sequences[0]?.tokens.length || 0;

      // Add a header for the block
      csvRows.push(''); // Spacer row
      csvRows.push(`"${blockId.replace(/_/g, ' ')}"`);
      csvRows.push(headers.join(','));

      // Add the data rows for this block
      for (let i = 0; i < alignmentLength; i++) {
        const rowData = [i.toString()];
        aligned_sequences.forEach((seq: any) => {
          const token = seq.tokens[i] || '';
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
            const alignmentLength = aligned_sequences[0]?.tokens.length || 0;

            const hasDifference = (position: number): boolean => {
              const tokensAtPosition = new Set();
              for (const seq of aligned_sequences) {
                const token = seq.tokens[position];
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
                      {draftIds.map(id => <th key={id}>{id.replace('_', ' ')}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: alignmentLength }).map((_, index) => (
                      <tr key={index} className={hasDifference(index) ? 'difference-row' : ''}>
                        <td>{index}</td>
                        {aligned_sequences.map((seq: any) => (
                          <td key={seq.draft_id} className={seq.tokens[index] === '-' ? 'gap-cell' : ''}>
                            {seq.tokens[index]}
                          </td>
                        ))}
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
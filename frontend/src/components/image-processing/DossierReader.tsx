// ============================================================================
// DOSSIER READER - Reading interface for stitched dossier content
// ============================================================================
// Displays dossier-level stitched content with segment boundaries and source attribution
// Shows each segment's best draft sequentially for a continuous reading experience
// ============================================================================

// TypeScript module declaration to ensure proper exports

import React, { useState, useEffect } from 'react';
import { Dossier, Segment, Run, Draft } from '../../types/dossier';
import { latestRunBestDraftPolicy } from '../../services/dossier/stitchingPolicy';
import { textApi } from '../../services/textApi';
import { dossierApi } from '../../services/dossier/dossierApi';

interface DossierReaderProps {
  dossierId: string;
  dossierTitle?: string;
  className?: string;
}

interface SegmentContent {
  segment: Segment;
  run: Run;
  draft: Draft;
  text: string;
}

export const DossierReader: React.FC<DossierReaderProps> = ({
  dossierId,
  dossierTitle,
  className = ''
}) => {
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [segmentContents, setSegmentContents] = useState<SegmentContent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadDossierData();
  }, [dossierId]);

  const loadDossierData = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Load the full dossier with segments, runs, and drafts
      const fullDossier = await dossierApi.getDossier(dossierId).catch((e: any) => {
        if (e?.statusCode === 404) {
          console.warn('DossierReader: dossier not found (404), refreshing list');
          try { document.dispatchEvent(new Event('dossiers:refresh')); } catch {}
          throw e;
        }
        throw e;
      });
      setDossier(fullDossier);

      await loadDossierContent(fullDossier);
    } catch (err: any) {
      console.error('Failed to load dossier:', err);
      if (err?.statusCode === 404) {
        setError('Dossier was removed');
      } else {
        setError('Failed to load dossier');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const loadDossierContent = async (dossierData: Dossier) => {
    try {
      const contents: SegmentContent[] = [];

      // Get the best draft selection for each segment
      const chosenDrafts = latestRunBestDraftPolicy(dossierData);

      // Load content for each chosen draft
      for (const choice of chosenDrafts) {
        // Find the segment
        const segment = dossierData.segments.find(s => s.id === choice.segmentId);
        if (!segment) continue;

        // Find the run by transcription id (support both casing styles)
        const run = segment.runs.find(r =>
          (r as any).transcriptionId === choice.transcriptionId ||
          (r as any).transcription_id === choice.transcriptionId
        );
        if (!run) continue;

        // Resolve a display draft for labeling even if strict id doesn't exist in run.drafts
        const displayDraft = resolveDisplayDraft(run, choice.draftId);

        // Always fetch the exact strict versioned id for content, scoped by dossier
        const text = await textApi
          .getDraftText(choice.transcriptionId, choice.draftId, dossierId)
          .catch(() => '');

        contents.push({
          segment,
          run,
          draft: displayDraft || ({ id: choice.draftId, position: 0, isBest: false, metadata: {} } as any),
          text: text || ''
        });
      }

      setSegmentContents(contents);
    } catch (err) {
      console.error('Failed to load dossier content:', err);
      setError('Failed to load dossier content');
      throw err;
    }
  };

  function resolveDisplayDraft(run: Run, choiceDraftId: string): Draft | null {
    const exact = (run.drafts || []).find(d => d.id === choiceDraftId);
    if (exact) return exact;

    const id = String(choiceDraftId);

    // Consensus strict -> base consensus
    if (/_consensus_(llm|alignment)_v[12]$/.test(id)) {
      const baseId = id.replace(/_v[12]$/, '');
      const base = (run.drafts || []).find(d => d.id === baseId);
      if (base) return base;
    }

    // Raw strict tid_vN_v1/v2 -> base raw tid_vN
    if (/_v\d+_v[12]$/.test(id)) {
      const baseId = id.replace(/_v(1|2)$/, '');
      const base = (run.drafts || []).find(d => d.id === baseId);
      if (base) return base;
    }

    // Alignment strict tid_draft_N_v1/v2 -> display Nth raw draft if present
    const m = id.match(/_draft_(\d+)_v[12]$/);
    if (m) {
      const n = Math.max(0, parseInt(m[1], 10) - 1);
      const byIndex = (run.drafts || [])[n];
      if (byIndex) return byIndex;
    }

    return (run.drafts || [])[0] || null;
  }

  const formatDraftSource = (run: Run, draft: Draft): string => {
    const runPosition = run.position + 1;
    const draftPosition = draft.position + 1;
    const isBest = draft.isBest ? '*' : '';
    return `Run ${runPosition}, Draft ${draftPosition}${isBest}`;
  };

  if (isLoading) {
    return (
      <div className={`dossier-reader loading ${className}`}>
        <div className="loading-indicator">
          <div className="loading-spinner"></div>
          <span>Loading dossier content...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`dossier-reader error ${className}`}>
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <span className="error-text">{error}</span>
        </div>
      </div>
    );
  }

  if (segmentContents.length === 0) {
    return (
      <div className={`dossier-reader empty ${className}`}>
        <div className="empty-state">
          <div className="empty-icon">📄</div>
          <h3>No content available</h3>
          <p>This dossier doesn't have any readable content yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`dossier-reader ${className}`}>
      {/* Dossier header */}
      <div className="dossier-reader-header">
        <h2 className="dossier-title">{dossier.title || dossier.name || 'Untitled Dossier'}</h2>
        <div className="dossier-meta">
          <span className="segment-count">{segmentContents.length} segments</span>
          <span className="total-drafts">
            {segmentContents.reduce((sum, content) => sum + content.segment.runs.reduce((runSum, run) => runSum + (run.drafts?.length || 0), 0), 0)} total drafts
          </span>
        </div>
      </div>

      {/* Segment content */}
      <div className="dossier-content">
        {segmentContents.map((content, index) => (
          <div key={content.segment.id} className="segment-section">
            {/* Segment header with source attribution */}
            <div className="segment-header">
              <div className="segment-info">
                <h3 className="segment-title">
                  {content.segment.name || `Segment ${index + 1}`}
                </h3>
                <span className="draft-source">
                  {formatDraftSource(content.run, content.draft)}
                </span>
              </div>

              {/* Future: Draft selector dropdown */}
              <div className="segment-controls">
                {/* Placeholder for future dropdown to switch drafts */}
              </div>
            </div>

            {/* Segment content */}
            <div className="segment-text">
              {content.text.split('\n').map((line, lineIndex) => (
                <p key={lineIndex} className={line.trim() === '' ? 'empty-line' : ''}>
                  {line || '\u00A0' /* Non-breaking space for empty lines */}
                </p>
              ))}
            </div>

            {/* Subtle segment boundary (not shown on last segment) */}
            {index < segmentContents.length - 1 && (
              <div className="segment-boundary">
                <hr className="segment-divider" />
                <div className="segment-transition">● ● ●</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// Default export for compatibility
export default DossierReader;

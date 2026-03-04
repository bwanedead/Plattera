import React from 'react';
import { getAgentViewerArtifactImageUrl, getAgentViewerArtifactJson, type AgentViewerEvent } from '../../../services/agentViewerApi';
import {
  buildLineDiffRows,
  collectArtifactCandidates,
  extractImagePath,
  extractImageVerificationResults,
  extractPreviewPolyline,
  findLatestRef,
  renderMetaOf,
  transcriptTextFromArtifact,
} from '../agentViewerUtils';
import type { AgentCanvasPage, CanvasMode } from '../types';

async function loadBestArtifactJson(startRef: string, candidates: string[]): Promise<{ ref: string; json: any }> {
  const queue = [startRef, ...candidates.filter((v) => v && v !== startRef)];
  const visited = new Set<string>();
  let lastError: Error | null = null;

  while (queue.length) {
    const ref = queue.shift() as string;
    if (!ref || visited.has(ref)) continue;
    visited.add(ref);
    try {
      const payload = await getAgentViewerArtifactJson(ref);
      const data = payload?.json;
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        const transcriptRef = typeof (data as any).transcript_ref === 'string' ? String((data as any).transcript_ref) : '';
        const sourceRef = typeof (data as any).source_transcript_ref === 'string' ? String((data as any).source_transcript_ref) : '';
        if (transcriptRef && !visited.has(transcriptRef)) {
          queue.unshift(transcriptRef);
          continue;
        }
        if (sourceRef && !visited.has(sourceRef)) {
          queue.unshift(sourceRef);
          continue;
        }
      }
      return { ref, json: data };
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Failed to open artifact');
    }
  }
  throw lastError || new Error('Failed to open artifact');
}

type Params = {
  orderedEvents: AgentViewerEvent[];
  canvasMode: CanvasMode;
};

export function useAgentViewerArtifacts({ orderedEvents, canvasMode }: Params) {
  const [selectedArtifactRef, setSelectedArtifactRef] = React.useState<string | null>(null);
  const [selectedArtifactJson, setSelectedArtifactJson] = React.useState<any>(null);
  const [artifactError, setArtifactError] = React.useState<string | null>(null);
  const [loadingArtifact, setLoadingArtifact] = React.useState(false);
  const [canvasPageIndex, setCanvasPageIndex] = React.useState(0);
  const [sourceTranscriptText, setSourceTranscriptText] = React.useState('');
  const [editedTranscriptText, setEditedTranscriptText] = React.useState('');
  const [selectedVerifyResultIndex, setSelectedVerifyResultIndex] = React.useState(0);

  const artifactCandidates = React.useMemo(() => collectArtifactCandidates(orderedEvents), [orderedEvents]);
  const sourceTranscriptRef = React.useMemo(() => findLatestRef(orderedEvents, 'tx_source_transcript_ref'), [orderedEvents]);
  const editedTranscriptRef = React.useMemo(() => findLatestRef(orderedEvents, 'tx_edited_transcript_ref'), [orderedEvents]);
  const transcriptDiffRows = React.useMemo(
    () => buildLineDiffRows(sourceTranscriptText, editedTranscriptText),
    [sourceTranscriptText, editedTranscriptText],
  );
  const activeImagePath = React.useMemo(
    () => extractImagePath(orderedEvents, selectedArtifactJson),
    [orderedEvents, selectedArtifactJson],
  );
  const imageVerifyResults = React.useMemo(
    () => extractImageVerificationResults(orderedEvents, selectedArtifactJson),
    [orderedEvents, selectedArtifactJson],
  );
  const selectedVerifyResult = imageVerifyResults[Math.min(selectedVerifyResultIndex, Math.max(imageVerifyResults.length - 1, 0))] || null;
  const selectedVerifyMeta = renderMetaOf(selectedVerifyResult);
  const verifyOriginalSize = React.useMemo(() => {
    const withMeta = imageVerifyResults.find((v) => renderMetaOf(v)?.original_size);
    const size = renderMetaOf(withMeta)?.original_size;
    if (Array.isArray(size) && size.length >= 2) return [Number(size[0]) || 1000, Number(size[1]) || 1000] as [number, number];
    return [1000, 1000] as [number, number];
  }, [imageVerifyResults]);
  const activeImageUrl = React.useMemo(
    () => (activeImagePath ? getAgentViewerArtifactImageUrl(activeImagePath) : null),
    [activeImagePath],
  );
  const previewPolyline = React.useMemo(
    () => extractPreviewPolyline(selectedArtifactJson),
    [selectedArtifactJson],
  );
  const previewPathD = React.useMemo(() => {
    if (!previewPolyline || previewPolyline.length < 2) return '';
    const xs = previewPolyline.map((p) => p[0]);
    const ys = previewPolyline.map((p) => p[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = Math.max(1e-6, maxX - minX);
    const height = Math.max(1e-6, maxY - minY);
    const pad = 24;
    const inner = 1000 - pad * 2;
    return previewPolyline
      .map(([x, y], idx) => {
        const nx = pad + ((x - minX) / width) * inner;
        const ny = 1000 - (pad + ((y - minY) / height) * inner);
        return `${idx === 0 ? 'M' : 'L'} ${nx.toFixed(2)} ${ny.toFixed(2)}`;
      })
      .join(' ');
  }, [previewPolyline]);

  const availableCanvasPages = React.useMemo(() => {
    const pages: Array<{ id: AgentCanvasPage; label: string }> = [{ id: 'live_draft', label: 'Live Draft' }];
    if (sourceTranscriptText || editedTranscriptText) pages.push({ id: 'diff', label: 'Compare' });
    if (activeImageUrl) pages.push({ id: 'verify_image', label: 'Image Verify' });
    if (selectedArtifactJson && typeof selectedArtifactJson === 'object') {
      const obj = selectedArtifactJson as Record<string, any>;
      if (Array.isArray(obj.ops) || Array.isArray(obj.plan?.ops) || Array.isArray(obj.results)) {
        pages.push({ id: 'ops', label: 'Ops/Checks' });
      }
    }
    if (previewPolyline || findLatestRef(orderedEvents, 'ir_ref')) pages.push({ id: 'wip_preview', label: 'WIP Preview' });
    return pages;
  }, [activeImageUrl, editedTranscriptText, orderedEvents, previewPolyline, selectedArtifactJson, sourceTranscriptText]);

  const activeCanvasPage = availableCanvasPages[Math.min(canvasPageIndex, Math.max(availableCanvasPages.length - 1, 0))]?.id ?? 'live_draft';

  React.useEffect(() => {
    if (canvasPageIndex < availableCanvasPages.length) return;
    setCanvasPageIndex(0);
  }, [availableCanvasPages.length, canvasPageIndex]);

  React.useEffect(() => {
    if (selectedVerifyResultIndex < imageVerifyResults.length) return;
    setSelectedVerifyResultIndex(0);
  }, [imageVerifyResults.length, selectedVerifyResultIndex]);

  React.useEffect(() => {
    if (canvasMode !== 'agent') return;
    if (!artifactCandidates.length) return;
    const preferredRef = artifactCandidates[0];
    if (!selectedArtifactRef || !artifactCandidates.includes(selectedArtifactRef)) {
      setSelectedArtifactRef(preferredRef);
    }
  }, [canvasMode, artifactCandidates, selectedArtifactRef]);

  React.useEffect(() => {
    if (!selectedArtifactRef) return;
    let cancelled = false;
    setLoadingArtifact(true);
    setArtifactError(null);
    (async () => {
      try {
        const loaded = await loadBestArtifactJson(selectedArtifactRef, artifactCandidates);
        if (!cancelled) {
          setSelectedArtifactRef(loaded.ref);
          setSelectedArtifactJson(loaded.json ?? null);
        }
      } catch (error) {
        if (!cancelled) {
          setSelectedArtifactJson(null);
          setArtifactError(error instanceof Error ? error.message : 'Failed to open artifact');
        }
      } finally {
        if (!cancelled) setLoadingArtifact(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedArtifactRef, artifactCandidates]);

  React.useEffect(() => {
    let cancelled = false;
    const loadTranscriptRef = async (ref: string | null, setter: (value: string) => void) => {
      if (!ref) {
        setter('');
        return;
      }
      try {
        const payload = await getAgentViewerArtifactJson(ref);
        if (!cancelled) setter(transcriptTextFromArtifact(payload?.json));
      } catch {
        if (!cancelled) setter('');
      }
    };
    void loadTranscriptRef(sourceTranscriptRef, setSourceTranscriptText);
    void loadTranscriptRef(editedTranscriptRef, setEditedTranscriptText);
    return () => {
      cancelled = true;
    };
  }, [sourceTranscriptRef, editedTranscriptRef]);

  return {
    selectedArtifactRef,
    setSelectedArtifactRef,
    selectedArtifactJson,
    setSelectedArtifactJson,
    artifactError,
    setArtifactError,
    loadingArtifact,
    canvasPageIndex,
    setCanvasPageIndex,
    sourceTranscriptText,
    setSourceTranscriptText,
    editedTranscriptText,
    setEditedTranscriptText,
    selectedVerifyResultIndex,
    setSelectedVerifyResultIndex,
    transcriptDiffRows,
    activeImageUrl,
    verifyOriginalSize,
    imageVerifyResults,
    selectedVerifyResult,
    selectedVerifyMeta,
    previewPathD,
    availableCanvasPages,
    activeCanvasPage,
  };
}

import React, { useState, useCallback, useEffect } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { AnimatedBorder } from './AnimatedBorder';
import { useTextToSchemaState, useWorkspaceNavigation } from '../hooks/useWorkspaceState';
import { convertTextToSchema, getTextToSchemaModels, getSchema } from '../services/textToSchemaApi';
import { finalizedApi } from '../services/dossier/finalizedApi';
import { saveSchemaForDossier } from '../services/textToSchemaApi';
import { saveDossierEditAPI } from '../services/imageProcessingApi';
import { TextToSchemaControlPanel } from './text-to-schema/TextToSchemaControlPanel';
import { SchemaResultsTabs } from './text-to-schema/SchemaResultsTabs';
import { OriginalTextTab } from './text-to-schema/OriginalTextTab';
import { JsonSchemaTab } from './text-to-schema/JsonSchemaTab';
import { FieldViewTab } from './text-to-schema/FieldViewTab';
import { FinalTextEditor } from './text-to-schema/FinalTextEditor';
import { SchemaTab, TextToSchemaResult } from '../types/textToSchema';
import { SchemaManager } from './schema/SchemaManager';
import { StableAllotmentContainer } from './layout/StableAllotmentContainer';
import { schemaApi } from '../services/schema/schemaApi';

interface TextToSchemaWorkspaceProps {
  onExit: () => void;
  onNavigateToImageText?: () => void;
}

export const TextToSchemaWorkspace: React.FC<TextToSchemaWorkspaceProps> = ({ 
  onExit, 
  onNavigateToImageText 
}) => {
  // Dedicated flag so we can keep EXE builds clean while still enabling
  // intensive layout diagnostics in dev when needed.
  const ALLOTMENT_DEBUG =
    typeof process !== 'undefined' &&
    (process as any).env &&
    (process as any).env.NEXT_PUBLIC_ALLOTMENT_DEBUG === 'true';
  // State persistence hooks
  const { state, updateState } = useTextToSchemaState();
  const { setActiveWorkspace } = useWorkspaceNavigation();
  
  // Local UI state (not persisted)
  const [homeHovered, setHomeHovered] = useState(false);
  const [imageTextHovered, setImageTextHovered] = useState(false);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [selectedTab, setSelectedTab] = useState<SchemaTab>('original');
  // Editing toggles and buffers
  const [finalEditMode, setFinalEditMode] = useState(false);
  const [finalEdits, setFinalEdits] = useState<string[]>([]);
  const [jsonEditToken, setJsonEditToken] = useState<number>(0);
  const [showSchemaManagerPanel, setShowSchemaManagerPanel] = useState<boolean>(false);

  // Measurement/debug refs for Allotment container
  const containerRef = React.useRef<HTMLDivElement | null>(null);


  // Layout helpers for main Allotment - keep sizes aligned with visible panes
  const getLayoutSizes = useCallback(
    () => (showSchemaManagerPanel ? [300, 280, 420] : [300, 700]),
    [showSchemaManagerPanel],
  );

  const layoutKey = showSchemaManagerPanel ? 'with-schema-manager' : 'no-schema-manager';

  // Finalized dossier selection state
  const [finalizedList, setFinalizedList] = useState<Array<{ dossier_id: string; title?: string; latest_generated_at?: string }>>([]);
  const [finalizedLoading, setFinalizedLoading] = useState(false);
  const [selectedFinalizedId, setSelectedFinalizedId] = useState<string | null>(
    (state as any)?.selectedFinalizedDossierId || null
  );

  // Debug the final draft text
  useEffect(() => {
    console.log('🔍 TEXT-TO-SCHEMA DEBUG: Final draft text type and value:', {
      type: typeof state.finalDraftText,
      value: state.finalDraftText,
      isString: typeof state.finalDraftText === 'string',
      length: state.finalDraftText ? state.finalDraftText.length : 'null'
    });
  }, [state.finalDraftText]);

  // Debug: measure container + Allotment rects across a few frames on layoutKey changes
  useEffect(() => {
    if (!containerRef.current) return;

    // In production/EXE we avoid stacking our own Resize/RAF measurement
    // on top of react-allotment's internals to reduce the chance of
    // triggering "ResizeObserver loop" warnings in WebView2.
    if (!ALLOTMENT_DEBUG) return;

    let frame = 0;
    const maxFrames = 5;
    let cancelled = false;

    const logFrame = () => {
      if (cancelled) return;
      const container = containerRef.current;
      const allotmentEl = container?.querySelector('.allotment') as HTMLElement | null;
      if (container) {
        const cr = container.getBoundingClientRect();
        const ar = allotmentEl ? allotmentEl.getBoundingClientRect() : null;
        console.error('📐 [ALLOTMENT MEASURE][text-to-schema]', {
          frame,
          layoutKey,
          container: { x: cr.x, y: cr.y, width: cr.width, height: cr.height },
          allotment: ar
            ? { x: ar.x, y: ar.y, width: ar.width, height: ar.height }
            : null,
        });
      }
      frame += 1;
      if (frame < maxFrames) {
        requestAnimationFrame(logFrame);
      }
    };

    requestAnimationFrame(logFrame);
    return () => {
      cancelled = true;
    };
  }, [layoutKey]);

  // Debug: ResizeObserver heartbeat on the workspace container
  useEffect(() => {
    if (!containerRef.current || typeof ResizeObserver === 'undefined') return;

    if (!ALLOTMENT_DEBUG) return;

    let count = 0;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const cr = entry.contentRect;
      count += 1;
      console.error('📏 [ALLOTMENT RO][text-to-schema]', {
        count,
        layoutKey,
        width: cr.width,
        height: cr.height,
      });
    });

    ro.observe(containerRef.current);
    return () => {
      try {
        ro.disconnect();
      } catch {}
    };
  }, [layoutKey]);

  // Set active workspace when component mounts
  useEffect(() => {
    setActiveWorkspace('text-to-schema');
  }, [setActiveWorkspace]);

  // Load models on mount
  useEffect(() => {
    loadAvailableModels();
  }, []);

  // Consume one-shot JSON edit token after navigating to JSON tab
  useEffect(() => {
    if (selectedTab === 'json' && jsonEditToken > 0) {
      const id = window.setTimeout(() => setJsonEditToken(0), 0);
      return () => window.clearTimeout(id);
    }
  }, [selectedTab, jsonEditToken]);

  // Load finalized dossiers list on mount
  useEffect(() => {
    let mounted = true;

    const waitForBackend = async () => {
      const delays = [400, 800, 1200, 2000, 3000, 5000, 8000];
      for (let i = 0; i < delays.length; i++) {
        try {
          const r = await fetch('http://localhost:8000/api/health', { cache: 'no-store' as RequestCache });
          if (r.ok) return true;
        } catch {}
        await new Promise(r => setTimeout(r, delays[i]));
      }
      return false;
    };

    const loadList = async () => {
      try {
        setFinalizedLoading(true);
        await waitForBackend();
        const list = await finalizedApi.listFinalized().catch(() => []);
        if (!mounted) return;
        setFinalizedList(list || []);
        // Detect staleness if selected dossier is chosen and timestamps differ
        if (selectedFinalizedId) {
          const entry = (list || []).find(e => String(e.dossier_id) === String(selectedFinalizedId));
          const latest = entry?.latest_generated_at;
          if (latest && state.selectedFinalizedSnapshotAt && latest !== state.selectedFinalizedSnapshotAt) {
            updateState({ isFinalizedSnapshotStale: true } as any);
          }
        }
      } finally {
        if (!mounted) return;
        setFinalizedLoading(false);
      }
    };

    loadList();

    const onFinalized = async (ev: Event) => {
      try {
        const d: any = (ev as CustomEvent)?.detail;
        if (!d?.dossierId) return;
        // refresh list and, if this is the selected dossier, reload snapshot
        const list = await finalizedApi.listFinalized().catch(() => []);
        if (!mounted) return;
        setFinalizedList(list || []);
        if (String(d.dossierId) === String(selectedFinalizedId)) {
          try {
            const data = await finalizedApi.getFinalLive(String(d.dossierId));
            const sectionsArr: string[] = Array.isArray(data?.sections)
              ? data.sections.map((s: any) => String(s?.text || '').trim())
              : (data?.stitched_text ? [String(data.stitched_text)] : []);
            const sectionRefs = Array.isArray(data?.sections)
              ? data.sections.map((s: any) => ({
                  segmentId: s?.segment_id,
                  transcriptionId: s?.transcription_id,
                  draftIdUsed: s?.draft_id_used
                }))
              : [];
            const stitched = sectionsArr.filter(Boolean).join('\n\n');
            updateState({
              finalDraftText: stitched,
              finalDraftMetadata: {
                source: 'finalized-dossier',
                dossierId: String(d.dossierId),
                dossierTitle: data?.dossier_title,
                generatedAt: data?.generated_at
              },
              schemaResults: null,
              selectedFinalizedSnapshotAt: data?.generated_at || null,
              isFinalizedSnapshotStale: false,
              selectedFinalizedSections: sectionsArr,
              selectedFinalizedSectionRefs: sectionRefs
            } as any);
            setSelectedTab('original');
            setFinalEditMode(false);
            setFinalEdits(sectionsArr);
          } catch (e) {
            console.warn('Failed to reload finalized snapshot after event', e);
          }
        }
      } catch {}
    };

    const onFinalSet = async (ev: Event) => {
      try {
        const d: any = (ev as CustomEvent)?.detail;
        if (!d?.dossierId) return;
        // Refresh list quickly so timestamps reflect latest finalize/unfinalize
        try {
          const list = await finalizedApi.listFinalized().catch(() => []);
          if (mounted) setFinalizedList(list || []);
        } catch {}
        // If current selection became cleared/outdated, mark stale in UI
        if (String(d.dossierId) === String(selectedFinalizedId) && (d?.draftId == null)) {
          updateState({ isFinalizedSnapshotStale: true } as any);
        }
      } catch {}
    };

    document.addEventListener('dossier:finalized', onFinalized as any);
    document.addEventListener('dossier:final-set', onFinalSet as any);

    return () => {
      mounted = false;
      document.removeEventListener('dossier:finalized', onFinalized as any);
      document.removeEventListener('dossier:final-set', onFinalSet as any);
    };
  }, [selectedFinalizedId, state.selectedFinalizedSnapshotAt, updateState]);

  // Load available models
  const loadAvailableModels = async () => {
    try {
      const response = await getTextToSchemaModels();
      if (response.status === 'success' && response.models) {
        setAvailableModels(response.models);
      }
    } catch (error) {
      console.warn('Failed to load models, using defaults:', error);
      setAvailableModels({
        "gpt-4o": { name: "GPT-4o", provider: "openai" },
        "gpt-4": { name: "GPT-4", provider: "openai" },
      });
    }
  };

  // Handle model selection change
  const handleModelChange = useCallback((model: string) => {
    updateState({ selectedModel: model });
  }, [updateState]);

  // Synchronize edit buffer with latest sections
  useEffect(() => {
    const arr = (state as any)?.selectedFinalizedSections;
    if (Array.isArray(arr)) {
      setFinalEdits(arr.slice());
    } else {
      setFinalEdits([]);
    }
  }, [state.selectedFinalizedSections]);

  // Save a single finalized section edit
  const handleSaveFinalSection = useCallback(async (index: number) => {
    try {
      const refs: Array<{ segmentId: string; transcriptionId: string; draftIdUsed: string }> = (state as any)?.selectedFinalizedSectionRefs || [];
      const ref = refs[index];
      const dossierId = (state.finalDraftMetadata as any)?.dossierId || (state.finalDraftMetadata as any)?.dossier_id || selectedFinalizedId;
      if (!ref || !dossierId) return;

      const transcriptionId = String(ref.transcriptionId || '');
      const draftIdUsed = String(ref.draftIdUsed || '');
      const body = finalEdits[index] || '';

      const payload: any = {
        dossierId: String(dossierId),
        transcriptionId,
        editedSections: [{ id: 1, body }]
      };

      const mAlign = draftIdUsed.match(/_draft_(\d+)(?:_v[12])?$/);
      const mRaw = draftIdUsed.match(new RegExp(`${transcriptionId}_v(\\d+)`));
      if (/_consensus_alignment/.test(draftIdUsed)) {
        payload.consensusType = 'alignment';
      } else if (/_consensus_llm/.test(draftIdUsed)) {
        payload.consensusType = 'llm';
      } else if (mAlign) {
        payload.alignmentDraftIndex = Math.max(0, parseInt(mAlign[1], 10) - 1);
      } else if (mRaw) {
        payload.draftIndex = Math.max(0, parseInt(mRaw[1], 10) - 1);
      }

      await saveDossierEditAPI(payload);

      const data = await finalizedApi.getFinalLive(String(dossierId));
      const sectionsArr: string[] = Array.isArray(data?.sections)
        ? data.sections.map((s: any) => String(s?.text || '').trim())
        : (data?.stitched_text ? [String(data.stitched_text)] : []);
      const sectionRefs = Array.isArray(data?.sections)
        ? data.sections.map((s: any) => ({
            segmentId: s?.segment_id,
            transcriptionId: s?.transcription_id,
            draftIdUsed: s?.draft_id_used
          }))
        : [];
      updateState({
        finalDraftText: sectionsArr.filter(Boolean).join('\n\n'),
        finalDraftMetadata: {
          ...(state.finalDraftMetadata || {}),
          generatedAt: data?.generated_at
        },
        selectedFinalizedSections: sectionsArr,
        selectedFinalizedSectionRefs: sectionRefs,
        isFinalizedSnapshotStale: false
      } as any);
      setFinalEdits(sectionsArr);
      setFinalEditMode(false);
    } catch (e) {
      console.error('Failed to save final section edit', e);
      alert('Failed to save section edit');
    }
  }, [state, finalEdits, selectedFinalizedId, updateState]);

  // Handle tab change
  const handleTabChange = useCallback((tab: SchemaTab) => {
    setSelectedTab(tab);
  }, []);

  // Handle text-to-schema processing
  const handleStartTextToSchema = useCallback(async (directText?: string) => {
    const DIRECT_TEXT_DOSSIER_ID = '__direct_text__';

    // Use direct text if provided, otherwise use final draft text
    const textToProcess = directText || (typeof state.finalDraftText === 'string' 
      ? state.finalDraftText 
      : String(state.finalDraftText || ''));

    console.log('🔍 TEXT-TO-SCHEMA PROCESSING: Starting with text:', {
      isDirectInput: !!directText,
      textSource: directText ? 'direct-input' : 'final-draft',
      textLength: textToProcess.length
    });

    if (!textToProcess.trim()) {
      console.warn('No text available for processing');
      return;
    }

    // Determine dossier context: real dossier when selected, otherwise virtual
    const effectiveDossierId = selectedFinalizedId || DIRECT_TEXT_DOSSIER_ID;
    const isVirtualDossier = !selectedFinalizedId;

    // Optimistic pending row for all schema runs (direct-text or finalized-dossier)
    const pendingId = `pending-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const pendingLabel = isVirtualDossier
      ? 'Direct Text (processing…)'
      : `${((state.finalDraftMetadata as any)?.dossierTitle || 'Finalized dossier')} (processing…)`;

    try {
      document.dispatchEvent(
        new CustomEvent('schemas:pending-add', {
          detail: {
            tempId: pendingId,
            dossier_id: effectiveDossierId,
            label: pendingLabel,
          },
        })
      );
    } catch {}

    updateState({ isProcessing: true, schemaResults: null });

    try {
      const response = await convertTextToSchema({
        text: textToProcess,
        model: state.selectedModel,
        parcel_id: `parcel-${Date.now()}`,
        // Always pass a dossier id for metadata tagging
        dossier_id: effectiveDossierId
      } as any);

      const result: TextToSchemaResult = {
        success: response.status === 'success',
        structured_data: response.structured_data,
        original_text: response.original_text,
        model_used: response.model_used,
        service_type: response.service_type,
        tokens_used: response.tokens_used,
        confidence_score: response.confidence_score,
        validation_warnings: response.validation_warnings,
        metadata: response.metadata
      };

      const firstTime = !(state as any)?.schemaResultsOriginal;
      updateState({ schemaResults: result, isProcessing: false, ...(firstTime ? { schemaResultsOriginal: result } : {}) });
      console.log('✅ Schema processing completed:', result);

      // Persist schema for both finalized-dossier and direct-text runs
      if (result.success && result.structured_data) {
        try {
          const saveRes = await saveSchemaForDossier({
            dossier_id: effectiveDossierId,
            model_used: result.model_used,
            structured_data: result.structured_data,
            original_text: textToProcess,
            metadata: {
              ...(state.finalDraftMetadata || {}),
              selection_source: selectedFinalizedId ? 'finalized_dossier' : 'direct_text'
            }
          });
          console.log('💾 Schema saved for dossier', effectiveDossierId, saveRes);
          // Notify schema manager to refresh listing
          try { document.dispatchEvent(new Event('schemas:refresh')); } catch {}

          // Enrich schemaData with persisted artifact (schema_id + metadata.dossierId/version_label) for mapping flow
          if (saveRes?.schema_id) {
            try {
              const artRes = await getSchema(effectiveDossierId, saveRes.schema_id);
              const artifact = artRes?.artifact || artRes;
              const enriched = {
                ...(artifact?.structured_data || result.structured_data),
                schema_id: artifact?.schema_id || saveRes.schema_id,
                metadata: {
                  ...(
                    (artifact && (artifact as any).metadata) ||
                    ((result.structured_data as any)?.metadata) ||
                    {}
                  ),
                  dossierId: String(effectiveDossierId)
                }
              };
              updateState({ schemaResults: { ...result, structured_data: enriched } });
            } catch (fetchErr) {
              // Fallback: minimally inject dossierId into current structured_data
              updateState({
                schemaResults: {
                  ...result,
                  structured_data: {
                    ...result.structured_data,
                    metadata: {
                      ...(((result.structured_data as any)?.metadata) || {}),
                      dossierId: String(effectiveDossierId)
                    }
                  }
                }
              });
            }
          }
        } catch (e) {
          console.warn('Failed to save schema for dossier', e);
        }
      }
      
      // Auto-switch to Field View tab when results come in
      setSelectedTab('fields');
    } catch (error) {
      const errorResult: TextToSchemaResult = {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
      
      updateState({
        schemaResults: errorResult,
        isProcessing: false,
      });
      console.error('❌ Schema processing failed:', error);
    } finally {
      // Remove pending row once this run finishes (success or error)
      try {
        document.dispatchEvent(
          new CustomEvent('schemas:pending-remove', { detail: { tempId: pendingId } })
        );
      } catch {}
    }
  }, [state.finalDraftText, state.selectedModel, updateState, selectedFinalizedId, state]);

  // Finalized selection handler
  const handleSelectFinalized = useCallback(async (dossierId: string) => {
    try {
      setSelectedFinalizedId(dossierId);
      updateState({ selectedFinalizedDossierId: dossierId } as any);
      const data = await finalizedApi.getFinalLive(dossierId);
      const sectionsArr: string[] = Array.isArray(data?.sections)
        ? data.sections.map((s: any) => String(s?.text || '').trim())
        : (data?.stitched_text ? [String(data.stitched_text)] : []);
      const sectionRefs = Array.isArray(data?.sections)
        ? data.sections.map((s: any) => ({
            segmentId: s?.segment_id,
            transcriptionId: s?.transcription_id,
            draftIdUsed: s?.draft_id_used
          }))
        : [];
      const stitched = sectionsArr.filter(Boolean).join('\n\n');
      updateState({
        finalDraftText: stitched,
        finalDraftMetadata: {
          source: 'finalized-dossier',
          dossierId,
          dossierTitle: data?.dossier_title,
          generatedAt: data?.generated_at
        },
        schemaResults: null,
        selectedFinalizedSnapshotAt: data?.generated_at || null,
        isFinalizedSnapshotStale: false,
        selectedFinalizedSections: sectionsArr,
        selectedFinalizedSectionRefs: sectionRefs
      } as any);
      setSelectedTab('original');
      setFinalEditMode(false);
      setFinalEdits(sectionsArr);
    } catch (e) {
      console.error('Failed to load finalized dossier', e);
    }
  }, [updateState]);

  // Render the appropriate tab content
  const renderTabContent = () => {
    // Ensure we have a valid string for display
    const finalText = typeof state.finalDraftText === 'string' 
      ? state.finalDraftText 
      : String(state.finalDraftText || '');

    switch (selectedTab) {
      case 'original':
        return finalText ? (
          finalEditMode ? (
            <FinalTextEditor
              sections={finalEdits}
              onChange={(i, v) => setFinalEdits(prev => prev.map((x, idx) => (idx === i ? v : x)))}
              onSave={(i) => handleSaveFinalSection(i)}
              onDone={() => setFinalEditMode(false)}
            />
          ) : (
            <OriginalTextTab
              text={finalText}
              showSectionMarkers={true}
              sections={state.selectedFinalizedSections || undefined}
              onToggleEdit={() => setFinalEditMode(v => !v)}
              editMode={finalEditMode}
            />
          )
        ) : (
          <div className="processing-placeholder">
            <p>No final draft available. Complete image-to-text processing to continue.</p>
          </div>
        );

      case 'json':
        return (
          <JsonSchemaTab
            schemaData={state.schemaResults?.structured_data}
            isSuccess={state.schemaResults?.success || false}
            error={state.schemaResults?.error}
            dossierId={selectedFinalizedId || (state.finalDraftMetadata as any)?.dossierId}
            originalText={finalText}
            currentSchemaId={(state.schemaResults?.structured_data as any)?.schema_id}
            rootSchemaId={(state as any)?.schemaResultsOriginal?.structured_data?.schema_id}
            startEditToken={jsonEditToken}
            onSaved={async (artifact: any) => {
              try {
                const dossier = selectedFinalizedId || (state.finalDraftMetadata as any)?.dossierId;
                if (!dossier || !artifact?.schema_id) return;
                // Retry with short backoff to avoid reading before the atomic write lands
                const delays = [120, 240, 480, 800];
                let fetched: any = null;
                for (let i = 0; i < delays.length; i++) {
                  try {
                    const art = await schemaApi.getSchema(dossier, artifact.schema_id);
                    const sd = (art as any)?.structured_data || (art as any)?.artifact?.structured_data;
                    if (sd) { fetched = sd; break; }
                  } catch {}
                  await new Promise(r => setTimeout(r, delays[i]));
                }
                if (fetched) {
                  // Inject schema_id and dossierId for stable parent/dossier resolution in JSON tab
                  const mergedFetched = { 
                    ...fetched, 
                    schema_id: artifact.schema_id,
                    metadata: { ...(fetched?.metadata || {}), dossierId: String(dossier) }
                  };
                  updateState({ 
                    schemaResults: { ...(state.schemaResults || {}), structured_data: mergedFetched } as any,
                    finalDraftMetadata: { ...(state.finalDraftMetadata || {}), dossierId: String(dossier) } as any
                  });
                }
                // Notify schema manager to refresh listing
                try { document.dispatchEvent(new Event('schemas:refresh')); } catch {}
              } catch {}
            }}
          />
        );

      case 'fields':
        return (
          <FieldViewTab
            schemaData={state.schemaResults?.structured_data || null}
            isSuccess={state.schemaResults?.success || false}
            error={state.schemaResults?.error}
            dossierId={selectedFinalizedId || (state.finalDraftMetadata as any)?.dossierId}
            onEditInJson={() => {
              setSelectedTab('json');
              setJsonEditToken(prev => prev + 1);
            }}
          />
        );

      default:
        return null;
    }
  };

  // Ensure we have a valid string for the control panel
  const finalText = typeof state.finalDraftText === 'string' 
    ? state.finalDraftText 
    : String(state.finalDraftText || '');

  // Version badge label (v1/v2) for the current schema results, from metadata or lineage
  const versionLabel: string | undefined =
    ((state.schemaResults?.structured_data as any)?.metadata?.version_label as string | undefined) ||
    ((state.schemaResults?.structured_data as any)?.lineage?.version_label as string | undefined);

  return (
    <div className="text-to-schema-workspace" ref={containerRef}>
      {/* Navigation Header */}
      <div className="workspace-nav">
        <AnimatedBorder
          isHovered={homeHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-home" 
            onClick={onExit}
            onMouseEnter={() => setHomeHovered(true)}
            onMouseLeave={() => setHomeHovered(false)}
          >
            Home
          </button>
        </AnimatedBorder>
        <AnimatedBorder
          isHovered={imageTextHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-prev" 
            onClick={onNavigateToImageText}
            onMouseEnter={() => setImageTextHovered(true)}
            onMouseLeave={() => setImageTextHovered(false)}
          >
            Image to Text
          </button>
        </AnimatedBorder>
      </div>

      {/* Main Content Area */}
      <StableAllotmentContainer debugLabel="text-to-schema">
        {() => {
      console.error('📐 [ALLOTMENT JSX RENDER][text-to-schema]', { layoutKey });
      return (
      <Allotment
        key={layoutKey}
        defaultSizes={getLayoutSizes()}
        vertical={false}
      >
        {/* Control Panel (Left) */}
        <Allotment.Pane minSize={250} maxSize={400}>
          <TextToSchemaControlPanel
            finalDraftText={finalText}
            finalDraftMetadata={state.finalDraftMetadata}
            selectedModel={state.selectedModel}
            availableModels={availableModels}
            isProcessing={state.isProcessing}
            onModelChange={handleModelChange}
            onStartProcessing={handleStartTextToSchema} // Now accepts optional text parameter
            finalizedDossiers={finalizedList}
            finalizedLoading={finalizedLoading}
            selectedFinalizedId={selectedFinalizedId}
            onSelectFinalized={handleSelectFinalized}
          />
          {showSchemaManagerPanel && (
            <div style={{ display: 'none' }}></div>
          )}
        </Allotment.Pane>

        {showSchemaManagerPanel && (
          <Allotment.Pane minSize={220} maxSize={480}>
            <div className="results-history-panel visible" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              <div className="history-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px', borderBottom: '1px solid #2d2d2d' }}>
                <h4 style={{ margin: 0 }}>Schema Manager</h4>
                <button onClick={() => setShowSchemaManagerPanel(false)}>‹</button>
              </div>
              <div className="schema-manager-content" style={{ flex: 1, minHeight: 0 }}>
                <SchemaManager
                  dossierId={selectedFinalizedId || (state.finalDraftMetadata as any)?.dossierId || null}
                  onSelectionChange={async (sel) => {
                    try {
                      const art = await schemaApi.getSchema(sel.dossier_id, sel.schema_id);
                      const sd = art?.structured_data || null;
                      if (sd) {
                        const merged: any = { 
                          ...sd, 
                          schema_id: art?.schema_id || sel.schema_id,
                          metadata: { ...((sd as any)?.metadata || {}), dossierId: String(sel.dossier_id) }
                        };

                        // Resolve original text, falling back to lineage root (v1) if needed.
                        let originalText: string =
                          (art as any)?.original_text ||
                          ((sd as any)?.metadata?.original_text as string) ||
                          '';

                        if (!originalText) {
                          try {
                            const lineage: any =
                              (art as any)?.lineage ||
                              ((sd as any)?.metadata?.lineage as any) ||
                              {};
                            const currentId = String(art?.schema_id || sel.schema_id || '');
                            let rootId: string | null =
                              (lineage?.root_schema_id as string) ||
                              (lineage?.parent_schema_id as string) ||
                              null;

                            // Fallback: if this looks like a v2 id, derive root from suffix
                            if (!rootId && currentId.endsWith('_v2')) {
                              rootId = currentId.slice(0, -3);
                            }

                            if (rootId && rootId !== currentId) {
                              const rootArt = await schemaApi.getSchema(sel.dossier_id, rootId);
                              originalText =
                                (rootArt as any)?.original_text ||
                                ((((rootArt as any)?.structured_data as any)?.metadata?.original_text) as string) ||
                                originalText;
                            }
                          } catch (lineageErr) {
                            console.warn('Failed to resolve original_text from lineage', lineageErr);
                          }
                        }

                        updateState({ 
                          schemaResults: { success: true, structured_data: merged } as any,
                          finalDraftMetadata: { ...(state.finalDraftMetadata || {}), dossierId: String(sel.dossier_id) } as any,
                          finalDraftText: originalText || state.finalDraftText
                        });
                      }
                    } catch (e) {
                      console.warn('Failed to load schema artifact', e);
                    }
                  }}
                />
              </div>
            </div>
          </Allotment.Pane>
        )}

        {/* Results Viewer (Right) */}
        <Allotment.Pane>
          <div className="results-viewer-panel" style={{ position: 'relative' }}>
            {!showSchemaManagerPanel && (
              <button
                className="history-toggle-button"
                onClick={() => setShowSchemaManagerPanel(true)}
                title="Show Schemas"
                style={{ left: 12 }}
              >
                ›
              </button>
            )}
            {!finalText && !state.schemaResults && (
              <div className="placeholder-view">
                <div className="placeholder-content">
                  <h3>Text to Schema Processing</h3>
                  <p>
                    Convert your final legal text into structured JSON data with organized PLSS Description and Metes & Bounds information.
                  </p>
                  <div className="placeholder-steps">
                    <div className="step">
                      <span className="step-number">1</span>
                      <span className="step-text">Complete image-to-text processing</span>
                    </div>
                    <div className="step">
                      <span className="step-number">2</span>
                      <span className="step-text">Select a final draft</span>
                    </div>
                    <div className="step">
                      <span className="step-number">3</span>
                      <span className="step-text">Convert to structured schema</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {(finalText || state.schemaResults) && (
            <div className="schema-results-viewer">
                <div className="viewer-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <h3>Processing Results</h3>
                    {versionLabel && (
                      <span
                        className="version-tag"
                        style={{
                          fontSize: '0.75rem',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          background: '#374151',
                          color: '#e5e7eb',
                          border: '1px solid #4b5563'
                        }}
                      >
                        {String(versionLabel).toUpperCase()}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {state.schemaResults && (state as any)?.schemaResultsOriginal && (
                      <button onClick={() => updateState({ schemaResults: (state as any).schemaResultsOriginal } as any)}>Revert Schema</button>
                    )}
                  </div>
                </div>
                
                {/* Tab Navigation */}
                <SchemaResultsTabs
                  selectedTab={selectedTab}
                  onTabChange={handleTabChange}
                  hasResults={state.schemaResults?.success || false}
                />

                {/* Tab Content */}
                <div className="tab-content">
                  {renderTabContent()}
                </div>
              </div>
            )}
          </div>
        </Allotment.Pane>
      </Allotment>
        );
        }}
      </StableAllotmentContainer>
    </div>
  );
};
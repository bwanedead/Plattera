export type PlssUiPhase =
  | 'downloading'
  | 'building_parquet'
  | 'finalizing'
  | 'complete'
  | 'canceled'
  | 'idle'
  | 'error'
  | 'unknown';

export interface PlssUiProgress {
  phase: PlssUiPhase;
  headline: string;
  detail?: string | null;
  percent?: number | null;
  showPercent: boolean;
  progressBar: 'determinate' | 'indeterminate' | 'none';
  /**
   * Exact backend stage string, preserved for diagnostics and any
   * high‑fidelity UI that wants to surface the raw value.
   */
  rawStage?: string | null;
}

interface RawProgress {
  stage?: string;
  overall?: { downloaded?: number; total?: number; percent?: number };
  status?: string;
  estimated_time?: string;
  final_phase?: boolean;
}

export function presentPlssProgress(
  raw: RawProgress | null | undefined,
): PlssUiProgress {
  const rawStage = raw?.stage ?? null;
  const stageNormalized = (rawStage || '').toLowerCase();
  const stageParts = stageNormalized.split(':').filter(Boolean);
  const [p1, p2, p3] = stageParts;

  const overallPercent =
    typeof raw?.overall?.percent === 'number' ? raw!.overall!.percent : null;
  const status = raw?.status ?? null;
  const finalPhase = !!raw?.final_phase;

  // Helper to build a default structure
  const base: PlssUiProgress = {
    phase: 'unknown',
    headline: 'Preparing PLSS data…',
    detail: status,
    percent: overallPercent,
    showPercent: typeof overallPercent === 'number',
    progressBar:
      typeof overallPercent === 'number' ? 'determinate' : 'indeterminate',
    rawStage,
  };

  // Helper to prettify dataset labels from stage fragments.
  const formatDatasetLabel = (rawPart?: string): string => {
    switch (rawPart) {
      case 'townships':
        return 'townships';
      case 'sections':
        return 'sections';
      case 'quarter_sections':
      case 'quarter-sections':
      case 'quartersections':
        return 'quarter sections';
      case 'subdivisions':
        return 'subdivisions';
      default:
        return 'PLSS data';
    }
  };

  // Fallback prettifier for unknown stages – keeps fidelity while
  // avoiding raw colon/underscore noise in the primary headline.
  const prettifyStageHeadline = (stageString: string): string => {
    const cleaned = stageString
      .replace(/:/g, ' › ')
      .replace(/[_-]+/g, ' ')
      .trim();
    if (!cleaned) return 'Preparing PLSS data…';

    return cleaned
      .split(/\s+/)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  };

  // High‑fidelity stage handling. We preserve full stage identity
  // (e.g., "downloading:sections", "building:parquet:subdivisions")
  // and map to polished but specific headlines.
  switch (p1) {
    case 'initializing':
    case 'processing': {
      return {
        ...base,
        phase: 'downloading',
        headline: 'Preparing PLSS download…',
        progressBar:
          typeof overallPercent === 'number' ? 'determinate' : 'indeterminate',
      };
    }

    case 'downloading': {
      const dataset = formatDatasetLabel(p2);
      return {
        ...base,
        phase: 'downloading',
        headline: `Downloading ${dataset}…`,
        progressBar:
          typeof overallPercent === 'number' ? 'determinate' : 'indeterminate',
      };
    }

    case 'building': {
      if (p2 === 'parquet') {
        const dataset = formatDatasetLabel(p3);
        return {
          ...base,
          phase: 'building_parquet',
          headline: `Building ${dataset} parquet…`,
        };
      }

      if (p2 === 'index') {
        const hasPercent = typeof overallPercent === 'number';
        return {
          ...base,
          phase: 'finalizing',
          headline: 'Building PLSS index…',
          percent: overallPercent,
          showPercent: hasPercent,
          progressBar: hasPercent ? 'determinate' : 'indeterminate',
        };
      }

      // Other building stages → generic finalizing, but preserve any
      // provided percent so the determinism policy stays data‑driven.
      return {
        ...base,
        phase: 'finalizing',
        headline: 'Finalizing PLSS installation…',
      };
    }

    case 'writing': {
      if (p2 === 'manifest') {
        return {
          ...base,
          phase: 'finalizing',
          headline: 'Writing PLSS manifest…',
        };
      }

      return {
        ...base,
        phase: 'finalizing',
        headline: 'Finalizing PLSS installation…',
      };
    }

    case 'complete': {
      return {
        ...base,
        phase: 'complete',
        headline: 'PLSS data ready.',
        percent: 100,
        showPercent: false,
        progressBar: 'none',
      };
    }

    case 'canceled': {
      return {
        ...base,
        phase: 'canceled',
        headline: 'PLSS download canceled.',
        showPercent: false,
        progressBar: 'none',
      };
    }

    case 'idle': {
      return {
        ...base,
        phase: 'idle',
        headline: 'PLSS download idle.',
        showPercent: false,
        progressBar: 'none',
      };
    }

    default: {
      if (finalPhase) {
        return {
          ...base,
          phase: 'finalizing',
          headline: 'Finalizing PLSS installation…',
        };
      }

      if (rawStage) {
        return {
          ...base,
          headline: prettifyStageHeadline(rawStage),
        };
      }

      return base;
    }
  }
}


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
}

interface RawProgress {
  stage?: string;
  overall?: { downloaded?: number; total?: number; percent?: number };
  status?: string;
  estimated_time?: string;
  final_phase?: boolean;
}

export function presentPlssProgress(raw: RawProgress | null | undefined): PlssUiProgress {
  const stage = (raw?.stage || '').toLowerCase();
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
  };

  // Normalize stage name families like "downloading:foo"
  const baseStage = stage.split(':')[0] || '';

  switch (baseStage) {
    case 'initializing':
    case 'processing':
    case 'downloading': {
      return {
        ...base,
        phase: 'downloading',
        headline: 'Downloading PLSS data…',
        progressBar:
          typeof overallPercent === 'number' ? 'determinate' : 'indeterminate',
      };
    }
    case 'building': {
      if (stage === 'building:parquet') {
        return {
          ...base,
          phase: 'building_parquet',
          headline: 'Building PLSS parquet data…',
          progressBar:
            typeof overallPercent === 'number'
              ? 'determinate'
              : 'indeterminate',
        };
      }
      // building:index → treat as finalizing
      return {
        ...base,
        phase: 'finalizing',
        headline: 'Finalizing PLSS installation…',
        percent: null,
        showPercent: false,
        progressBar: 'indeterminate',
      };
    }
    case 'writing': {
      // writing:manifest → finalizing, no percent
      return {
        ...base,
        phase: 'finalizing',
        headline: 'Finalizing PLSS installation…',
        percent: null,
        showPercent: false,
        progressBar: 'indeterminate',
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
          percent: null,
          showPercent: false,
          progressBar: 'indeterminate',
        };
      }
      return base;
    }
  }
}


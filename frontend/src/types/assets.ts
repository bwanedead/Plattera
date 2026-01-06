export type AssetStatus = 'missing' | 'installing' | 'installed' | 'failed' | 'canceled';

export interface AssetManifestSummary {
  revision?: string;
  installed_at?: string;
  total_bytes?: number;
  smoke_test?: string;
}

export interface AssetRow {
  asset_id: string;
  display_name: string;
  kind: string;
  source: string;
  status: AssetStatus;
  stage?: string | null;
  message?: string | null;
  headline?: string | null;
  detail?: string | null;
  progress_bar?: 'determinate' | 'indeterminate' | 'none' | null;
  percent?: number | null;
  bytes_downloaded?: number | null;
  bytes_total?: number | null;
  current_file?: string | null;
  phase?: string | null;
  updated_at?: string | null;
  manifest?: AssetManifestSummary | null;
  plss_state?: string | null;
}

export interface AssetProgress {
  status: AssetStatus;
  stage?: string | null;
  message?: string | null;
  headline?: string | null;
  detail?: string | null;
  progress_bar?: 'determinate' | 'indeterminate' | 'none' | null;
  percent?: number | null;
  bytes_downloaded?: number | null;
  bytes_total?: number | null;
  current_file?: string | null;
  phase?: string | null;
  updated_at?: string | null;
  error?: string | null;
}

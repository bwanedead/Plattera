import { AssetProgress, AssetRow } from '../../types/assets';

const apiBase = 'http://localhost:8000/api';

export class AssetsApi {
  async listAssets(plssState?: string | null): Promise<AssetRow[]> {
    const url = plssState ? `${apiBase}/assets?plss_state=${encodeURIComponent(plssState)}` : `${apiBase}/assets`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    return data.assets || [];
  }

  async installAsset(assetId: string): Promise<{ success: boolean; status?: string; error?: string }> {
    const res = await fetch(`${apiBase}/assets/${assetId}/install`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  async getProgress(assetId: string): Promise<AssetProgress> {
    const res = await fetch(`${apiBase}/assets/${assetId}/progress`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  async cancel(assetId: string): Promise<{ success: boolean; status?: string; error?: string }> {
    const res = await fetch(`${apiBase}/assets/${assetId}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  async stop(assetId: string): Promise<{ success: boolean; status?: string; error?: string }> {
    const res = await fetch(`${apiBase}/assets/${assetId}/stop`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  async purge(assetId: string): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${apiBase}/assets/${assetId}/purge`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  async clearCache(assetId: string): Promise<{ success: boolean; error?: string }> {
    const res = await fetch(`${apiBase}/assets/${assetId}/clear-cache`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }
}

export const assetsApi = new AssetsApi();

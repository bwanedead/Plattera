import { dossierApi } from '@/services/dossier/dossierApi';
import type { Dossier } from '@/types/dossier';

let cached: Dossier[] | null = null;
let preloading = false;

export function getCachedDossiers(): Dossier[] | null {
  return cached;
}

export async function startDossierPreload(): Promise<void> {
  if (preloading || cached) return;
  preloading = true;
  try {
    // Probe health briefly with small backoff; ignore failures
    const attempts = [600, 1000, 1500];
    for (let i = 0; i < attempts.length; i++) {
      const ok = await dossierApi.health(attempts[i]);
      if (ok) break;
      await new Promise(r => setTimeout(r, 400));
    }
    // Warm first page
    const list = await dossierApi.getDossiers({ limit: 50, offset: 0 });
    if (Array.isArray(list) && list.length > 0) {
      cached = list;
    }
  } catch {
    // silent failure; normal flows will still work
  } finally {
    preloading = false;
  }
}



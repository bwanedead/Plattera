import type { ArtifactLoadResult } from '../../model/artifactLoadResult';
import type { ReplayBundle } from './replayTypes';
import { resolveReplayArtifactPath } from './replayPathResolvers';

export function resolveReplayImageUrl(bundle: ReplayBundle, ref: string): string | null {
  const media = bundle.mediaCatalog.find((entry) => entry.ref_id === ref);
  if (!media?.placeholder_file) return null;
  return `${bundle.baseUrl}/${media.placeholder_file}`;
}

export async function loadReplayArtifact(bundle: ReplayBundle, ref: string): Promise<ArtifactLoadResult> {
  const trimmed = ref.trim();
  if (!trimmed) {
    return { kind: 'unresolved', ref, reason: 'Empty artifact ref' };
  }

  const imageUrl = resolveReplayImageUrl(bundle, trimmed);
  if (imageUrl) {
    return {
      kind: 'image',
      ref: trimmed,
      url: imageUrl,
      sourcePath: resolveReplayArtifactPath(bundle, trimmed) || imageUrl,
    };
  }

  const jsonPath = resolveReplayArtifactPath(bundle, trimmed);
  if (!jsonPath) {
    return { kind: 'unresolved', ref: trimmed, reason: 'No replay path mapping for ref' };
  }

  if (jsonPath.endsWith('.svg') || jsonPath.endsWith('.png') || jsonPath.endsWith('.jpg')) {
    return {
      kind: 'image',
      ref: trimmed,
      url: `${bundle.baseUrl}/${jsonPath}`,
      sourcePath: jsonPath,
    };
  }

  try {
    const response = await fetch(`${bundle.baseUrl}/${jsonPath}`);
    if (!response.ok) {
      return { kind: 'unresolved', ref: trimmed, reason: `HTTP ${response.status} for ${jsonPath}` };
    }
    const json = await response.json();
    return { kind: 'json', ref: trimmed, json, sourcePath: jsonPath };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown fetch error';
    return { kind: 'unresolved', ref: trimmed, reason: message };
  }
}

import { getAgentViewerArtifactImageUrl, getAgentViewerArtifactJson } from '../../../../services/agentViewerApi';
import type { ArtifactLoadResult } from '../../model/artifactLoadResult';

export async function loadLiveArtifact(ref: string): Promise<ArtifactLoadResult> {
  const trimmed = ref.trim();
  if (!trimmed) {
    return { kind: 'unresolved', ref, reason: 'Empty artifact ref' };
  }

  const looksLikeImage =
    trimmed.startsWith('image:') ||
    trimmed.includes('/images/') ||
    /\.(png|jpe?g|svg|webp|gif)$/i.test(trimmed);

  if (looksLikeImage) {
    return {
      kind: 'image',
      ref: trimmed,
      url: getAgentViewerArtifactImageUrl(trimmed),
      sourcePath: trimmed,
    };
  }

  try {
    const payload = await getAgentViewerArtifactJson(trimmed);
    return {
      kind: 'json',
      ref: trimmed,
      json: payload.json,
      sourcePath: payload.artifact_path || trimmed,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to load artifact';
    return { kind: 'unresolved', ref: trimmed, reason: message };
  }
}

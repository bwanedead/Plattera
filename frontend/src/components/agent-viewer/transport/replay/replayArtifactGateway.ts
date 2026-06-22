import type { ReplayBundle } from './replayTypes';

const TRANSCRIPT_ARTIFACT_PATHS: Record<string, string> = {
  'transcript_edit:output': 'artifacts/transcript_edit/output/output.json',
  'transcript_edit:working': 'artifacts/transcript_edit/working/latest.json',
  'transcript_edit:working:rev:0001': 'artifacts/transcript_edit/working/rev_0001.json',
};

export type ReplayArtifactResult =
  | { kind: 'json'; ref: string; json: unknown; sourcePath: string }
  | { kind: 'image'; ref: string; url: string; sourcePath: string }
  | { kind: 'unresolved'; ref: string; reason: string };

export function resolveReplayImageUrl(bundle: ReplayBundle, ref: string): string | null {
  const media = bundle.mediaCatalog.find((entry) => entry.ref_id === ref);
  if (!media?.placeholder_file) return null;
  return `${bundle.baseUrl}/${media.placeholder_file}`;
}

export function resolveReplayArtifactPath(bundle: ReplayBundle, ref: string): string | null {
  const known = TRANSCRIPT_ARTIFACT_PATHS[ref];
  if (known) return known;

  const media = bundle.mediaCatalog.find((entry) => entry.ref_id === ref);
  if (media?.descriptor_file) return media.descriptor_file;

  const catalog = bundle.artifactCatalog.find((entry) => entry.ref_id === ref);
  if (catalog?.media_placeholder) {
    return catalog.media_placeholder;
  }

  if (ref.startsWith('image:derived:')) {
    const hash = ref.replace('image:derived:', '');
    return `artifacts/transcript_edit/derived_images/${hash}.json`;
  }

  return null;
}

export async function loadReplayArtifact(bundle: ReplayBundle, ref: string): Promise<ReplayArtifactResult> {
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

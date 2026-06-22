import type { ReplayBundle } from './replayTypes';
import { transcriptEditReplayPathResolver } from '../../renderers/domains/transcriptEdit/transcriptReplayPaths';

export type ReplayPathResolver = {
  id: string;
  priority?: number;
  matches: (ref: string, bundle: ReplayBundle) => boolean;
  resolve: (ref: string, bundle: ReplayBundle) => string | null;
};

const defaultReplayResolvers: ReplayPathResolver[] = [transcriptEditReplayPathResolver];

export function resolveReplayArtifactPath(
  bundle: ReplayBundle,
  ref: string,
  resolvers: ReplayPathResolver[] = defaultReplayResolvers,
): string | null {
  const media = bundle.mediaCatalog.find((entry) => entry.ref_id === ref);
  if (media?.placeholder_file) return media.placeholder_file;

  const catalog = bundle.artifactCatalog.find((entry) => entry.ref_id === ref);
  if (catalog?.media_placeholder) return catalog.media_placeholder;

  const sorted = [...resolvers].sort((a, b) => (b.priority || 0) - (a.priority || 0));
  for (const resolver of sorted) {
    if (!resolver.matches(ref, bundle)) continue;
    const path = resolver.resolve(ref, bundle);
    if (path) return path;
  }
  return null;
}

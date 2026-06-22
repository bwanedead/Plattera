import type { ReplayBundle } from './replayTypes';

export type ReplayPathResolver = {
  id: string;
  priority?: number;
  matches: (ref: string, bundle: ReplayBundle) => boolean;
  resolve: (ref: string, bundle: ReplayBundle) => string | null;
};

const transcriptEditReplayResolver: ReplayPathResolver = {
  id: 'transcript_edit.replay_paths',
  priority: 10,
  matches: (ref) =>
    ref.startsWith('transcript_edit:') ||
    ref.startsWith('image:derived:') ||
    ref.startsWith('t0:'),
  resolve: (ref, bundle) => {
    const known: Record<string, string> = {
      'transcript_edit:output': 'artifacts/transcript_edit/output/output.json',
      'transcript_edit:working': 'artifacts/transcript_edit/working/latest.json',
      'transcript_edit:working:rev:0001': 'artifacts/transcript_edit/working/rev_0001.json',
    };
    if (known[ref]) return known[ref];

    if (ref.startsWith('image:derived:')) {
      const hash = ref.replace('image:derived:', '');
      return `artifacts/transcript_edit/derived_images/${hash}.json`;
    }

    const media = bundle.mediaCatalog.find((entry) => entry.ref_id === ref);
    if (media?.descriptor_file) return media.descriptor_file;
    return null;
  },
};

const defaultReplayResolvers: ReplayPathResolver[] = [transcriptEditReplayResolver];

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

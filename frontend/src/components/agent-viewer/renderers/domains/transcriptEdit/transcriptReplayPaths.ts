import type { ReplayBundle, ReplayPathResolver } from '../../../transport/replay/replayPathResolvers';

export const transcriptEditReplayPathResolver: ReplayPathResolver = {
  id: 'domain.transcript_edit.replay_paths',
  priority: 20,
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

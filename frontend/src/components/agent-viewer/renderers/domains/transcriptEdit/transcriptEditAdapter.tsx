import type { CanvasRendererRegistration } from '../../../registry/canvasRendererRegistry';
import type { ExtendedDomainAdapter } from '../../../registry/defaultDomainAdapters';
import { TextArtifactRenderer } from '../../generic/TextArtifactRenderer';
import { extractTranscriptDraftText } from './transcriptDraftText';

export const transcriptEditDomainAdapter: ExtendedDomainAdapter = {
  id: 'domain.transcript_edit',
  label: 'Transcript edit',
  priority: 20,
  matches: (snapshot) => snapshot.run.loop_kind === 'transcript_edit',
  canvasRegistrations: [
    {
      id: 'domain.transcript_edit.draft_text',
      priority: 75,
      matches: ({ artifact }) => {
        if (artifact?.kind !== 'json') return false;
        return Boolean(extractTranscriptDraftText(artifact.json));
      },
      render: ({ artifact, selection }) => {
        if (artifact?.kind !== 'json') return null;
        const text = extractTranscriptDraftText(artifact.json);
        if (!text) return null;
        return <TextArtifactRenderer text={text} title={selection.label || artifact.ref} />;
      },
    },
  ],
};

import test from 'node:test';
import assert from 'node:assert/strict';
import { viewerEventIdentity } from './eventIdentity.ts';
import { replayStreamEventToViewerEvent } from './normalizeReplay.ts';

test('viewerEventIdentity prefers normalized __view_id', () => {
  const id = viewerEventIdentity({
    protocol: 'agent_viewer_event_v1',
    run_id: 'run-1',
    loop_kind: 'transcript_edit',
    event_type: 'turn_completed',
    payload: { __view_id: 'turn-event-7', turn_index: 7 },
  });
  assert.equal(id, 'turn-event-7');
});

test('replayStreamEventToViewerEvent sets __view_id', () => {
  const manifest = {
    schema_version: 'agent_run_replay.v1',
    fixture_id: 'fixture-1',
    source: {
      domain_id: 'transcript_edit',
      run_id: 'run-1',
      turn_count: 1,
      terminal_status: 'completed',
    },
  };
  const event = replayStreamEventToViewerEvent(
    manifest,
    {
      schema_version: 'agent_run_replay_event.v1',
      event_id: 'e1',
      sequence: 1,
      event_type: 'turn_completed',
      occurred_at_epoch_seconds: 1,
      turn_index: 3,
    },
    null,
  );
  assert.equal(event.payload?.__view_id, 'turn-event-3');
});

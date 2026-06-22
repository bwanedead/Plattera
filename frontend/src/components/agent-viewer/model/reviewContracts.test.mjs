import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeReplayBundleToSnapshot } from './normalizeReplay.ts';
import {
  activeHitlPrompt,
  isConsumedFeedbackEntry,
  resolvedPromptIdsFromEvents,
} from './normalizeHitl.ts';
import {
  extractHitlExchangesFromTurnSnapshot,
  hitlPromptsFromReplayExchanges,
  replayInteractionEventsUpToTurn,
} from './normalizeReplayInteractions.ts';
import { executeViewerAction } from '../registry/actionRegistry.ts';
import {
  acquireClientLogBridgeRef,
  getClientLogBridgeRefCount,
  releaseClientLogBridgeRef,
  resetClientLogBridgeRefCountForTests,
} from '../transport/live/clientLogBridgeRefCount.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_ROOT = path.resolve(__dirname, '../../../../../docs/ui-agent-resources/fixtures/practice-row-live-20260619-76');

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURE_ROOT, relativePath), 'utf8'));
}

function buildFixtureBundle() {
  const manifest = readJson('replay_manifest.json');
  const turnIndex = readJson('replay/turn_index.json');
  const finalState = readJson('replay/final_state.json');
  const artifactCatalog = readJson('artifacts/artifact_catalog.json');
  const feedback = readJson('interactions/feedback.json');
  return {
    fixtureId: manifest.fixture_id,
    baseUrl: '/agent-viewer-replay/practice-row-live-20260619-76',
    manifest,
    turnIndex,
    events: [],
    artifactCatalog,
    mediaCatalog: [],
    finalState,
    interactions: { feedback, messages: null },
  };
}

test('turn 0 does not project final work items or artifacts', () => {
  const bundle = buildFixtureBundle();
  const snapshot = normalizeReplayBundleToSnapshot(bundle, {
    turnIndex: 0,
    turnSnapshot: null,
    projectionStatus: 'unavailable',
  });
  assert.equal(snapshot.work_items.length, 0);
  assert.equal(snapshot.artifacts.length, 0);
  assert.equal(snapshot.run.refs.replay_projection_status, 'unavailable');
});

test('non-terminal turn without snapshot stays unavailable (no final-state leak)', () => {
  const bundle = buildFixtureBundle();
  const terminalCount = bundle.finalState.resolution_state?.items?.length ?? 0;
  assert.ok(terminalCount > 0, 'fixture should have terminal resolution items');

  const snapshot = normalizeReplayBundleToSnapshot(bundle, {
    turnIndex: 5,
    turnSnapshot: null,
    projectionStatus: 'loading',
  });
  assert.equal(snapshot.work_items.length, 0);
  assert.equal(snapshot.run.refs.replay_projection_status, 'loading');
});

test('mid-run snapshot projects only that turn state', () => {
  const bundle = buildFixtureBundle();
  const turn1 = readJson('replay/turns/turn_0001.json');
  const turn2 = readJson('replay/turns/turn_0002.json');
  const early = normalizeReplayBundleToSnapshot(bundle, {
    turnIndex: 1,
    turnSnapshot: turn1,
    projectionStatus: 'available',
  });
  const later = normalizeReplayBundleToSnapshot(bundle, {
    turnIndex: 2,
    turnSnapshot: turn2,
    projectionStatus: 'available',
  });
  assert.equal(early.work_items.length, 0);
  assert.ok(later.work_items.length > 0);
});

test('replay turn 5 exposes pending HITL prompt', () => {
  const turn5 = readJson('replay/turns/turn_0005.json');
  const exchanges = extractHitlExchangesFromTurnSnapshot(turn5);
  const prompts = hitlPromptsFromReplayExchanges(exchanges, 5);
  assert.equal(prompts.length, 1);
  assert.equal(prompts[0].prompt_id, 'hitl-ad8f78d47b3f49c29b593ca39704c173');
});

test('consumed HITL is resolved from replay interaction events', () => {
  const bundle = buildFixtureBundle();
  const turn7 = readJson('replay/turns/turn_0007.json');
  const exchanges = extractHitlExchangesFromTurnSnapshot(turn7);
  const events = replayInteractionEventsUpToTurn(bundle, 7, exchanges);
  const resolved = resolvedPromptIdsFromEvents(events);
  assert.ok(resolved.has('hitl-ad8f78d47b3f49c29b593ca39704c173'));
  const active = activeHitlPrompt(
    { hitl_prompts: hitlPromptsFromReplayExchanges(exchanges, 7), protocol: 'agent_viewer_snapshot_v1', run: { run_id: 'x', loop_kind: 'y', status: 'running' }, chapters: [], activity: [], artifacts: [], evidence: [], work_items: [], actions: [] },
    events,
    resolved,
  );
  assert.equal(active, null);
});

test('submitted feedback without consumed lifecycle does not resolve prompt', () => {
  const submittedOnly = {
    submitted_at_epoch_seconds: 1,
    prompt_id: 'hitl-test',
    choice: 'yes',
    metadata: { lifecycle: 'submitted' },
  };
  assert.equal(isConsumedFeedbackEntry(submittedOnly), false);
});

test('unknown action kinds return unsupported result', async () => {
  const result = await executeViewerAction(
    { id: 'x', label: 'X', kind: 'not_a_real_kind' },
    { select: () => undefined, refreshSnapshot: () => undefined },
  );
  assert.equal(result.ok, false);
  assert.match(result.reason || '', /Unsupported action kind/);
});

test('viewer_command with unknown command returns failure', async () => {
  const result = await executeViewerAction(
    { id: 'x', label: 'X', kind: 'viewer_command', target: { command: 'nope' } },
    { select: () => undefined, refreshSnapshot: () => undefined },
  );
  assert.equal(result.ok, false);
});

test('log bridge ref-count supports concurrent viewers safely', () => {
  resetClientLogBridgeRefCountForTests();
  acquireClientLogBridgeRef();
  acquireClientLogBridgeRef();
  assert.equal(getClientLogBridgeRefCount(), 2);
  releaseClientLogBridgeRef();
  assert.equal(getClientLogBridgeRefCount(), 1);
  releaseClientLogBridgeRef();
  assert.equal(getClientLogBridgeRefCount(), 0);
});

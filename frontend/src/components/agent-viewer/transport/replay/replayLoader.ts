import type {
  ReplayArtifactCatalogEntry,
  ReplayBundle,
  ReplayFinalState,
  ReplayManifest,
  ReplayMediaCatalogEntry,
  ReplayStreamEvent,
  ReplayTurnIndexEntry,
  ReplayTurnSnapshot,
} from './replayTypes';
import { DEFAULT_REPLAY_FIXTURE_ID, REPLAY_FIXTURES_BASE } from './replayTypes';

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Replay load failed (${response.status}): ${url}`);
  }
  return response.json() as Promise<T>;
}

async function fetchJsonl<T extends Record<string, unknown>>(url: string): Promise<T[]> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Replay load failed (${response.status}): ${url}`);
  }
  const text = await response.text();
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as T);
}

export function replayFixtureBaseUrl(fixtureId: string = DEFAULT_REPLAY_FIXTURE_ID): string {
  return `${REPLAY_FIXTURES_BASE}/${fixtureId}`;
}

export async function loadReplayBundle(fixtureId: string = DEFAULT_REPLAY_FIXTURE_ID): Promise<ReplayBundle> {
  const baseUrl = replayFixtureBaseUrl(fixtureId);
  const manifest = await fetchJson<ReplayManifest>(`${baseUrl}/replay_manifest.json`);

  const [turnIndex, events, artifactCatalog, mediaCatalog, finalState] = await Promise.all([
    fetchJson<ReplayTurnIndexEntry[]>(`${baseUrl}/replay/turn_index.json`),
    fetchJsonl<ReplayStreamEvent>(`${baseUrl}/replay/events.jsonl`),
    fetchJson<ReplayArtifactCatalogEntry[]>(`${baseUrl}/artifacts/artifact_catalog.json`),
    fetchJson<ReplayMediaCatalogEntry[]>(`${baseUrl}/artifacts/media_catalog.json`),
    fetchJson<ReplayFinalState>(`${baseUrl}/replay/final_state.json`),
  ]);

  return {
    fixtureId,
    baseUrl,
    manifest,
    turnIndex,
    events,
    artifactCatalog,
    mediaCatalog,
    finalState,
  };
}

export async function loadReplayTurnSnapshot(
  baseUrl: string,
  turnIndexEntry: ReplayTurnIndexEntry,
): Promise<ReplayTurnSnapshot> {
  const path = turnIndexEntry.file.startsWith('replay/')
    ? turnIndexEntry.file
    : `replay/${turnIndexEntry.file}`;
  return fetchJson<ReplayTurnSnapshot>(`${baseUrl}/${path}`);
}

export function findTurnEntry(bundle: ReplayBundle, turnIndex: number): ReplayTurnIndexEntry | null {
  return bundle.turnIndex.find((entry) => entry.turn_index === turnIndex) || null;
}

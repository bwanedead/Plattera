export type ArtifactLoadResult =
  | { kind: 'json'; ref: string; json: unknown; sourcePath: string }
  | { kind: 'image'; ref: string; url: string; sourcePath: string }
  | { kind: 'unresolved'; ref: string; reason: string };

export type ArtifactLoader = (ref: string) => Promise<ArtifactLoadResult>;

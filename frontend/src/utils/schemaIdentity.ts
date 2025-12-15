export interface SchemaIdentity {
  label: string;
  versionLabel?: string;
}

/**
 * Derive a user-facing label + version tag for a schema artifact.
 * Keeps all "what do we show as title/version" logic in one place so
 * JSON view, Field View, and outer headers stay consistent.
 */
export function deriveSchemaIdentity(schemaData: any | null | undefined): SchemaIdentity | null {
  if (!schemaData) return null;

  const metadata = (schemaData as any)?.metadata || {};
  const lineage = (schemaData as any)?.lineage || {};
  const schemaId = (schemaData as any)?.schema_id as string | undefined;

  const rawLabel: string =
    (metadata.schema_label as string | undefined) ||
    (metadata.dossierTitle as string | undefined) ||
    '';

  let label = rawLabel;
  if (!label) {
    if (typeof schemaId === 'string' && schemaId.length > 0) {
      label = `Schema ${schemaId.slice(0, 8)}…`;
    } else {
      label = 'Schema';
    }
  }

  let versionLabel: string | undefined =
    (metadata.version_label as string | undefined) ||
    (lineage.version_label as string | undefined);

  // Best-effort inference from id suffix when explicit metadata is missing.
  if (!versionLabel && typeof schemaId === 'string') {
    if (schemaId.endsWith('_v2')) {
      versionLabel = 'v2';
    } else if (schemaId.endsWith('_v1')) {
      versionLabel = 'v1';
    }
  }

  // As long as we conceptually support v1/v2, make the
  // baseline explicit: if we still don't know, assume v1.
  if (!versionLabel) {
    versionLabel = 'v1';
  }

  return { label, versionLabel };
}


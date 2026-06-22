export function extractGenericText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value;
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  for (const key of ['text', 'content', 'body']) {
    if (typeof record[key] === 'string' && record[key]) return record[key] as string;
  }
  return null;
}

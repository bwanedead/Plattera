import React from 'react';
import { deriveSchemaIdentity, SchemaIdentity } from '../../utils/schemaIdentity';

interface SchemaHeaderStripProps {
  schemaData: any | null;
  identityOverride?: SchemaIdentity;
  rightContent?: React.ReactNode;
  size?: 'default' | 'compact';
}

/**
 * Shared "schema title + version" header strip used by JSON and Field views.
 * This keeps schema identity presentation consistent across tabs.
 */
export const SchemaHeaderStrip: React.FC<SchemaHeaderStripProps> = ({
  schemaData,
  identityOverride,
  rightContent,
  size = 'default',
}) => {
  const identity = identityOverride || deriveSchemaIdentity(schemaData || null);
  if (!identity) return null;

  const { label, versionLabel } = identity;
  const fontSize = size === 'compact' ? '0.8rem' : '0.9rem';

  return (
    <div
      className="schema-header-strip"
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: size === 'compact' ? 8 : 12,
        paddingBottom: size === 'default' ? 6 : 4,
        borderBottom: size === 'default' ? '1px solid #1f2937' : 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize }}>
        <span>{label}</span>
        {versionLabel && (
          <span
            className="version-tag"
            style={{
              fontSize: '0.75rem',
              padding: '2px 8px',
              borderRadius: 12,
              background: '#111827',
              color: '#e5e7eb',
              border: '1px solid #374151',
            }}
            title={`Schema version: ${versionLabel}`}
          >
            {String(versionLabel).toUpperCase()}
          </span>
        )}
      </div>
      {rightContent && (
        <div
          className="schema-header-actions"
          style={{ display: 'flex', alignItems: 'center', gap: 8 }}
        >
          {rightContent}
        </div>
      )}
    </div>
  );
};


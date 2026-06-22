import React from 'react';

type JsonTreeViewProps = {
  value: unknown;
  maxDepth?: number;
};

export function JsonTreeView({ value, maxDepth = 6 }: JsonTreeViewProps) {
  return <div className="av-json-tree">{renderNode('root', value, 0, maxDepth)}</div>;
}

function renderNode(key: string, value: unknown, depth: number, maxDepth: number): React.ReactNode {
  if (depth >= maxDepth) {
    return <div className="av-json-leaf av-json-truncated">{key}: …</div>;
  }

  if (value === null || value === undefined) {
    return (
      <div className="av-json-leaf">
        <span className="av-json-key">{key}</span>
        <span className="av-json-null">null</span>
      </div>
    );
  }

  if (typeof value !== 'object') {
    return (
      <div className="av-json-leaf">
        <span className="av-json-key">{key}</span>
        <span className="av-json-value">{formatPrimitive(value)}</span>
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <details className="av-json-node" open={depth < 2}>
        <summary>
          <span className="av-json-key">{key}</span>
          <span className="av-json-meta">[{value.length}]</span>
        </summary>
        <div className="av-json-children">
          {value.slice(0, 40).map((item, index) => renderNode(String(index), item, depth + 1, maxDepth))}
          {value.length > 40 ? <div className="av-json-leaf av-json-truncated">… {value.length - 40} more</div> : null}
        </div>
      </details>
    );
  }

  const entries = Object.entries(value as Record<string, unknown>);
  return (
    <details className="av-json-node" open={depth < 2}>
      <summary>
        <span className="av-json-key">{key}</span>
        <span className="av-json-meta">{`{${entries.length}}`}</span>
      </summary>
      <div className="av-json-children">
        {entries.slice(0, 40).map(([childKey, childValue]) => renderNode(childKey, childValue, depth + 1, maxDepth))}
        {entries.length > 40 ? <div className="av-json-leaf av-json-truncated">… {entries.length - 40} more</div> : null}
      </div>
    </details>
  );
}

function formatPrimitive(value: unknown): string {
  if (typeof value === 'string') return value.length > 240 ? `${value.slice(0, 240)}…` : value;
  return String(value);
}

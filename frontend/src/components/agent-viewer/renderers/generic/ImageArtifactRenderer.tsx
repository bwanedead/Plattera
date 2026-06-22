import React from 'react';

type ImageArtifactRendererProps = {
  url: string;
  title?: string | null;
  meta?: Record<string, unknown>;
};

export function ImageArtifactRenderer({ url, title, meta }: ImageArtifactRendererProps) {
  return (
    <div className="av-image-renderer">
      {title ? <div className="av-image-title">{title}</div> : null}
      <div className="av-image-frame">
        <img src={url} alt={title || 'Artifact image'} className="av-image" />
      </div>
      {meta ? (
        <div className="av-image-meta">
          {Object.entries(meta)
            .slice(0, 6)
            .map(([key, value]) => (
              <span key={key} className="av-meta-chip">
                {key}: {String(value)}
              </span>
            ))}
        </div>
      ) : null}
    </div>
  );
}

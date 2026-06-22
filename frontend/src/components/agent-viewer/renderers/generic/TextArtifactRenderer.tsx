import React from 'react';

type TextArtifactRendererProps = {
  text: string;
  title?: string | null;
};

export function TextArtifactRenderer({ text, title }: TextArtifactRendererProps) {
  return (
    <div className="av-text-renderer">
      {title ? <div className="av-text-title">{title}</div> : null}
      <pre className="av-text-body">{text}</pre>
    </div>
  );
}

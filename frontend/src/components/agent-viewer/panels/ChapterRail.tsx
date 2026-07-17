import React from 'react';
import type { AgentViewerRunChapter } from '../../../services/agentViewerApi';

type ChapterRailProps = {
  chapters: AgentViewerRunChapter[];
  activeChapterId: string | null;
  onSelectChapter: (chapter: AgentViewerRunChapter) => void;
};

export function ChapterRail({ chapters, activeChapterId, onSelectChapter }: ChapterRailProps) {
  if (!chapters.length) return null;

  return (
    <nav className="av-chapter-rail" aria-label="Run chapters">
      <span className="av-chapter-rail-label">Chapters</span>
      <div className="av-chapter-rail-items">
        {chapters.map((chapter) => {
          const active = chapter.id === activeChapterId;
          return (
            <button
              key={chapter.id}
              type="button"
              className={`av-chapter-chip ${active ? 'is-active' : ''}`}
              onClick={() => onSelectChapter(chapter)}
              title={chapter.title}
            >
              <span className="av-chapter-chip-title">{chapter.title}</span>
              <span className="av-chapter-chip-status">{chapter.status}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

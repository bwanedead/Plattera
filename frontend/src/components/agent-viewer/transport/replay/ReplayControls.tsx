import React from 'react';
import type { ReplayPlaybackState } from '../../hooks/useAgentViewerReplay';

type ReplayControlsProps = {
  playback: ReplayPlaybackState;
  onPlay: () => void;
  onPause: () => void;
  onStepForward: () => void;
  onStepBackward: () => void;
  onScrub: (turn: number) => void;
  onRestart: () => void;
};

export function ReplayControls({
  playback,
  onPlay,
  onPause,
  onStepForward,
  onStepBackward,
  onScrub,
  onRestart,
}: ReplayControlsProps) {
  const { currentTurn, maxTurn, isPlaying } = playback;

  return (
    <div className="av-replay-controls">
      <div className="av-replay-buttons">
        <button type="button" className="av-button" onClick={onStepBackward} disabled={currentTurn <= 0}>
          ◀
        </button>
        {isPlaying ? (
          <button type="button" className="av-button av-button-primary" onClick={onPause}>
            Pause
          </button>
        ) : (
          <button type="button" className="av-button av-button-primary" onClick={onPlay}>
            Play
          </button>
        )}
        <button type="button" className="av-button" onClick={onStepForward} disabled={currentTurn >= maxTurn}>
          ▶
        </button>
        <button type="button" className="av-button av-button-ghost" onClick={onRestart}>
          Restart
        </button>
      </div>
      <div className="av-replay-scrub">
        <label className="av-replay-label" htmlFor="av-replay-range">
          Turn {currentTurn} / {maxTurn}
        </label>
        <input
          id="av-replay-range"
          type="range"
          min={0}
          max={maxTurn}
          value={currentTurn}
          onChange={(event) => onScrub(Number(event.target.value))}
          className="av-replay-range"
        />
      </div>
    </div>
  );
}

import React from 'react';
import type { ViewerSelection } from './selectionTypes';

export function useViewerSelection(initial: ViewerSelection | null = null) {
  const [selection, setSelection] = React.useState<ViewerSelection | null>(initial);
  const [followLive, setFollowLive] = React.useState(true);

  const select = React.useCallback((next: ViewerSelection | null) => {
    setSelection(next);
    if (next) setFollowLive(false);
  }, []);

  const selectLive = React.useCallback((next: ViewerSelection | null) => {
    setSelection(next);
  }, []);

  const resumeFollowLive = React.useCallback(() => {
    setFollowLive(true);
    setSelection(null);
  }, []);

  return {
    selection,
    followLive,
    select,
    selectLive,
    resumeFollowLive,
    setFollowLive,
  };
}

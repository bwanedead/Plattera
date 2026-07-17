import React from 'react';
import type { AgentViewerEvent } from '../../../services/agentViewerApi';
import { viewerEventIdentity, viewerEventLabel } from '../model/eventIdentity';
import type { ViewerSelection } from '../selection/selectionTypes';

type ActivityTimelineProps = {
  events: AgentViewerEvent[];
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

function delegateSignal(event: AgentViewerEvent): boolean {
  const actions = event.payload?.actions;
  if (Array.isArray(actions)) {
    return actions.some((entry) => {
      if (!entry || typeof entry !== 'object') return false;
      const actionType = String(
        (entry as Record<string, unknown>).action_type ||
          (entry as Record<string, unknown>).tool_id ||
          '',
      ).toLowerCase();
      return actionType.includes('delegate');
    });
  }
  return event.event_type.toLowerCase().includes('delegate');
}

export function ActivityTimeline({ events, selection, onSelect }: ActivityTimelineProps) {
  if (!events.length) {
    return <div className="av-empty-panel">No activity yet. Start replay or connect to a live run.</div>;
  }

  return (
    <div className="av-activity-timeline">
      {events
        .slice()
        .reverse()
        .map((event) => {
          const id = viewerEventIdentity(event);
          const selected = selection?.kind === 'event' && selection.id === id;
          const hasDelegate = delegateSignal(event);
          return (
            <button
              key={id}
              type="button"
              className={`av-activity-row ${selected ? 'is-selected' : ''}`}
              onClick={() =>
                onSelect({
                  kind: 'event',
                  id,
                  label: viewerEventLabel(event),
                  payload: { event },
                })
              }
            >
              <div className="av-activity-row-top">
                <span className="av-activity-turn">
                  {typeof event.payload?.turn_index === 'number' ? `T${event.payload.turn_index}` : event.event_type}
                </span>
                <span className="av-activity-stage-row">
                  {hasDelegate ? <span className="av-activity-delegate">delegate</span> : null}
                  <span className="av-activity-stage">{event.status?.stage || 'event'}</span>
                </span>
              </div>
              <div className="av-activity-line1">{event.status?.line1 || event.event_type}</div>
              {event.status?.line2 ? <div className="av-activity-line2">{event.status.line2}</div> : null}
            </button>
          );
        })}
    </div>
  );
}

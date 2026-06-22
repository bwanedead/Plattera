import React from 'react';
import type { AgentViewerEvent } from '../../../services/agentViewerApi';
import type { ViewerSelection } from '../selection/selectionTypes';

type ActivityTimelineProps = {
  events: AgentViewerEvent[];
  selection: ViewerSelection | null;
  onSelect: (selection: ViewerSelection) => void;
};

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
          const id = eventDedupeId(event);
          const selected = selection?.kind === 'event' && selection.id === id;
          const turnIndex = event.payload?.turn_index;
          return (
            <button
              key={id}
              type="button"
              className={`av-activity-row ${selected ? 'is-selected' : ''}`}
              onClick={() =>
                onSelect({
                  kind: 'event',
                  id,
                  label: event.status?.line1 || event.event_type,
                  payload: {
                    event,
                    turn_index: turnIndex ?? null,
                  },
                })
              }
            >
              <div className="av-activity-row-top">
                <span className="av-activity-turn">
                  {typeof turnIndex === 'number' ? `T${turnIndex}` : event.event_type}
                </span>
                <span className="av-activity-stage">{event.status?.stage || 'event'}</span>
              </div>
              <div className="av-activity-line1">{event.status?.line1 || event.event_type}</div>
              {event.status?.line2 ? <div className="av-activity-line2">{event.status.line2}</div> : null}
            </button>
          );
        })}
    </div>
  );
}

function eventDedupeId(event: AgentViewerEvent): string {
  const turn = event.payload?.turn_index;
  if (typeof turn === 'number') return `turn-event-${turn}`;
  if (typeof event.seq === 'number') return `seq-${event.seq}`;
  return `${event.event_type}-${event.timestamp_epoch_seconds ?? 'na'}`;
}

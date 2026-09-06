import { useEffect, useRef, useState } from "react";
import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";

export type EventStreamState =
  | "connecting"
  | "live"
  | "reconnecting"
  | "closed";

export function useEventStream({
  afterSeq,
  enabled,
  epicId,
  onEvent,
}: {
  afterSeq: number;
  enabled: boolean;
  epicId: string;
  onEvent: (event: CoordinationEvent) => void;
}) {
  const onEventRef = useRef(onEvent);
  const [state, setState] = useState<EventStreamState>("closed");
  const [lastSequence, setLastSequence] = useState(afterSeq);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!enabled || !epicId) {
      setState("closed");
      return;
    }
    let active = true;
    const source = new EventSource(
      `/api/coordination/stream?epic_id=${encodeURIComponent(epicId)}&after_seq=${afterSeq}`,
    );
    setLastSequence(afterSeq);
    setState("connecting");
    source.onopen = () => {
      if (active) setState("live");
    };
    source.onerror = () => {
      if (active) setState("reconnecting");
    };
    const receive = (message: MessageEvent<string>) => {
      try {
        const event = JSON.parse(message.data) as CoordinationEvent;
        const sequence = Number(message.lastEventId || event.seq);
        if (!Number.isFinite(sequence) || sequence <= 0) return;
        setLastSequence((current) => Math.max(current, sequence));
        onEventRef.current(event);
      } catch {
        // A malformed SSE frame is ignored; the next id-tagged frame remains resumable.
      }
    };
    source.addEventListener("coordination", receive as EventListener);
    return () => {
      active = false;
      source.removeEventListener("coordination", receive as EventListener);
      source.close();
      setState("closed");
    };
  }, [afterSeq, enabled, epicId]);

  return { lastSequence, state };
}

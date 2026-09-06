import { History } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import {
  formatTimelineMessages,
  type CoordinationEvent,
  type TimelineEntry,
} from "@/features/workspace/lib/formatTimelineMessages";
import { useAnchoredScroll } from "@/features/workspace/lib/useAnchoredScroll";
import { TIMELINE_EVENT_LIMIT } from "@/shared/api/queries";
import { TimelineDaySeparator } from "@/features/workspace/timeline/day-separator";
import { TimelineGroup } from "@/features/workspace/timeline/timeline-group";
import { TimelineUnreadDivider } from "@/features/workspace/timeline/unread-divider";
import { Button } from "@/shared/ui/button";
import { TimelineSkeleton } from "@/shared/ui/TimelineSkeleton";
import { UnreadPill } from "@/shared/ui/UnreadPill";
import { VirtualizedList } from "@/shared/ui/VirtualizedList";

const PAGE_SIZE = 200;

function TimelineEntryView({ entry }: { entry: TimelineEntry }) {
  if (entry.kind === "day") return <TimelineDaySeparator label={entry.label} />;
  if (entry.kind === "unread")
    return <TimelineUnreadDivider count={entry.count} />;
  return <TimelineGroup group={entry} />;
}

export function TimelineList({
  epicId,
  events,
  lastSeenSeq,
  loading,
  truncated = false,
}: {
  epicId: string;
  events: CoordinationEvent[];
  lastSeenSeq: number;
  loading: boolean;
  /** The server returned a full page, so older events exist but are not here. */
  truncated?: boolean;
}) {
  const [visibleStart, setVisibleStart] = useState<number | null>(null);
  const [groupBreakSeqs, setGroupBreakSeqs] = useState<Set<number>>(
    () => new Set(),
  );
  const firstEventEpicId = events[0]?.epic_id;

  // biome-ignore lint/correctness/useExhaustiveDependencies: epicId is the reset signal for pagination-owned group boundaries.
  useEffect(() => {
    setGroupBreakSeqs(new Set());
  }, [epicId]);

  useLayoutEffect(() => {
    setVisibleStart((current) => {
      if (!firstEventEpicId || firstEventEpicId !== epicId) return null;
      return current ?? Math.max(0, events.length - PAGE_SIZE);
    });
  }, [epicId, events.length, firstEventEpicId]);

  const resolvedStart = visibleStart ?? Math.max(0, events.length - PAGE_SIZE);
  const visibleEvents = events.slice(resolvedStart);
  const firstUnreadSeq = events.find((event) => event.seq > lastSeenSeq)?.seq;
  const unreadCount = firstUnreadSeq
    ? events.filter((event) => event.seq >= firstUnreadSeq).length
    : 0;
  const entries = useMemo(
    () =>
      formatTimelineMessages(visibleEvents, {
        firstUnreadSeq,
        groupBreakSeqs,
        unreadCount,
      }),
    [firstUnreadSeq, groupBreakSeqs, unreadCount, visibleEvents],
  );
  const eventKeys = visibleEvents.map((event) => event.event_id);
  const { listRef, newMessageCount, onScroll, scrollToBottom, shift } =
    useAnchoredScroll({
      channelId: epicId,
      entryKeys: eventKeys,
      itemCount: entries.length,
    });

  const loadOlder = () => {
    if (resolvedStart === 0) return;
    const firstVisibleSeq = visibleEvents[0]?.seq;
    if (firstVisibleSeq) {
      setGroupBreakSeqs((current) => new Set([...current, firstVisibleSeq]));
    }
    setVisibleStart(Math.max(0, resolvedStart - PAGE_SIZE));
  };

  if (loading) return <TimelineSkeleton />;
  if (events.length === 0) {
    return (
      <div className="flex h-full min-h-80 items-center justify-center p-8 text-center">
        <div className="max-w-sm">
          <History
            aria-hidden="true"
            className="mx-auto mb-3 size-8 text-primary"
          />
          <h2 className="font-semibold">История пока пуста</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Первое сообщение станет началом видимого журнала этого эпика.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="flex min-h-11 items-center justify-between gap-3 border-b border-border-soft px-3 py-2 sm:px-4">
        <p className="text-xs text-muted-foreground">
          Показано {visibleEvents.length} из {events.length}
        </p>
        {resolvedStart > 0 ? (
          <Button onClick={loadOlder} size="sm" type="button" variant="ghost">
            Показать более ранние ({resolvedStart})
          </Button>
        ) : truncated ? (
          <span className="text-xs text-warning">
            Показаны последние {TIMELINE_EVENT_LIMIT} событий
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Начало истории</span>
        )}
      </div>
      <div className="min-h-0 flex-1">
        <VirtualizedList
          ariaLabel="Обсуждение эпика"
          getItemKey={(entry) => entry.key}
          items={entries}
          listRef={listRef}
          onScroll={onScroll}
          renderItem={(entry) => <TimelineEntryView entry={entry} />}
          shift={shift}
        />
      </div>
      {newMessageCount > 0 ? (
        <div className="pointer-events-none absolute bottom-4 left-1/2 z-10 -translate-x-1/2">
          <UnreadPill count={newMessageCount} onClick={scrollToBottom} />
        </div>
      ) : null}
    </div>
  );
}

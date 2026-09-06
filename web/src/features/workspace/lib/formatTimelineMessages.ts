/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

export interface ArtifactReference {
  path: string;
  digest: string;
  media_type: string;
}

export interface CoordinationEvent {
  seq: number;
  event_id: string;
  project_id: string;
  epic_id: string;
  beads_issue_id: string | null;
  dispatch_id: string | null;
  runtime_session_id: string | null;
  author_kind: string;
  event_kind: string;
  body_text: string;
  artifact_refs: ArtifactReference[];
  reply_to: string | null;
  created_at: string;
}

export interface TimelineDayEntry {
  kind: "day";
  key: string;
  dayKey: string;
  label: string;
}

export interface TimelineUnreadEntry {
  kind: "unread";
  key: string;
  firstUnreadSeq: number;
  count: number;
}

export interface TimelineGroupEntry {
  kind: "group";
  key: string;
  authorKey: string;
  authorKind: string;
  events: CoordinationEvent[];
}

export type TimelineEntry =
  | TimelineDayEntry
  | TimelineUnreadEntry
  | TimelineGroupEntry;

const GROUP_WINDOW_MS = 5 * 60 * 1_000;

function timestamp(event: CoordinationEvent) {
  const value = Date.parse(event.created_at);
  return Number.isFinite(value) ? value : 0;
}

function dayKey(event: CoordinationEvent) {
  return new Date(timestamp(event)).toISOString().slice(0, 10);
}

function dayLabel(key: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${key}T00:00:00Z`));
}

function authorKey(event: CoordinationEvent) {
  if (event.author_kind === "runtime") {
    return [event.author_kind, event.runtime_session_id, event.dispatch_id]
      .filter(Boolean)
      .join(":");
  }
  return event.author_kind || "system";
}

export function mergeCoordinationEvents(
  current: CoordinationEvent[],
  incoming: CoordinationEvent[],
): CoordinationEvent[] {
  if (incoming.length === 0) return current;
  const eventIds = new Set(current.map((event) => event.event_id));
  const sequences = new Set(current.map((event) => event.seq));
  const additions = incoming.filter(
    (event) => !eventIds.has(event.event_id) && !sequences.has(event.seq),
  );
  if (additions.length === 0) return current;
  return [...current, ...additions].sort((left, right) => left.seq - right.seq);
}

export function formatTimelineMessages(
  source: CoordinationEvent[],
  options: {
    lastSeenSeq?: number;
    firstUnreadSeq?: number;
    unreadCount?: number;
    groupBreakSeqs?: ReadonlySet<number>;
  } = {},
): TimelineEntry[] {
  const events = [...source].sort((left, right) => left.seq - right.seq);
  const firstUnreadSeq =
    options.firstUnreadSeq ??
    events.find(
      (event) => event.seq > (options.lastSeenSeq ?? Number.POSITIVE_INFINITY),
    )?.seq;
  const unreadCount =
    options.unreadCount ??
    (firstUnreadSeq
      ? events.filter((event) => event.seq >= firstUnreadSeq).length
      : 0);
  const entries: TimelineEntry[] = [];
  let currentDay = "";
  let group: TimelineGroupEntry | null = null;
  let unreadInserted = false;

  for (const event of events) {
    const nextDay = dayKey(event);
    if (nextDay !== currentDay) {
      currentDay = nextDay;
      group = null;
      entries.push({
        kind: "day",
        key: `day:${nextDay}`,
        dayKey: nextDay,
        label: dayLabel(nextDay),
      });
    }

    if (options.groupBreakSeqs?.has(event.seq)) group = null;

    if (
      firstUnreadSeq &&
      unreadCount > 0 &&
      !unreadInserted &&
      event.seq >= firstUnreadSeq
    ) {
      group = null;
      unreadInserted = true;
      entries.push({
        kind: "unread",
        key: `unread:${firstUnreadSeq}`,
        firstUnreadSeq,
        count: unreadCount,
      });
    }

    const nextAuthor = authorKey(event);
    const previous = group?.events.at(-1);
    const canJoin =
      group !== null &&
      group.authorKey === nextAuthor &&
      previous !== undefined &&
      timestamp(event) - timestamp(previous) <= GROUP_WINDOW_MS;
    if (canJoin && group) {
      group.events.push(event);
      continue;
    }

    group = {
      kind: "group",
      key: `group:${event.event_id}`,
      authorKey: nextAuthor,
      authorKind: event.author_kind || "system",
      events: [event],
    };
    entries.push(group);
  }

  return entries;
}

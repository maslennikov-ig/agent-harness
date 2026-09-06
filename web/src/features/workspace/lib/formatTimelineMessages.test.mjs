/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  formatTimelineMessages,
  mergeCoordinationEvents,
} from "./formatTimelineMessages.ts";

function event(seq, overrides = {}) {
  return {
    seq,
    event_id: `event-${seq}`,
    project_id: "project-console",
    epic_id: "epic-one",
    beads_issue_id: null,
    dispatch_id: null,
    runtime_session_id: null,
    author_kind: "user",
    event_kind: "message",
    body_text: `message ${seq}`,
    artifact_refs: [],
    reply_to: null,
    created_at: `2026-08-12T10:${String(seq).padStart(2, "0")}:00Z`,
    ...overrides,
  };
}

test("consecutive events from one author inside five minutes form one group", () => {
  const entries = formatTimelineMessages([
    event(1, { created_at: "2026-08-12T10:00:00Z" }),
    event(2, { created_at: "2026-08-12T10:04:59Z" }),
    event(3, { author_kind: "agent", created_at: "2026-08-12T10:05:00Z" }),
  ]);

  assert.deepEqual(
    entries.map((entry) => entry.kind),
    ["day", "group", "group"],
  );
  assert.deepEqual(
    entries[1].events.map((item) => item.seq),
    [1, 2],
  );
  assert.deepEqual(
    entries[2].events.map((item) => item.seq),
    [3],
  );
});

test("a day boundary starts a separator and cannot bridge an author group", () => {
  const entries = formatTimelineMessages([
    event(1, { created_at: "2026-08-12T23:59:00Z" }),
    event(2, { created_at: "2026-08-13T00:01:00Z" }),
  ]);

  assert.deepEqual(
    entries.map((entry) => entry.kind),
    ["day", "group", "day", "group"],
  );
  assert.notEqual(entries[0].dayKey, entries[2].dayKey);
});

test("the unread divider is fixed before the first event beyond the captured cursor", () => {
  const entries = formatTimelineMessages([event(1), event(2), event(3)], {
    lastSeenSeq: 1,
  });

  assert.deepEqual(
    entries.map((entry) => entry.kind),
    ["day", "group", "unread", "group"],
  );
  assert.equal(entries[2].firstUnreadSeq, 2);
  assert.equal(entries[2].count, 2);
});

test("the unread divider remains visible when the first unread event is before the rendered window", () => {
  const entries = formatTimelineMessages([event(201), event(202)], {
    firstUnreadSeq: 2,
    unreadCount: 201,
  });

  assert.deepEqual(
    entries.map((entry) => entry.kind),
    ["day", "unread", "group"],
  );
  assert.equal(entries[1].firstUnreadSeq, 2);
  assert.equal(entries[1].count, 201);
});

test("incremental merge preserves old event objects and rejects replayed ids", () => {
  const first = event(1);
  const second = event(2);
  const merged = mergeCoordinationEvents([first], [first, second]);

  assert.equal(merged.length, 2);
  assert.equal(merged[0], first);
  assert.equal(merged[1], second);
  assert.equal(mergeCoordinationEvents(merged, [second]), merged);
});

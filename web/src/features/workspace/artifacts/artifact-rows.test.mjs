import assert from "node:assert/strict";
import test from "node:test";

import { artifactRows } from "./artifact-rows.ts";

const ref = (
  path,
  digest = "b".repeat(64),
  mediaType = "application/json",
) => ({
  path,
  digest,
  media_type: mediaType,
});

const event = (eventId, refs) => ({
  event_id: eventId,
  artifact_refs: refs,
});

test("every reference keeps a row in source order", () => {
  const rows = artifactRows([
    event("event-1", [ref("a.json"), ref("b.json")]),
    event("event-2", [ref("c.json")]),
  ]);

  assert.deepEqual(
    rows.map((row) => row.artifact.path),
    ["a.json", "b.json", "c.json"],
  );
});

test("two identical references inside one event stay two distinct rows", () => {
  const rows = artifactRows([
    event("event-1", [ref("plan.md"), ref("plan.md")]),
  ]);

  assert.equal(rows.length, 2);
  assert.notEqual(rows[0].key, rows[1].key);
});

test("the same reference in two events stays two distinct rows", () => {
  const rows = artifactRows([
    event("event-1", [ref("plan.md")]),
    event("event-2", [ref("plan.md")]),
  ]);

  assert.equal(rows.length, 2);
  assert.notEqual(rows[0].key, rows[1].key);
});

test("no two rows ever share a key, whatever the repetition", () => {
  const rows = artifactRows([
    event("event-1", [ref("plan.md"), ref("plan.md"), ref("spec.md")]),
    event("event-2", [ref("plan.md"), ref("plan.md")]),
  ]);

  assert.equal(rows.length, 5);
  assert.equal(new Set(rows.map((row) => row.key)).size, rows.length);
});

test("references that differ only by media type are not folded together", () => {
  const rows = artifactRows([
    event("event-1", [
      ref("plan.md", "e".repeat(64), "text/markdown"),
      ref("plan.md", "e".repeat(64), "text/plain"),
    ]),
  ]);

  assert.equal(new Set(rows.map((row) => row.key)).size, 2);
});

test("an event without references contributes no rows", () => {
  assert.deepEqual(artifactRows([event("event-1", [])]), []);
});

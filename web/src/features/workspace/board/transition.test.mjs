import assert from "node:assert/strict";
import test from "node:test";

import { buildBoardTransition } from "./transition.ts";

const scope = {
  projectId: "project-abc",
  epicId: "epic-abc",
};

const card = {
  id: "project-abc.5",
  column: "ready",
  targets: ["running"],
  dependency_blocked: false,
  blocked_by: [],
};

test("an allowed move produces only the existing server transition fields", () => {
  assert.deepEqual(buildBoardTransition(scope, card, "running"), {
    project_id: "project-abc",
    epic_id: "epic-abc",
    issue_id: "project-abc.5",
    from_column: "ready",
    to_column: "running",
  });
});

test("a target outside the server-projected allowlist is refused locally", () => {
  assert.throws(
    () => buildBoardTransition(scope, card, "done"),
    /does not allow ready → done/,
  );
});

test("a dependency-held card names its blocker and cannot build a request", () => {
  assert.throws(
    () =>
      buildBoardTransition(
        scope,
        {
          ...card,
          dependency_blocked: true,
          blocked_by: ["project-abc.4"],
          targets: [],
        },
        "running",
      ),
    /project-abc\.4/,
  );
});

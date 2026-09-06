import assert from "node:assert/strict";
import test from "node:test";

import { planningCopy } from "./planning-copy.ts";

test("the specification tab agrees in gender and case like the legacy panel", () => {
  assert.deepEqual(planningCopy("specification"), {
    accepted: "Принятая спецификация",
    register: "Зарегистрировать спецификацию",
  });
});

test("the plan tab keeps its own agreeing forms", () => {
  assert.deepEqual(planningCopy("plan"), {
    accepted: "Принятый план",
    register: "Зарегистрировать план",
  });
});

test("no tab renders a nominative noun after a verb or a mismatched adjective", () => {
  for (const kind of ["specification", "plan"]) {
    const copy = planningCopy(kind);
    assert.ok(
      !copy.register.endsWith("спецификация"),
      `${kind} register form must not be nominative`,
    );
    assert.ok(
      !copy.accepted.startsWith("Принятый спецификация"),
      `${kind} accepted form must agree in gender`,
    );
  }
});

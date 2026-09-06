import assert from "node:assert/strict";
import test from "node:test";

import { workspaceMetaNote } from "./workspaceMetaNote.ts";

test("a writable workspace states the schema and the paid-action rule", () => {
  assert.equal(
    workspaceMetaNote({
      enabled: true,
      flag: "ORCH_COORDINATION",
      schema_version: 1,
    }),
    "Схема 1. Запуск runtime — только явным подтверждением; это платное действие.",
  );
});

test("a read-only workspace names the flag that turns mutations on", () => {
  assert.equal(
    workspaceMetaNote({
      enabled: false,
      flag: "ORCH_COORDINATION",
      schema_version: 2,
    }),
    "Схема 2. Мутации выключены: запустите панель с ORCH_COORDINATION=1.",
  );
});

test("an unloaded overview says nothing rather than guessing a schema", () => {
  assert.equal(workspaceMetaNote(undefined), "");
});

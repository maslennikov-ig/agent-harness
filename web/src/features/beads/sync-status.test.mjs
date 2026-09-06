import assert from "node:assert/strict";
import test from "node:test";

import { syncStatusQueryErrorView, syncStatusView } from "./sync-status.ts";

const healthy = {
  enrolled: true,
  hooks_installed: true,
  inflight: false,
  last_error: "",
  oldest_pending_age: null,
  pending_count: 0,
  pin_mismatch: "",
  pin_valid: true,
  state_error: "",
  state_status: "ready",
};

test("sync errors win and are announced without rendering their raw body", () => {
  for (const status of [
    {
      ...healthy,
      last_error: "Authorization: secret-token-value",
      pending_count: 3,
    },
    {
      ...healthy,
      state_error: "corrupt body: secret-token-value",
      state_status: "error",
    },
  ]) {
    const view = syncStatusView(status);

    assert.deepEqual(view, {
      className: "text-destructive",
      role: "alert",
      text: "Синхронизация с GitHub: ошибка. Проверьте журнал.",
    });
    assert.ok(!view.text.includes("secret-token-value"));
  }
});

test("legacy receipts and pin drift require reenrollment", () => {
  for (const status of [
    { ...healthy, state_status: "reenrollment_required" },
    { ...healthy, pin_valid: false, pin_mismatch: "digest changed" },
    { ...healthy, enrolled: false, state_status: "not_enrolled" },
  ]) {
    assert.deepEqual(syncStatusView(status), {
      className: "text-warning",
      text: "Синхронизация с GitHub: требуется повторное подключение.",
    });
  }
});

test("excluded repositories explain the safe known reason without reenrollment copy", () => {
  assert.deepEqual(
    syncStatusView({
      ...healthy,
      enrolled: false,
      exclusion_reason: "no_github_origin",
      state_status: "excluded",
    }),
    {
      className: "text-muted-foreground",
      text: "Синхронизация с GitHub: репозиторий намеренно исключён — не задан GitHub origin.",
    },
  );
  assert.deepEqual(
    syncStatusView({
      ...healthy,
      enrolled: false,
      exclusion_reason: "configured",
      state_status: "excluded",
    }),
    {
      className: "text-muted-foreground",
      text: "Синхронизация с GitHub: репозиторий намеренно исключён.",
    },
  );
});

test("a failed status query is a compact alert", () => {
  assert.deepEqual(syncStatusQueryErrorView(), {
    className: "text-destructive",
    role: "alert",
    text: "Не удалось получить статус синхронизации с GitHub.",
  });
});

test("active and queued work use concise operational copy", () => {
  assert.equal(
    syncStatusView({ ...healthy, inflight: true, inflight_stale: false }).text,
    "Синхронизация с GitHub: синхронизация выполняется.",
  );
  assert.deepEqual(
    syncStatusView({ ...healthy, inflight: true, inflight_stale: true }),
    {
      className: "text-warning",
      text: "Синхронизация с GitHub задержалась и требует внимания.",
    },
  );
  assert.deepEqual(syncStatusView({ ...healthy, pending_count: 2 }), {
    className: "text-muted-foreground",
    text: "Синхронизация с GitHub: в очереди 2.",
  });
  assert.deepEqual(
    syncStatusView({
      ...healthy,
      pending_count: 2,
      oldest_pending_age: 901,
    }),
    {
      className: "text-warning",
      text: "Синхронизация с GitHub: в очереди 2, обработка задерживается.",
    },
  );
});

test("healthy state says the synchronizer is working", () => {
  assert.deepEqual(syncStatusView(healthy), {
    className: "text-muted-foreground",
    text: "Синхронизация с GitHub: синхронизация работает.",
  });
});

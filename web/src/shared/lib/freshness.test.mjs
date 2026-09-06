import assert from "node:assert/strict";
import test from "node:test";

import { formatFreshness } from "./freshness.ts";

test("freshness reads in seconds, minutes, hours and days", () => {
  assert.equal(formatFreshness(0), "обновлено только что");
  assert.equal(formatFreshness(4), "обновлено только что");
  assert.equal(formatFreshness(5), "обновлено 5 с назад");
  assert.equal(formatFreshness(59), "обновлено 59 с назад");
  assert.equal(formatFreshness(60), "обновлено 1 мин назад");
  assert.equal(formatFreshness(3599), "обновлено 59 мин назад");
  assert.equal(formatFreshness(3600), "обновлено 1 ч назад");
  assert.equal(formatFreshness(86_400), "обновлено 1 дн назад");
});

/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  captureScrollAnchor,
  isPrependDelta,
  restoreScrollAnchor,
} from "./useAnchoredScroll.ts";

function row(id, top, bottom) {
  return {
    dataset: { timelineKey: id },
    getBoundingClientRect: () => ({ top, bottom }),
  };
}

function container(rows, overrides = {}) {
  return {
    clientHeight: 400,
    scrollHeight: 1_200,
    scrollTop: 300,
    getBoundingClientRect: () => ({ top: 100 }),
    querySelectorAll: () => rows,
    querySelector: (selector) => {
      const id = selector.match(/"(.+)"/)?.[1];
      return (
        rows.find((candidate) => candidate.dataset.timelineKey === id) ?? null
      );
    },
    ...overrides,
  };
}

test("capture and restore keep the first visible row at the same viewport offset", () => {
  const before = container([row("entry-1", 70, 120), row("entry-2", 120, 190)]);
  const anchor = captureScrollAnchor(before);
  assert.deepEqual(anchor, { key: "entry-1", topOffset: -30 });

  const after = container([row("entry-1", 270, 320)], { scrollTop: 300 });
  assert.equal(restoreScrollAnchor(after, anchor), true);
  assert.equal(after.scrollTop, 500);
});

test("the physical bottom is represented by no row anchor", () => {
  const atBottom = container([], { scrollHeight: 700, scrollTop: 300 });
  assert.equal(captureScrollAnchor(atBottom), null);
});

test("virtua shift is armed only for a stable-key prepend", () => {
  assert.equal(isPrependDelta(["3", "4"], ["1", "2", "3", "4"]), true);
  assert.equal(isPrependDelta(["1", "2"], ["1", "2", "3"]), false);
  assert.equal(isPrependDelta(["1", "3"], ["1", "2", "3"]), false);
});

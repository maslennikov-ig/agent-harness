/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import * as React from "react";
import type { VListHandle } from "virtua";

const AT_BOTTOM_THRESHOLD_PX = 32;

export interface ScrollAnchor {
  key: string;
  topOffset: number;
}

type AnchorRow = HTMLElement & { dataset: { timelineKey?: string } };
type AnchorContainer = Pick<
  HTMLElement,
  | "clientHeight"
  | "scrollHeight"
  | "scrollTop"
  | "getBoundingClientRect"
  | "querySelectorAll"
> & { querySelector: (selector: string) => Element | null };

export function isAtBottom(container: {
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
}) {
  return (
    container.scrollHeight - container.clientHeight - container.scrollTop <=
    AT_BOTTOM_THRESHOLD_PX
  );
}

export function captureScrollAnchor(
  container: AnchorContainer,
): ScrollAnchor | null {
  if (isAtBottom(container)) return null;
  const containerTop = container.getBoundingClientRect().top;
  const rows = container.querySelectorAll<AnchorRow>("[data-timeline-key]");
  for (const row of rows) {
    const rect = row.getBoundingClientRect();
    const key = row.dataset.timelineKey;
    if (rect.bottom > containerTop && key) {
      return { key, topOffset: rect.top - containerTop };
    }
  }
  return null;
}

export function restoreScrollAnchor(
  container: AnchorContainer,
  anchor: ScrollAnchor | null,
) {
  if (!anchor) return false;
  const rows = container.querySelectorAll<AnchorRow>("[data-timeline-key]");
  const row = [...rows].find(
    (candidate) => candidate.dataset.timelineKey === anchor.key,
  );
  if (!row) return false;
  const containerTop = container.getBoundingClientRect().top;
  const nextOffset = row.getBoundingClientRect().top - containerTop;
  container.scrollTop += nextOffset - anchor.topOffset;
  return true;
}

export function isPrependDelta(previous: string[], next: string[]) {
  if (previous.length === 0 || next.length <= previous.length) return false;
  const offset = next.length - previous.length;
  return previous.every((key, index) => next[index + offset] === key);
}

export function useAnchoredScroll({
  channelId,
  entryKeys,
  itemCount,
}: {
  channelId: string;
  entryKeys: string[];
  itemCount: number;
}) {
  const listRef = React.useRef<VListHandle>(null);
  const previousKeysRef = React.useRef<string[]>([]);
  const initializedRef = React.useRef(false);
  const [atBottom, setAtBottom] = React.useState(true);
  const [newMessageCount, setNewMessageCount] = React.useState(0);
  const shift = isPrependDelta(previousKeysRef.current, entryKeys);

  const scrollToBottom = React.useCallback(() => {
    const list = listRef.current;
    if (!list || itemCount === 0) return;
    list.scrollToIndex(itemCount - 1, { align: "end" });
    setAtBottom(true);
    setNewMessageCount(0);
  }, [itemCount]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: channelId is the reset signal for ref-owned scroll state.
  React.useLayoutEffect(() => {
    previousKeysRef.current = [];
    initializedRef.current = false;
    setAtBottom(true);
    setNewMessageCount(0);
  }, [channelId]);

  React.useLayoutEffect(() => {
    const previous = previousKeysRef.current;
    const appended =
      initializedRef.current &&
      !shift &&
      entryKeys.length > previous.length &&
      previous.every((key, index) => entryKeys[index] === key);
    previousKeysRef.current = entryKeys;
    if (!initializedRef.current && entryKeys.length > 0) {
      initializedRef.current = true;
      requestAnimationFrame(scrollToBottom);
    } else if (appended) {
      const count = entryKeys.length - previous.length;
      if (atBottom) requestAnimationFrame(scrollToBottom);
      else setNewMessageCount((current) => current + count);
    }
  }, [atBottom, entryKeys, scrollToBottom, shift]);

  const onScroll = React.useCallback((offset: number) => {
    const list = listRef.current;
    if (!list) return;
    const next =
      list.scrollSize - list.viewportSize - offset <= AT_BOTTOM_THRESHOLD_PX;
    setAtBottom((current) => (current === next ? current : next));
    if (next) setNewMessageCount(0);
  }, []);

  return {
    atBottom,
    listRef,
    newMessageCount,
    onScroll,
    scrollToBottom,
    shift,
  };
}

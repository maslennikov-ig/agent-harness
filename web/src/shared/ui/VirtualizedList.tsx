/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import type { ReactNode, RefObject } from "react";
import { VList, type VListHandle } from "virtua";

export function VirtualizedList<T>({
  ariaLabel,
  getItemKey,
  items,
  listRef,
  onScroll,
  renderItem,
  shift,
}: {
  ariaLabel: string;
  getItemKey: (item: T, index: number) => string;
  items: T[];
  listRef: RefObject<VListHandle | null>;
  onScroll: (offset: number) => void;
  renderItem: (item: T, index: number) => ReactNode;
  shift: boolean;
}) {
  return (
    <VList
      aria-label={ariaLabel}
      className="h-full overscroll-contain rounded-[inherit] [scrollbar-gutter:stable]"
      data={items}
      id="timeline-list"
      onScroll={onScroll}
      ref={listRef}
      role="log"
      shift={shift}
    >
      {(item, index) => {
        const key = getItemKey(item, index);
        return (
          <div data-timeline-key={key} key={key}>
            {renderItem(item, index)}
          </div>
        );
      }}
    </VList>
  );
}

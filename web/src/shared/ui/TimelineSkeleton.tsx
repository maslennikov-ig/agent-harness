/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import { Skeleton } from "@/shared/ui/skeleton";

const widths = ["w-4/5", "w-2/3", "w-11/12", "w-3/4"];

export function TimelineSkeleton() {
  return (
    <div
      aria-label="Загрузка обсуждения"
      className="space-y-5 p-5"
      role="status"
    >
      {widths.map((width, index) => (
        <div className="flex gap-3" key={width}>
          <Skeleton className="size-9 shrink-0 rounded-full" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex gap-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-14" />
            </div>
            <Skeleton className={`h-4 ${width}`} />
            {index % 2 === 0 ? <Skeleton className="h-4 w-1/2" /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

/*
 * SPDX-License-Identifier: Apache-2.0
 * Adapted from block/buzz at commit 1ff98fa. See docs/vendored-from-buzz.md.
 */

import { ArrowDown } from "lucide-react";
import { Button } from "@/shared/ui/button";

export function UnreadPill({
  count,
  onClick,
}: {
  count: number;
  onClick: () => void;
}) {
  return (
    <Button
      className="pointer-events-auto rounded-full shadow-lg"
      data-testid="new-message-pill"
      onClick={onClick}
      size="sm"
      type="button"
    >
      <ArrowDown aria-hidden="true" />
      {count} {count === 1 ? "новое событие" : "новых событий"}
    </Button>
  );
}

import { reviewGateText } from "@/features/workspace/review/review-gate";
import type { CoordinationReviewExecutor } from "@/shared/api/types";

export function ReviewGate({ entry }: { entry: CoordinationReviewExecutor }) {
  return (
    <p
      className="rounded-lg bg-surface-low p-3 text-sm"
      data-gate={
        !entry.is_current
          ? "superseded"
          : entry.done_allowed
            ? "open"
            : "closed"
      }
      title={entry.done_blocked_reason}
    >
      {reviewGateText(entry)}
    </p>
  );
}

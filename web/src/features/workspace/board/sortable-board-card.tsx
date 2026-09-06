import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, LockKeyhole } from "lucide-react";
import type { BoardColumnId, CoordinationBoardCard } from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import { Select } from "@/shared/ui/select";

const columnLabels: Record<BoardColumnId, string> = {
  ready: "Ready",
  running: "Running",
  blocked: "Blocked",
  done: "Done",
};

const phaseLabels: Record<string, string> = {
  planning: "планирование",
  execution: "исполнение",
  review: "ревью",
  accepted: "принято",
};

export function SortableBoardCard({
  card,
  disabled,
  onMove,
}: {
  card: CoordinationBoardCard;
  disabled: boolean;
  onMove: (card: CoordinationBoardCard, target: BoardColumnId) => void;
}) {
  const held = disabled || card.dependency_blocked || card.targets.length === 0;
  const {
    attributes,
    isDragging,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({
    id: card.id,
    disabled: held,
    data: { type: "card", column: card.column },
  });

  return (
    <article
      className="rounded-xl border border-border-soft bg-card p-3 transition-[border-color,opacity,transform] duration-200 data-[dragging=true]:opacity-60"
      data-card-id={card.id}
      data-dragging={isDragging}
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
    >
      <div className="flex items-start gap-2">
        {held ? (
          <span
            aria-hidden="true"
            className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-disabled-bg text-muted-foreground"
          >
            <LockKeyhole className="size-4" />
          </span>
        ) : (
          <Button
            aria-label={`Перетащить ${card.id}`}
            className="mt-0.5 shrink-0 cursor-grab touch-none active:cursor-grabbing"
            data-drag-handle
            size="icon"
            type="button"
            variant="ghost"
            {...attributes}
            {...listeners}
          >
            <GripVertical aria-hidden="true" />
          </Button>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs text-muted-foreground">
            {card.id}
          </p>
          <h4 className="mt-1 text-sm font-semibold leading-snug">
            {card.title}
          </h4>
          <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
            <span className="rounded-md bg-surface-mid px-2 py-1">
              {columnLabels[card.column]}
            </span>
            <span className="rounded-md bg-runtime-accent-soft px-2 py-1 text-primary">
              {phaseLabels[card.phase] ?? card.phase}
            </span>
            <span className="rounded-md bg-surface-low px-2 py-1 font-mono">
              P{card.priority ?? "—"}
            </span>
          </div>
          {card.dependency_blocked ? (
            <p className="mt-2 text-xs text-warning">
              Beads держит:{" "}
              {card.blocked_by.join(", ") || "незакрытая зависимость"}
            </p>
          ) : null}
        </div>
      </div>
      <label
        className="mt-3 block text-xs text-muted-foreground"
        htmlFor={`board-move-${card.id}`}
      >
        <span className="sr-only">Переместить {card.id}</span>
        <Select
          aria-label={`Переместить ${card.id}`}
          className="rounded-lg text-sm"
          id={`board-move-${card.id}`}
          disabled={held}
          onChange={(event) => {
            if (!event.target.value) return;
            onMove(card, event.target.value as BoardColumnId);
            event.target.value = "";
          }}
          value=""
        >
          <option value="">
            {held ? "переместить недоступно" : "переместить…"}
          </option>
          {card.targets.map((target) => (
            <option key={target} value={target}>
              → {columnLabels[target]}
            </option>
          ))}
        </Select>
      </label>
    </article>
  );
}

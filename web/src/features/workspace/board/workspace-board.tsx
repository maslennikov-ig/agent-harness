import {
  closestCorners,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  sortableKeyboardCoordinates,
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useState } from "react";
import { toast } from "sonner";
import { SortableBoardCard } from "@/features/workspace/board/sortable-board-card";
import { buildBoardTransition } from "@/features/workspace/board/transition";
import { postJson } from "@/shared/api/client";
import type {
  BoardColumnId,
  CoordinationBoardCard,
  CoordinationBoardPayload,
} from "@/shared/api/types";
import { Button } from "@/shared/ui/button";

const columns: BoardColumnId[] = ["ready", "running", "blocked", "done"];
const columnLabels: Record<BoardColumnId, { label: string; mark: string }> = {
  ready: { label: "Ready", mark: "○" },
  running: { label: "Running", mark: "▶" },
  blocked: { label: "Blocked", mark: "▬" },
  done: { label: "Done", mark: "✓" },
};
const phases = ["", "planning", "execution", "review", "accepted"];
const phaseLabels: Record<string, string> = {
  "": "Все фазы",
  planning: "Планирование",
  execution: "Исполнение",
  review: "Ревью",
  accepted: "Принято",
};

function BoardColumn({
  cards,
  column,
  disabled,
  onMove,
}: {
  cards: CoordinationBoardCard[];
  column: BoardColumnId;
  disabled: boolean;
  onMove: (card: CoordinationBoardCard, target: BoardColumnId) => void;
}) {
  const droppable = useDroppable({
    id: `column:${column}`,
    data: { type: "column", column },
  });
  return (
    <section
      className="min-w-0 rounded-xl bg-surface-low p-2.5"
      data-board-column={column}
      ref={droppable.setNodeRef}
    >
      <header className="mb-2 flex items-center justify-between px-1 py-1">
        <h3 className="text-sm font-semibold">
          <span aria-hidden="true" className="mr-1.5 text-primary">
            {columnLabels[column].mark}
          </span>
          {columnLabels[column].label}
        </h3>
        <span className="font-mono text-xs text-muted-foreground">
          {cards.length}
        </span>
      </header>
      <SortableContext
        items={cards.map((card) => card.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="grid min-h-24 content-start gap-2">
          {cards.map((card) => (
            <SortableBoardCard
              card={card}
              disabled={disabled}
              key={card.id}
              onMove={onMove}
            />
          ))}
          {cards.length === 0 ? (
            <p className="grid min-h-20 place-items-center rounded-lg border border-dashed border-border-soft text-xs text-muted-foreground">
              пусто
            </p>
          ) : null}
        </div>
      </SortableContext>
    </section>
  );
}

export function WorkspaceBoard({
  board,
  onRefresh,
  onStartRequested,
}: {
  board: CoordinationBoardPayload;
  onRefresh: () => Promise<unknown>;
  onStartRequested: (issueId: string) => void;
}) {
  const [phase, setPhase] = useState("");
  const [status, setStatus] = useState("");
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const cards = board.columns.flatMap((column) => column.issues);

  const move = async (card: CoordinationBoardCard, target: BoardColumnId) => {
    try {
      const request = buildBoardTransition(
        { projectId: board.project_id ?? "", epicId: board.epic_id },
        card,
        target,
      );
      const result = await postJson<{
        column: BoardColumnId;
        requires_start: boolean;
      }>("/api/coordination/board/transition", request);
      setStatus(
        `${card.id}: Beads подтвердил колонку ${columnLabels[result.column].label}.`,
      );
      await onRefresh();
      if (result.requires_start) onStartRequested(card.id);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Переход отклонён";
      setStatus(`Переход отклонён — ${message}`);
      toast.error(message);
      await onRefresh();
    }
  };

  const onDragEnd = (event: DragEndEvent) => {
    const card = cards.find((candidate) => candidate.id === event.active.id);
    const target = event.over?.data.current?.column as
      | BoardColumnId
      | undefined;
    if (!card || !target || target === card.column) return;
    void move(card, target);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 rounded-xl bg-surface-low p-3 lg:flex-row lg:items-center lg:justify-between">
        <p className="min-w-0 break-words font-mono text-xs text-muted-foreground">
          {board.errors.length
            ? board.errors.join(" · ")
            : `${board.repo_path ?? ""} · ${board.beads_issue_id ?? ""}`}
        </p>
        <fieldset className="flex flex-wrap gap-1">
          <legend className="sr-only">Фильтр по фазе</legend>
          {phases.map((item) => (
            <Button
              aria-pressed={phase === item}
              key={item || "all"}
              onClick={() => setPhase(item)}
              size="sm"
              type="button"
              variant={phase === item ? "secondary" : "ghost"}
            >
              {phaseLabels[item]}
            </Button>
          ))}
        </fieldset>
      </div>
      <p
        aria-live="polite"
        className="min-h-5 text-sm text-muted-foreground"
        role="status"
      >
        {status}
      </p>
      <p className="text-sm text-muted-foreground">
        Перетащите карточку за рукоятку или выберите колонку в списке. Оба пути
        отправляют один и тот же переход; позиция меняется только после ответа
        Beads.
      </p>
      <DndContext
        collisionDetection={closestCorners}
        onDragEnd={onDragEnd}
        sensors={sensors}
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {columns.map((column) => (
            <BoardColumn
              cards={(
                board.columns.find((item) => item.id === column)?.issues ?? []
              ).filter((card) => !phase || card.phase === phase)}
              column={column}
              disabled={!board.writable}
              key={column}
              onMove={(card, target) => void move(card, target)}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
}

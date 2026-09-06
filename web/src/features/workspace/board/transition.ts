import type { BoardColumnId } from "@/shared/api/types";

export type BoardTransitionCard = {
  blocked_by: string[];
  column: BoardColumnId;
  dependency_blocked: boolean;
  id: string;
  targets: BoardColumnId[];
};

export type BoardTransitionScope = {
  epicId: string;
  projectId: string;
};

export type BoardTransitionRequest = {
  project_id: string;
  epic_id: string;
  issue_id: string;
  from_column: BoardColumnId;
  to_column: BoardColumnId;
};

export function buildBoardTransition(
  scope: BoardTransitionScope,
  card: BoardTransitionCard,
  toColumn: BoardColumnId,
): BoardTransitionRequest {
  if (card.dependency_blocked) {
    const blockers = card.blocked_by.join(", ") || "an open dependency";
    throw new Error(`${card.id} is held by ${blockers}`);
  }
  if (!card.targets.includes(toColumn)) {
    throw new Error(`${card.id} does not allow ${card.column} → ${toColumn}`);
  }
  return {
    project_id: scope.projectId,
    epic_id: scope.epicId,
    issue_id: card.id,
    from_column: card.column,
    to_column: toColumn,
  };
}

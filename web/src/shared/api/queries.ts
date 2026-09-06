import { queryOptions } from "@tanstack/react-query";
import { requestJson } from "@/shared/api/client";
import type {
  CoordinationBoardPayload,
  CoordinationDispatch,
  CoordinationOverviewPayload,
  CoordinationPlanningArtifact,
  CoordinationReviewsPayload,
  OverviewPayload,
} from "@/shared/api/types";
import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";

/**
 * D6: list screens poll once a minute while their tab is visible. The
 * coordination timeline is excluded on purpose — it is driven by SSE.
 */
export const LIST_REFRESH_INTERVAL_MS = 60_000;

/**
 * Long enough that navigating between screens does not refetch, short enough
 * that returning to the window (`refetchOnWindowFocus`) does.
 */
const PROJECTION_STALE_TIME_MS = 30_000;

/**
 * Server-side cap on one timeline page. The timeline tells the reader when it
 * hits this, because older events are then missing from the view.
 */
export const TIMELINE_EVENT_LIMIT = 2000;

export const queryKeys = {
  overview: ["overview"] as const,
  coordination: ["coordination"] as const,
  coordinationEvents: (epicId: string) =>
    ["coordination", "events", epicId] as const,
  coordinationDispatches: (epicId: string) =>
    ["coordination", "dispatches", epicId] as const,
  coordinationBoard: (epicId: string) =>
    ["coordination", "board", epicId] as const,
  coordinationPlanning: (epicId: string) =>
    ["coordination", "planning", epicId] as const,
  coordinationReviews: (epicId: string) =>
    ["coordination", "reviews", epicId] as const,
};

export const overviewQuery = queryOptions({
  queryKey: queryKeys.overview,
  queryFn: () => requestJson<OverviewPayload>("/api/overview"),
  staleTime: PROJECTION_STALE_TIME_MS,
});

export const coordinationOverviewQuery = queryOptions({
  queryKey: queryKeys.coordination,
  queryFn: () => requestJson<CoordinationOverviewPayload>("/api/coordination"),
  refetchInterval: LIST_REFRESH_INTERVAL_MS,
  staleTime: PROJECTION_STALE_TIME_MS,
});

export const coordinationEventsQuery = (epicId: string) =>
  queryOptions({
    queryKey: queryKeys.coordinationEvents(epicId),
    queryFn: () =>
      requestJson<{
        epic_id: string;
        events: CoordinationEvent[];
        latest_seq: number;
      }>(
        `/api/coordination/events?epic_id=${encodeURIComponent(epicId)}&limit=${TIMELINE_EVENT_LIMIT}`,
      ),
    staleTime: Number.POSITIVE_INFINITY,
  });

export const coordinationDispatchesQuery = (epicId: string) =>
  queryOptions({
    queryKey: queryKeys.coordinationDispatches(epicId),
    queryFn: () =>
      requestJson<{ epic_id: string; dispatches: CoordinationDispatch[] }>(
        `/api/coordination/dispatches?epic_id=${encodeURIComponent(epicId)}`,
      ),
    staleTime: Number.POSITIVE_INFINITY,
  });

export const coordinationBoardQuery = (epicId: string) =>
  queryOptions({
    queryKey: queryKeys.coordinationBoard(epicId),
    queryFn: () =>
      requestJson<CoordinationBoardPayload>(
        `/api/coordination/board?epic_id=${encodeURIComponent(epicId)}`,
      ),
  });

export const coordinationPlanningQuery = (epicId: string) =>
  queryOptions({
    queryKey: queryKeys.coordinationPlanning(epicId),
    queryFn: () =>
      requestJson<{
        epic_id: string;
        artifacts: CoordinationPlanningArtifact[];
      }>(
        `/api/coordination/planning-artifacts?epic_id=${encodeURIComponent(epicId)}`,
      ),
  });

export const coordinationReviewsQuery = (epicId: string) =>
  queryOptions({
    queryKey: queryKeys.coordinationReviews(epicId),
    queryFn: () =>
      requestJson<CoordinationReviewsPayload>(
        `/api/coordination/reviews?epic_id=${encodeURIComponent(epicId)}`,
      ),
  });

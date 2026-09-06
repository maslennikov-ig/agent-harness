import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { ArtifactsPanel } from "@/features/workspace/artifacts/artifacts-panel";
import { WorkspaceBoard } from "@/features/workspace/board/workspace-board";
import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";
import { PlanningPanel } from "@/features/workspace/planning/planning-panel";
import { RunsPanel } from "@/features/workspace/runs/runs-panel";
import { StartSheet } from "@/features/workspace/start-sheet/start-sheet";
import {
  coordinationBoardQuery,
  coordinationPlanningQuery,
  coordinationReviewsQuery,
} from "@/shared/api/queries";
import type {
  CoordinationDispatch,
  CoordinationEpic,
  CoordinationOverviewPayload,
  CoordinationProject,
} from "@/shared/api/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";

export function WorkspaceTabs({
  discussion,
  dispatches,
  enabled,
  epic,
  events,
  onRunsChanged,
  overview,
  project,
}: {
  discussion: ReactNode;
  dispatches: CoordinationDispatch[];
  enabled: boolean;
  epic: CoordinationEpic;
  events: CoordinationEvent[];
  onRunsChanged: () => Promise<unknown>;
  overview: CoordinationOverviewPayload;
  project: CoordinationProject;
}) {
  const board = useQuery(coordinationBoardQuery(epic.epic_id));
  const planning = useQuery(coordinationPlanningQuery(epic.epic_id));
  const reviews = useQuery(coordinationReviewsQuery(epic.epic_id));
  const [startOpen, setStartOpen] = useState(false);
  const [startIssueId, setStartIssueId] = useState("");

  const openStart = (issueId = "") => {
    setStartIssueId(issueId);
    setStartOpen(true);
  };
  const refreshRuns = async () => {
    await Promise.all([onRunsChanged(), board.refetch(), reviews.refetch()]);
  };

  return (
    <>
      <Tabs className="space-y-3" defaultValue="discussion">
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 bg-surface-low p-2">
          <TabsTrigger value="discussion">Обсуждение</TabsTrigger>
          <TabsTrigger value="specification">Спецификация</TabsTrigger>
          <TabsTrigger value="plan">План</TabsTrigger>
          <TabsTrigger value="tasks">Задачи</TabsTrigger>
          <TabsTrigger value="artifacts">Артефакты</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
        </TabsList>
        <TabsContent className="mt-0" value="discussion">
          {discussion}
        </TabsContent>
        <TabsContent className="mt-0" value="specification">
          <PlanningPanel
            artifacts={planning.data?.artifacts ?? []}
            enabled={enabled}
            epicId={epic.epic_id}
            kind="specification"
            onChanged={() => planning.refetch()}
            projectId={project.project_id}
          />
        </TabsContent>
        <TabsContent className="mt-0" value="plan">
          <PlanningPanel
            artifacts={planning.data?.artifacts ?? []}
            enabled={enabled}
            epicId={epic.epic_id}
            kind="plan"
            onChanged={() => planning.refetch()}
            projectId={project.project_id}
          />
        </TabsContent>
        <TabsContent className="mt-0" value="tasks">
          {board.data ? (
            <WorkspaceBoard
              board={board.data}
              onRefresh={() => board.refetch()}
              onStartRequested={openStart}
            />
          ) : (
            <div className="rounded-xl bg-surface-low p-6 text-sm text-muted-foreground">
              Загружаем каноническую доску Beads…
            </div>
          )}
        </TabsContent>
        <TabsContent className="mt-0" value="artifacts">
          <ArtifactsPanel events={events} />
        </TabsContent>
        <TabsContent className="mt-0" value="runs">
          <RunsPanel
            dispatches={dispatches}
            enabled={enabled}
            onChanged={refreshRuns}
            onOpenStart={() => openStart()}
            providers={overview.providers}
            reviews={reviews.data}
          />
        </TabsContent>
      </Tabs>
      <StartSheet
        enabled={enabled}
        epic={epic}
        initialIssueId={startIssueId}
        onChanged={refreshRuns}
        onOpenChange={setStartOpen}
        open={startOpen}
        planning={planning.data?.artifacts ?? []}
        project={project}
        providers={overview.providers}
      />
    </>
  );
}

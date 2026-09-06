import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Radio } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { screenById } from "@/app/navigation";
import { ScreenFrame } from "@/app/components/screen-frame";
import {
  mergeCoordinationEvents,
  type CoordinationEvent,
} from "@/features/workspace/lib/formatTimelineMessages";
import { useEventStream } from "@/features/workspace/lib/useEventStream";
import { workspaceMetaNote } from "@/features/workspace/lib/workspaceMetaNote";
import { TimelineComposer } from "@/features/workspace/timeline/composer";
import { TimelineList } from "@/features/workspace/timeline/timeline-list";
import { WorkspaceTabs } from "@/features/workspace/workspace-tabs";
import { GithubIntakeDialog } from "@/features/workspace/create/github-intake-dialog";
import { WorkspaceCreateDialog } from "@/features/workspace/create/workspace-create-dialog";
import {
  coordinationDispatchesQuery,
  coordinationEventsQuery,
  TIMELINE_EVENT_LIMIT,
  coordinationOverviewQuery,
  queryKeys,
} from "@/shared/api/queries";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import { Freshness } from "@/shared/ui/freshness";
import { Select } from "@/shared/ui/select";

const workspace = screenById("workspace");
const PROJECT_STORE_KEY = "orch-prompts.workspace-project";
const ALL_PROJECTS = "all";
const lastSeenKey = (epicId: string) =>
  `orch-prompts.workspace.last-seen:${epicId}`;

function storedProject() {
  try {
    return localStorage.getItem(PROJECT_STORE_KEY) || ALL_PROJECTS;
  } catch {
    return ALL_PROJECTS;
  }
}

function readLastSeen(epicId: string) {
  try {
    return Math.max(0, Number(localStorage.getItem(lastSeenKey(epicId))) || 0);
  } catch {
    return 0;
  }
}

export function WorkspaceScreen({ epicId = "" }: { epicId?: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const overview = useQuery(coordinationOverviewQuery);
  const eventsQuery = useQuery({
    ...coordinationEventsQuery(epicId),
    enabled: Boolean(epicId),
  });
  const dispatchesQuery = useQuery({
    ...coordinationDispatchesQuery(epicId),
    enabled: Boolean(epicId),
  });
  const [events, setEvents] = useState<CoordinationEvent[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [projectFilter, setProjectFilter] = useState(storedProject);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const latestSequenceRef = useRef(0);
  const lastSeenSeq = useMemo(() => readLastSeen(epicId), [epicId]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: epicId resets the local projection before the next query lands.
  useEffect(() => {
    setEvents([]);
    latestSequenceRef.current = 0;
  }, [epicId]);

  useEffect(() => {
    if (!eventsQuery.data) return;
    setEvents(eventsQuery.data.events);
    latestSequenceRef.current = eventsQuery.data.events.at(-1)?.seq ?? 0;
  }, [eventsQuery.data]);

  useEffect(
    () => () => {
      if (!epicId || latestSequenceRef.current <= 0) return;
      try {
        localStorage.setItem(
          lastSeenKey(epicId),
          String(latestSequenceRef.current),
        );
      } catch {
        // The unread cursor is a convenience; storage failures do not block reading.
      }
    },
    [epicId],
  );

  const appendEvent = useCallback(
    (event: CoordinationEvent) => {
      latestSequenceRef.current = Math.max(
        latestSequenceRef.current,
        event.seq,
      );
      setEvents((current) => mergeCoordinationEvents(current, [event]));
      if (event.dispatch_id) {
        void Promise.all([
          queryClient.invalidateQueries({
            queryKey: queryKeys.coordinationDispatches(epicId),
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.coordinationBoard(epicId),
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.coordinationReviews(epicId),
          }),
        ]);
      }
    },
    [epicId, queryClient],
  );

  const initialCursor = eventsQuery.data?.events.at(-1)?.seq ?? 0;
  // A full page back from the server means older events were cut off.
  const timelineTruncated =
    (eventsQuery.data?.events.length ?? 0) >= TIMELINE_EVENT_LIMIT;
  const stream = useEventStream({
    afterSeq: initialCursor,
    enabled: Boolean(epicId && eventsQuery.isSuccess),
    epicId,
    onEvent: appendEvent,
  });

  const selectedEpic = overview.data?.epics.find(
    (epic) => epic.epic_id === epicId,
  );
  const project = overview.data?.projects.find(
    (candidate) => candidate.project_id === selectedEpic?.project_id,
  );
  const metaNote = workspaceMetaNote(overview.data);
  const projects = overview.data?.projects ?? [];
  const projectName = (projectId: string) =>
    projects.find((candidate) => candidate.project_id === projectId)?.name ||
    projectId;
  // A project can be removed from the store, so an unknown filter shows every
  // epic instead of an empty picker.
  const activeFilter = projects.some(
    (candidate) => candidate.project_id === projectFilter,
  )
    ? projectFilter
    : ALL_PROJECTS;
  const visibleEpics = (overview.data?.epics ?? []).filter(
    (epic) => activeFilter === ALL_PROJECTS || epic.project_id === activeFilter,
  );
  // GitHub intake reads one repository, so it needs a selected project.
  const filteredProject = projects.find(
    (candidate) => candidate.project_id === activeFilter,
  );
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.coordination }),
      epicId
        ? queryClient.invalidateQueries({
            queryKey: queryKeys.coordinationEvents(epicId),
          })
        : Promise.resolve(),
      epicId
        ? queryClient.invalidateQueries({
            queryKey: queryKeys.coordinationDispatches(epicId),
          })
        : Promise.resolve(),
    ]);
  };

  return (
    <ScreenFrame
      actions={
        <>
          <Freshness
            isFetching={overview.isFetching}
            updatedAt={overview.dataUpdatedAt}
          />
          <Button onClick={refresh} size="sm" type="button" variant="outline">
            <RefreshCw aria-hidden="true" /> Обновить
          </Button>
        </>
      }
      marker={{ kind: "native", id: "workspace" }}
      screen={workspace}
    >
      {!epicId ? (
        <Card>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Выберите эпик</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Эпик — крупная работа с собственной перепиской, доской задач и
                  запусками. Порядок работы целиком описан в{" "}
                  <Link className="text-primary underline" to="/help">
                    Помощи
                  </Link>
                  .
                </p>
              </div>
              {overview.data ? (
                <div className="flex flex-wrap gap-2">
                  <Button
                    disabled={!filteredProject}
                    onClick={() => setIntakeOpen(true)}
                    title={
                      filteredProject
                        ? undefined
                        : "Выберите проект: issues читаются из его репозитория"
                    }
                    type="button"
                    variant="outline"
                  >
                    Из GitHub issue
                  </Button>
                  <Button onClick={() => setCreateOpen(true)} type="button">
                    {overview.data.epics.length
                      ? "Создать эпик"
                      : "Создать первый эпик"}
                  </Button>
                </div>
              ) : null}
            </div>
            {overview.data ? (
              <label
                className="mt-4 block max-w-sm text-xs text-muted-foreground"
                htmlFor="workspace-project-filter"
              >
                Проект
                <Select
                  className="rounded-lg text-sm"
                  containerClassName="mt-1"
                  id="workspace-project-filter"
                  onChange={(event) => {
                    setProjectFilter(event.target.value);
                    try {
                      localStorage.setItem(
                        PROJECT_STORE_KEY,
                        event.target.value,
                      );
                    } catch {
                      // The filter is a convenience; storage failures do not block it.
                    }
                  }}
                  value={activeFilter}
                >
                  <option value={ALL_PROJECTS}>
                    Все проекты ({projects.length})
                  </option>
                  {projects.map((candidate) => (
                    <option
                      key={candidate.project_id}
                      value={candidate.project_id}
                    >
                      {candidate.name}
                    </option>
                  ))}
                </Select>
              </label>
            ) : null}
            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {visibleEpics.map((epic) => (
                <Link
                  className="rounded-xl border border-border-soft bg-surface-low p-4 transition-colors hover:border-primary/60"
                  key={epic.epic_id}
                  params={{ epicId: epic.epic_id }}
                  to="/workspace/$epicId"
                >
                  <span className="font-semibold">{epic.title}</span>
                  <span className="mt-1 block font-mono text-xs text-muted-foreground">
                    {epic.beads_issue_id || epic.epic_id}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {projectName(epic.project_id)}
                    {epic.source_ref ? ` · ${epic.source_ref}` : ""}
                  </span>
                </Link>
              ))}
              {overview.isSuccess && visibleEpics.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {overview.data.epics.length
                    ? "В этом проекте эпиков пока нет."
                    : "Зарегистрированных эпиков пока нет."}
                </p>
              ) : null}
            </div>
            {overview.data && filteredProject ? (
              <GithubIntakeDialog
                onCreated={async (epic) => {
                  setIntakeOpen(false);
                  await queryClient.invalidateQueries({
                    queryKey: queryKeys.coordination,
                  });
                  await navigate({
                    to: "/workspace/$epicId",
                    params: { epicId: epic.epic_id },
                  });
                }}
                onOpenChange={setIntakeOpen}
                open={intakeOpen}
                project={filteredProject}
              />
            ) : null}
            {overview.data ? (
              <WorkspaceCreateDialog
                onCreated={async (epic) => {
                  setCreateOpen(false);
                  await queryClient.invalidateQueries({
                    queryKey: queryKeys.coordination,
                  });
                  await navigate({
                    to: "/workspace/$epicId",
                    params: { epicId: epic.epic_id },
                  });
                }}
                onOpenChange={setCreateOpen}
                open={createOpen}
                overview={overview.data}
              />
            ) : null}
          </CardContent>
        </Card>
      ) : selectedEpic && project && overview.data ? (
        <WorkspaceTabs
          dispatches={dispatchesQuery.data?.dispatches ?? []}
          enabled={Boolean(overview.data.enabled)}
          epic={selectedEpic}
          events={events}
          onRunsChanged={async () => {
            await queryClient.invalidateQueries({
              queryKey: queryKeys.coordinationDispatches(epicId),
            });
          }}
          overview={overview.data}
          project={project}
          discussion={
            <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-panel">
              <div className="flex flex-col gap-3 border-b border-border-soft bg-surface-low px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-lg font-semibold">
                      {selectedEpic?.title ?? epicId}
                    </h2>
                    <Badge
                      variant={overview.data?.enabled ? "default" : "secondary"}
                    >
                      {overview.data?.enabled
                        ? "запись включена"
                        : "только чтение"}
                    </Badge>
                  </div>
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {project?.name ??
                      selectedEpic?.project_id ??
                      "Локальный проект"}
                    {selectedEpic?.beads_issue_id
                      ? ` · Beads ${selectedEpic.beads_issue_id}`
                      : ""}
                  </p>
                  {selectedEpic?.source_url ? (
                    <a
                      className="mt-1 inline-block text-xs text-primary underline underline-offset-2"
                      href={selectedEpic.source_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Источник: {selectedEpic.source_ref || "GitHub issue"}
                    </a>
                  ) : null}
                  {metaNote ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {metaNote}
                    </p>
                  ) : null}
                </div>
                <div className="flex w-full flex-col items-stretch gap-2 sm:w-auto sm:flex-row sm:items-center sm:gap-3">
                  <label className="sr-only" htmlFor="workspace-epic-select">
                    Эпик
                  </label>
                  <Select
                    className="rounded-lg text-sm"
                    containerClassName="w-full sm:max-w-64"
                    id="workspace-epic-select"
                    onChange={(event) =>
                      navigate({
                        to: "/workspace/$epicId",
                        params: { epicId: event.target.value },
                      })
                    }
                    value={epicId}
                  >
                    {projects.map((candidate) => (
                      <optgroup
                        key={candidate.project_id}
                        label={candidate.name}
                      >
                        {(overview.data?.epics ?? [])
                          .filter(
                            (epic) => epic.project_id === candidate.project_id,
                          )
                          .map((epic) => (
                            <option key={epic.epic_id} value={epic.epic_id}>
                              {epic.title}
                            </option>
                          ))}
                      </optgroup>
                    ))}
                    {/* An epic whose project left the store still has to be reachable. */}
                    {(overview.data?.epics ?? [])
                      .filter(
                        (epic) =>
                          !projects.some(
                            (candidate) =>
                              candidate.project_id === epic.project_id,
                          ),
                      )
                      .map((epic) => (
                        <option key={epic.epic_id} value={epic.epic_id}>
                          {epic.title}
                        </option>
                      ))}
                  </Select>
                  <span
                    className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted-foreground"
                    data-last-sequence={stream.lastSequence}
                    data-stream-state={stream.state}
                  >
                    <Radio
                      aria-hidden="true"
                      className="size-3.5 text-secondary"
                    />
                    {stream.state === "live" ? "поток подключён" : stream.state}
                  </span>
                </div>
              </div>
              <div className="h-[min(68vh,52rem)] min-h-[32rem]">
                <TimelineList
                  epicId={epicId}
                  events={events}
                  lastSeenSeq={lastSeenSeq}
                  loading={eventsQuery.isLoading}
                  truncated={timelineTruncated}
                />
              </div>
              <TimelineComposer
                dispatches={dispatchesQuery.data?.dispatches ?? []}
                enabled={Boolean(
                  overview.data?.enabled && selectedEpic && project,
                )}
                epicId={epicId}
                onDispatchChanged={() => {
                  void queryClient.invalidateQueries({
                    queryKey: queryKeys.coordinationDispatches(epicId),
                  });
                }}
                onStored={appendEvent}
                projectId={project?.project_id ?? ""}
              />
            </div>
          }
        />
      ) : overview.isError ? (
        <div
          className="rounded-xl border border-destructive/50 bg-destructive/10 p-6 text-sm"
          role="alert"
        >
          Не удалось загрузить Workspace:{" "}
          {overview.error instanceof Error
            ? overview.error.message
            : String(overview.error)}
        </div>
      ) : overview.data && !selectedEpic ? (
        <div
          className="rounded-xl border border-dashed border-border-soft p-6 text-sm text-muted-foreground"
          role="status"
        >
          Эпик <span className="font-mono">{epicId}</span> не найден.{" "}
          <Link className="underline" to="/workspace">
            К списку эпиков
          </Link>
        </div>
      ) : overview.data && selectedEpic && !project ? (
        <div
          className="rounded-xl border border-dashed border-border-soft p-6 text-sm text-muted-foreground"
          role="status"
        >
          Проект эпика «{selectedEpic.title}» удалён из хранилища; Workspace для
          него недоступен.{" "}
          <Link className="underline" to="/workspace">
            К списку эпиков
          </Link>
        </div>
      ) : (
        <div
          className="rounded-xl border border-dashed border-border-soft p-6 text-sm text-muted-foreground"
          role="status"
        >
          Загружаем Workspace…
        </div>
      )}
    </ScreenFrame>
  );
}

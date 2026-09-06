import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { BeadsBoard } from "@/features/beads/beads-board";
import { BeadsRepoCard } from "@/features/beads/beads-repo";
import {
  type SyncStatus,
  syncStatusQueryErrorView,
  syncStatusView,
} from "@/features/beads/sync-status";
import type { BeadsIssue, BeadsPayload } from "@/features/beads/types";
import { WorkspaceCreateDialog } from "@/features/workspace/create/workspace-create-dialog";
import { requestJson } from "@/shared/api/client";
import { useProjectionQuery } from "@/shared/api/projection";
import {
  coordinationOverviewQuery,
  LIST_REFRESH_INTERVAL_MS,
  queryKeys,
} from "@/shared/api/queries";
import { useAppearance } from "@/shared/theme/appearance-provider";
import { Button } from "@/shared/ui/button";
import { Freshness } from "@/shared/ui/freshness";
import { RawInspector } from "@/shared/ui/raw-inspector";
import { Select } from "@/shared/ui/select";
import { ToneBadge } from "@/shared/ui/projection";

const screen = screenById("beads");

const VIEW_STORE_KEY = "orch-prompts.beads-view";
const PROJECT_STORE_KEY = "orch-prompts.beads-project";
const ALL_PROJECTS = "all";

type BeadsView = "list" | "board";

interface PromptCard {
  id: string;
  launcher_text?: string;
  text?: string;
}

interface PromptsPayload {
  prompts: PromptCard[];
}

function shellQuote(value: string) {
  return `'${value.replaceAll("'", `'"'"'`)}'`;
}

function storedValue(key: string, fallback: string) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function storeValue(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage is optional; the choice stays active for this session.
  }
}

export function BeadsScreen() {
  const { runtime } = useAppearance();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const coordination = useQuery(coordinationOverviewQuery);
  const [showAll, setShowAll] = useState(false);
  const [handoff, setHandoff] = useState<{
    repoPath: string;
    issue: BeadsIssue;
  } | null>(null);
  const [view, setView] = useState<BeadsView>(() =>
    storedValue(VIEW_STORE_KEY, "list") === "board" ? "board" : "list",
  );
  const [project, setProject] = useState(() =>
    storedValue(PROJECT_STORE_KEY, ALL_PROJECTS),
  );
  const endpoint = showAll ? "/api/beads?limit=all" : "/api/beads";
  const { query, refresh } = useProjectionQuery<BeadsPayload>(endpoint, {
    refetchInterval: LIST_REFRESH_INTERVAL_MS,
  });
  const prompts = useQuery({
    queryKey: ["prompts", runtime, ""],
    queryFn: () =>
      requestJson<PromptsPayload>(`/api/prompts?runtime=${runtime}`),
  });
  const data = query.data;
  // A repository disappears when Beads is rescanned, so an unknown selection
  // falls back to every project instead of showing an empty screen.
  const known = (data?.repos ?? []).some((repo) => repo.repo_path === project);
  const activeProject = known ? project : ALL_PROJECTS;
  const repos = (data?.repos ?? []).filter(
    (repo) =>
      activeProject === ALL_PROJECTS || repo.repo_path === activeProject,
  );
  const totals = repos.reduce(
    (sum, repo) => ({
      ready: sum.ready + (repo.counts.ready || 0),
      in_progress: sum.in_progress + (repo.counts.in_progress || 0),
      blocked: sum.blocked + (repo.counts.blocked || 0),
    }),
    { ready: 0, in_progress: 0, blocked: 0 },
  );
  const sync = useQuery({
    enabled: activeProject !== ALL_PROJECTS,
    queryKey: ["github-sync-status", activeProject],
    queryFn: () =>
      requestJson<SyncStatus>(
        `/api/github/sync-status?repo=${encodeURIComponent(activeProject)}`,
      ),
  });
  const syncView = sync.isError
    ? syncStatusQueryErrorView()
    : sync.data
      ? syncStatusView(sync.data)
      : null;
  const hasMore = repos.some(
    (repo) =>
      repo.ready.length < (repo.counts.ready || 0) ||
      repo.in_progress.length < (repo.counts.in_progress || 0) ||
      repo.blocked.length < (repo.counts.blocked || 0),
  );

  const copy = async (text: string, success: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(success);
    } catch {
      toast.error("Не удалось скопировать");
    }
  };

  const copyCommand = (repoPath: string, issue: BeadsIssue) =>
    copy(
      `cd ${shellQuote(repoPath)} && bd show ${issue.id}`,
      `Команда для ${issue.id} скопирована`,
    );

  const copyPrompt = (repoPath: string, issue: BeadsIssue) => {
    const baseId =
      issue.status === "in_progress" ? "continue-stage" : "start-stage";
    const fallbackId =
      baseId === "start-stage" ? "continue-stage" : "start-stage";
    const ids =
      runtime === "claude"
        ? [`claude-${baseId}`, baseId, `claude-${fallbackId}`, fallbackId]
        : [baseId, fallbackId];
    const prompt = ids
      .map((id) => prompts.data?.prompts.find((item) => item.id === id))
      .find(Boolean);
    const header = `Repo: ${repoPath}\nBeads task: ${issue.id} — ${issue.title}`;
    const launcher = prompt?.launcher_text || prompt?.text || "";
    return copy(
      launcher ? `${header}\n\n${launcher}` : header,
      `Промпт с задачей ${issue.id} скопирован`,
    );
  };

  // An epic already linked to this issue is the destination; otherwise the
  // create dialog opens with the repository and the issue already filled in.
  const openInWorkspace = (repoPath: string, issue: BeadsIssue) => {
    const existing = coordination.data?.epics.find(
      (epic) => epic.beads_issue_id === issue.id,
    );
    if (existing) {
      void navigate({
        to: "/workspace/$epicId",
        params: { epicId: existing.epic_id },
      });
      return;
    }
    if (!coordination.data?.enabled) {
      toast.error(
        "Workspace открыт только на чтение: запустите панель без ORCH_COORDINATION=0",
      );
      return;
    }
    setHandoff({ repoPath, issue });
  };

  return (
    <ScreenFrame
      actions={
        <>
          <Freshness
            isFetching={query.isFetching}
            updatedAt={query.dataUpdatedAt}
          />
          <Button onClick={refresh} size="sm" type="button" variant="outline">
            <RefreshCw aria-hidden="true" /> Обновить
          </Button>
        </>
      }
      marker={{ kind: "native", id: "beads" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Загружаем Beads…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          {query.error instanceof Error
            ? query.error.message
            : "Beads недоступен"}
        </p>
      ) : data && !data.available ? (
        <p className="rounded-xl border border-warning p-5 text-warning">
          {data.error || "Установите Beads (bd), чтобы видеть задачи."}
        </p>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl bg-surface-low p-3">
            <label
              className="block min-w-0 text-xs text-muted-foreground"
              htmlFor="beads-project"
            >
              Проект
              <Select
                className="rounded-lg text-sm"
                containerClassName="mt-1 min-w-56"
                id="beads-project"
                onChange={(event) => {
                  setProject(event.target.value);
                  storeValue(PROJECT_STORE_KEY, event.target.value);
                }}
                value={activeProject}
              >
                <option value={ALL_PROJECTS}>
                  Все проекты ({data.repos.length})
                </option>
                {data.repos.map((repo) => (
                  <option key={repo.repo_path} value={repo.repo_path}>
                    {repo.project}
                  </option>
                ))}
              </Select>
            </label>
            {activeProject !== ALL_PROJECTS && syncView ? (
              <p
                className={`min-w-0 grow break-words text-xs ${syncView.className}`}
                role={syncView.role}
              >
                {syncView.text}
              </p>
            ) : null}
            <fieldset className="flex gap-1 rounded-lg border border-border-soft p-1">
              <legend className="sr-only">Вид</legend>
              {(["list", "board"] as const).map((item) => (
                <Button
                  aria-pressed={view === item}
                  key={item}
                  onClick={() => {
                    setView(item);
                    storeValue(VIEW_STORE_KEY, item);
                  }}
                  size="sm"
                  type="button"
                  variant={view === item ? "secondary" : "ghost"}
                >
                  {item === "list" ? "Список" : "Канбан"}
                </Button>
              ))}
            </fieldset>
          </div>
          <section
            className="space-y-3"
            aria-labelledby="beads-repositories-title"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2
                  className="text-lg font-semibold"
                  id="beads-repositories-title"
                >
                  Репозитории Beads
                </h2>
                <div className="mt-2 flex flex-wrap gap-2" data-beads-totals>
                  <ToneBadge>repos {repos.length}</ToneBadge>
                  <ToneBadge tone={totals.ready ? "neutral" : "muted"}>
                    ready {totals.ready}
                  </ToneBadge>
                  <ToneBadge tone={totals.in_progress ? "warn" : "muted"}>
                    in progress {totals.in_progress}
                  </ToneBadge>
                  <ToneBadge tone={totals.blocked ? "warn" : "muted"}>
                    blocked {totals.blocked}
                  </ToneBadge>
                </div>
              </div>
              {hasMore && !showAll ? (
                <Button
                  onClick={() => setShowAll(true)}
                  type="button"
                  variant="outline"
                >
                  Показать все
                </Button>
              ) : null}
            </div>
            {!repos.length ? (
              <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
                Репозитории с .beads/ не найдены.
              </p>
            ) : view === "board" ? (
              <BeadsBoard
                onCopyCommand={copyCommand}
                onCopyPrompt={copyPrompt}
                onOpenWorkspace={openInWorkspace}
                repos={repos}
                showProject={activeProject === ALL_PROJECTS}
              />
            ) : (
              <div className="grid gap-3">
                {repos.map((repo) => (
                  <BeadsRepoCard
                    key={repo.repo_path}
                    onCopyCommand={copyCommand}
                    onCopyPrompt={copyPrompt}
                    onOpenWorkspace={openInWorkspace}
                    repo={repo}
                  />
                ))}
              </div>
            )}
          </section>
          <RawInspector data={data} />
          {coordination.data && handoff ? (
            <WorkspaceCreateDialog
              initialBeadsIssueId={handoff.issue.id}
              initialRepoPath={handoff.repoPath}
              initialTitle={handoff.issue.title}
              onCreated={async (epic) => {
                setHandoff(null);
                await queryClient.invalidateQueries({
                  queryKey: queryKeys.coordination,
                });
                await navigate({
                  to: "/workspace/$epicId",
                  params: { epicId: epic.epic_id },
                });
              }}
              onOpenChange={(next) => {
                if (!next) setHandoff(null);
              }}
              open={Boolean(handoff)}
              overview={coordination.data}
            />
          ) : null}
        </div>
      ) : null}
    </ScreenFrame>
  );
}

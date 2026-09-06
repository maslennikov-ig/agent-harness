import { useEffect, useRef, useState } from "react";
import type {
  CoordinationEpic,
  CoordinationOverviewPayload,
  CoordinationProject,
} from "@/shared/api/types";
import { postJson } from "@/shared/api/client";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Select } from "@/shared/ui/select";

const NEW_PROJECT = "new-project";

interface CreationIdentity {
  epicId: string;
  key: string;
}

function projectIdFor(repoPath: string, projects: CoordinationProject[]) {
  const base =
    repoPath
      .replace(/[/\\]+$/, "")
      .split(/[/\\]/)
      .pop()
      ?.toLowerCase()
      .replace(/[^a-z0-9-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "project";
  // The id is the store key: reusing one would overwrite the other project.
  let candidate = base;
  let index = 2;
  while (
    projects.some(
      (project) =>
        project.project_id === candidate && project.repo_path !== repoPath,
    )
  ) {
    candidate = `${base}-${index}`;
    index += 1;
  }
  return candidate;
}

function newIdentity(): CreationIdentity {
  const id = crypto.randomUUID();
  return {
    epicId: `epic-${id}`,
    key: `workspace-create:${id}`,
  };
}

export function WorkspaceCreateDialog({
  initialBeadsIssueId = "",
  initialRepoPath = "",
  initialTitle = "",
  onCreated,
  onOpenChange,
  open,
  overview,
}: {
  initialBeadsIssueId?: string;
  initialRepoPath?: string;
  initialTitle?: string;
  onCreated: (epic: CoordinationEpic) => Promise<void>;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  overview: CoordinationOverviewPayload;
}) {
  const [step, setStep] = useState<"form" | "confirm">("form");
  const [repoPath, setRepoPath] = useState(overview.console_repo);
  const [projectId, setProjectId] = useState(
    overview.projects[0]?.project_id || "",
  );
  const [title, setTitle] = useState("");
  const [beadsIssueId, setBeadsIssueId] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const identityRef = useRef<CreationIdentity | null>(null);
  const inFlightRef = useRef(false);
  const repositories = overview.repositories ?? [];
  const createsProject =
    overview.projects.length === 0 || projectId === NEW_PROJECT;

  useEffect(() => {
    if (!open) {
      identityRef.current = null;
      inFlightRef.current = false;
      return;
    }
    identityRef.current = newIdentity();
    // An entry point can name the repository it came from; its project is
    // selected when it is already registered, and created when it is not.
    const seededRepo = initialRepoPath || overview.console_repo;
    const seededProject = overview.projects.find(
      (project) => project.repo_path === seededRepo,
    );
    setStep("form");
    setRepoPath(seededRepo);
    setProjectId(
      seededProject?.project_id ||
        (initialRepoPath
          ? NEW_PROJECT
          : overview.projects[0]?.project_id || ""),
    );
    setTitle(initialTitle);
    setBeadsIssueId(initialBeadsIssueId);
    setError("");
  }, [
    initialBeadsIssueId,
    initialRepoPath,
    initialTitle,
    open,
    overview.console_repo,
    overview.projects,
  ]);

  const create = async () => {
    if (inFlightRef.current || !identityRef.current) return;
    inFlightRef.current = true;
    setSending(true);
    setError("");
    const identity = identityRef.current;
    try {
      let selectedProjectId = projectId;
      if (createsProject) {
        const project = await postJson<CoordinationProject>(
          "/api/coordination/projects",
          {
            project_id: projectIdFor(repoPath.trim(), overview.projects),
            repo_path: repoPath.trim(),
            idempotency_key: identity.key,
          },
        );
        selectedProjectId = project.project_id;
      }
      const epic = await postJson<CoordinationEpic>("/api/coordination/epics", {
        project_id: selectedProjectId,
        epic_id: identity.epicId,
        title: title.trim(),
        beads_issue_id: beadsIssueId.trim(),
        source_kind: initialBeadsIssueId ? "beads" : "",
        source_ref: initialBeadsIssueId,
        idempotency_key: identity.key,
      });
      await onCreated(epic);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Workspace creation failed",
      );
      inFlightRef.current = false;
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog
      onOpenChange={(nextOpen) => {
        if (!sending) onOpenChange(nextOpen);
      }}
      open={open}
    >
      <DialogContent>
        {step === "form" ? (
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (
                title.trim() &&
                (createsProject ? repoPath.trim() : projectId)
              ) {
                setStep("confirm");
              }
            }}
          >
            <DialogHeader>
              <DialogTitle>Создать эпик Workspace</DialogTitle>
              <DialogDescription>
                На пустой установке сначала регистрируется локальный проект,
                затем связанный эпик. Runtime не запускается.
              </DialogDescription>
            </DialogHeader>
            {overview.projects.length ? (
              <label className="grid gap-1.5 text-sm" htmlFor="create-project">
                Проект
                <Select
                  className="text-sm"
                  id="create-project"
                  onChange={(event) => setProjectId(event.target.value)}
                  value={projectId}
                >
                  {overview.projects.map((project) => (
                    <option key={project.project_id} value={project.project_id}>
                      {project.name} — {project.repo_path}
                    </option>
                  ))}
                  <option value={NEW_PROJECT}>Новый проект…</option>
                </Select>
              </label>
            ) : null}
            {createsProject ? (
              <label
                className="grid gap-1.5 text-sm"
                htmlFor="create-repo-path"
              >
                Путь репозитория
                {repositories.length ? (
                  <Select
                    className="text-sm"
                    id="create-repo-path"
                    onChange={(event) => setRepoPath(event.target.value)}
                    value={repoPath}
                  >
                    {repositories.map((repository) => (
                      <option
                        key={repository.repo_path}
                        value={repository.repo_path}
                      >
                        {repository.name} — {repository.repo_path}
                        {overview.projects.some(
                          (project) =>
                            project.repo_path === repository.repo_path,
                        )
                          ? " · уже зарегистрирован"
                          : ""}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    id="create-repo-path"
                    onChange={(event) => setRepoPath(event.target.value)}
                    required
                    value={repoPath}
                  />
                )}
              </label>
            ) : null}
            <label className="grid gap-1.5 text-sm" htmlFor="create-epic-title">
              Название эпика
              <Input
                id="create-epic-title"
                onChange={(event) => setTitle(event.target.value)}
                required
                value={title}
              />
            </label>
            <label
              className="grid gap-1.5 text-sm"
              htmlFor="create-beads-issue"
            >
              Beads issue
              <Input
                id="create-beads-issue"
                onChange={(event) => setBeadsIssueId(event.target.value)}
                placeholder="можно пропустить"
                value={beadsIssueId}
              />
            </label>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Отмена
                </Button>
              </DialogClose>
              <Button type="submit">Проверить данные</Button>
            </DialogFooter>
          </form>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Подтвердите создание</DialogTitle>
              <DialogDescription>
                Это создаст только локальные записи project/epic. Runtime и
                модельный вызов не запускаются.
              </DialogDescription>
            </DialogHeader>
            <dl className="grid gap-2 rounded-lg border border-border-soft bg-surface-low p-3 font-mono text-xs">
              <div className="grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="text-muted-foreground">repo</dt>
                <dd className="break-all">
                  {createsProject
                    ? repoPath.trim()
                    : overview.projects.find(
                        (project) => project.project_id === projectId,
                      )?.repo_path || "—"}
                </dd>
              </div>
              <div className="grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="text-muted-foreground">title</dt>
                <dd>{title.trim()}</dd>
              </div>
              <div className="grid grid-cols-[5.5rem_1fr] gap-2">
                <dt className="text-muted-foreground">Beads</dt>
                <dd>{beadsIssueId.trim() || "—"}</dd>
              </div>
            </dl>
            {error ? (
              <p
                className="rounded-lg border border-destructive p-3 text-sm text-destructive"
                role="alert"
              >
                {error}
              </p>
            ) : null}
            <DialogFooter>
              <Button
                disabled={sending}
                onClick={() => setStep("form")}
                type="button"
                variant="outline"
              >
                Назад
              </Button>
              <Button disabled={sending} onClick={create} type="button">
                {sending
                  ? "Создаю…"
                  : createsProject
                    ? "Создать project и epic"
                    : "Создать epic"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

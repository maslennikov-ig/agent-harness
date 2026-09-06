import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { postJson, requestJson } from "@/shared/api/client";
import type { CoordinationEpic, CoordinationProject } from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import { Radio } from "@/shared/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

interface GithubIssue {
  number: number;
  title: string;
  url: string;
  state: string;
  updated_at: string;
  labels: string[];
}

interface GithubIssuesPayload {
  available: boolean;
  error?: string;
  slug?: string;
  issues?: GithubIssue[];
}

export function GithubIntakeDialog({
  onCreated,
  onOpenChange,
  open,
  project,
}: {
  onCreated: (epic: CoordinationEpic) => Promise<void>;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  project: CoordinationProject;
}) {
  const [selected, setSelected] = useState(0);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const keyRef = useRef("");
  const issues = useQuery({
    enabled: open,
    queryKey: ["github-issues", project.repo_path],
    queryFn: () =>
      requestJson<GithubIssuesPayload>(
        `/api/github/issues?repo=${encodeURIComponent(project.repo_path)}`,
      ),
  });

  useEffect(() => {
    if (!open) return;
    keyRef.current = `github-intake:${crypto.randomUUID()}`;
    setSelected(0);
    setError("");
  }, [open]);

  const issue = (issues.data?.issues ?? []).find(
    (item) => item.number === selected,
  );

  const create = async () => {
    if (!issue || sending) return;
    setSending(true);
    setError("");
    try {
      const epic = await postJson<CoordinationEpic>("/api/coordination/epics", {
        project_id: project.project_id,
        epic_id: `epic-gh-${issue.number}-${keyRef.current.slice(-8)}`,
        title: `#${issue.number} ${issue.title}`,
        source_kind: "github",
        source_ref: `#${issue.number}`,
        source_url: issue.url,
        idempotency_key: keyRef.current,
      });
      await onCreated(epic);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Импорт не удался");
      setSending(false);
      return;
    }
    setSending(false);
  };

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!sending) onOpenChange(next);
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Эпик из GitHub issue</DialogTitle>
          <DialogDescription>
            Читается через `gh issue list` в {project.name}. Создаётся только
            запись эпика Workspace: задачу в Beads панель не заводит, issue на
            GitHub не меняет.
          </DialogDescription>
        </DialogHeader>
        {issues.isLoading ? (
          <p className="text-sm text-muted-foreground">Читаем issues…</p>
        ) : issues.data && !issues.data.available ? (
          <p
            className="rounded-lg border border-warning p-3 text-sm text-warning"
            role="alert"
          >
            {issues.data.error || "GitHub недоступен"}
          </p>
        ) : issues.data?.issues?.length ? (
          <div className="grid max-h-80 gap-2 overflow-auto">
            {issues.data.issues.map((item) => (
              <label
                className="grid cursor-pointer gap-1 rounded-lg border border-border-soft bg-surface-low p-3 text-sm has-checked:border-primary"
                htmlFor={`github-issue-${item.number}`}
                key={item.number}
              >
                <span className="flex items-start gap-2">
                  <Radio
                    checked={selected === item.number}
                    className="mt-1"
                    id={`github-issue-${item.number}`}
                    name="github-issue"
                    onChange={() => setSelected(item.number)}
                    value={item.number}
                  />
                  <span className="min-w-0">
                    <span className="block break-words font-medium">
                      {item.title}
                    </span>
                    <span className="mt-1 block font-mono text-xs text-muted-foreground">
                      #{item.number}
                      {item.labels.length ? ` · ${item.labels.join(", ")}` : ""}
                    </span>
                  </span>
                </span>
              </label>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Открытых issues нет.</p>
        )}
        {error ? (
          <p
            className="rounded-lg border border-destructive p-3 text-sm text-destructive"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Отмена
            </Button>
          </DialogClose>
          <Button disabled={!issue || sending} onClick={create} type="button">
            {sending ? "Создаём…" : "Создать эпик"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

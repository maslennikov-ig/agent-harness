import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { planningCopy } from "@/features/workspace/planning/planning-copy";
import { postJson } from "@/shared/api/client";
import type { CoordinationPlanningArtifact } from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";

export function PlanningPanel({
  artifacts,
  enabled,
  epicId,
  kind,
  onChanged,
  projectId,
}: {
  artifacts: CoordinationPlanningArtifact[];
  enabled: boolean;
  epicId: string;
  kind: "specification" | "plan";
  onChanged: () => Promise<unknown>;
  projectId: string;
}) {
  const [path, setPath] = useState("");
  const [issueId, setIssueId] = useState("");
  const [saving, setSaving] = useState(false);
  const items = artifacts.filter((artifact) => artifact.kind === kind);
  const copy = planningCopy(kind);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!path.trim() || saving) return;
    setSaving(true);
    try {
      await postJson<CoordinationPlanningArtifact>(
        "/api/coordination/planning-artifacts",
        {
          project_id: projectId,
          epic_id: epicId,
          kind,
          path: path.trim(),
          beads_issue_id: issueId.trim(),
        },
      );
      setPath("");
      await onChanged();
      toast.success("Зарегистрировано: путь и digest");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Регистрация не удалась",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)]">
      <section aria-label={copy.accepted} className="min-w-0">
        {items.length ? (
          <ul className="divide-y divide-border-soft rounded-xl border border-border-soft bg-surface-low">
            {items.map((artifact) => (
              <li className="p-4" key={`${artifact.path}:${artifact.digest}`}>
                <code className="block break-all text-sm text-foreground">
                  {artifact.path}
                </code>
                <div className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-muted-foreground">
                  <span>{artifact.digest.slice(0, 12)}</span>
                  <span>{artifact.beads_issue_id || "без Beads-ссылки"}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-xl border border-dashed border-border-soft p-6 text-sm text-muted-foreground">
            Ещё не зарегистрировано. Текст живёт в Git; здесь хранятся только
            путь, digest и Beads-ссылка.
          </div>
        )}
      </section>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{copy.register}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={submit}>
            <label className="block text-sm" htmlFor={`planning-path-${kind}`}>
              <span className="mb-1.5 block text-muted-foreground">
                Путь в репозитории
              </span>
              <Input
                className="rounded-lg"
                id={`planning-path-${kind}`}
                disabled={!enabled}
                onChange={(event) => setPath(event.target.value)}
                placeholder={`docs/superpowers/${kind === "plan" ? "plans" : "specs"}/....md`}
                required
                value={path}
              />
            </label>
            <label className="block text-sm" htmlFor={`planning-issue-${kind}`}>
              <span className="mb-1.5 block text-muted-foreground">
                Beads issue
              </span>
              <Input
                className="rounded-lg"
                id={`planning-issue-${kind}`}
                disabled={!enabled}
                onChange={(event) => setIssueId(event.target.value)}
                placeholder="project-abc"
                value={issueId}
              />
            </label>
            <Button
              className="w-full"
              disabled={!enabled || saving}
              type="submit"
            >
              {saving ? "Регистрируем…" : copy.register}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

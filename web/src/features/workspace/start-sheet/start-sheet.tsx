import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { postJson } from "@/shared/api/client";
import type {
  CoordinationDispatch,
  CoordinationEpic,
  CoordinationPlanningArtifact,
  CoordinationProject,
  CoordinationProvider,
} from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Checkbox } from "@/shared/ui/checkbox";
import { Input } from "@/shared/ui/input";
import { Select } from "@/shared/ui/select";
import { Textarea } from "@/shared/ui/textarea";

export function StartSheet({
  enabled,
  epic,
  initialIssueId,
  onChanged,
  onOpenChange,
  open,
  planning,
  project,
  providers,
}: {
  enabled: boolean;
  epic?: CoordinationEpic;
  initialIssueId: string;
  onChanged: () => Promise<unknown>;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  planning: CoordinationPlanningArtifact[];
  project?: CoordinationProject;
  providers: CoordinationProvider[];
}) {
  const available = useMemo(
    () => providers.filter((provider) => provider.available),
    [providers],
  );
  const [providerId, setProviderId] = useState("");
  const [issueId, setIssueId] = useState("");
  const [writeZone, setWriteZone] = useState("");
  const [taskText, setTaskText] = useState("");
  const [verification, setVerification] = useState("");
  const [taskScale, setTaskScale] = useState<"simple" | "staged">("simple");
  const [reviewRequired, setReviewRequired] = useState(false);
  const [busy, setBusy] = useState(false);
  const actionKey = useRef("");

  useEffect(() => {
    if (!open) return;
    setProviderId((current) =>
      available.some((provider) => provider.id === current)
        ? current
        : (available[0]?.id ?? ""),
    );
    setIssueId(initialIssueId || epic?.beads_issue_id || "");
    setTaskScale("simple");
    actionKey.current = `browser-start:${crypto.randomUUID()}`;
  }, [available, epic?.beads_issue_id, initialIssueId, open]);

  const provider = available.find((item) => item.id === providerId);
  const judge = providers.find((item) => item.id !== providerId);
  const judgeFact = !judge
    ? "нет второго провайдера на этой машине"
    : !reviewRequired
      ? `${judge.id} — не запрашивается: ревью для этой задачи выключено`
      : `${judge.id} — свежая read-only сессия, ${judge.available ? "установлен" : "не найден — ревью нельзя будет запросить"}`;
  const plans = planning.filter((item) => item.kind === "plan");
  const planFact = plans.length
    ? plans
        .map((item) => `${item.path} @ ${item.digest.slice(0, 12)}`)
        .join("; ")
    : "не зарегистрирован — вкладка «План»";

  const setOpen = (next: boolean) => {
    if (!next) actionKey.current = "";
    onOpenChange(next);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!actionKey.current || !taskText.trim() || busy) return;
    setBusy(true);
    try {
      await postJson<CoordinationDispatch>("/api/coordination/dispatches", {
        project_id: project?.project_id ?? "",
        epic_id: epic?.epic_id ?? "",
        provider: providerId,
        task_text: taskText.trim(),
        write_zone: writeZone.trim(),
        verification: verification.trim(),
        beads_issue_id: issueId.trim(),
        review_required: reviewRequired,
        ...(taskScale === "staged" && provider?.root_role
          ? { prompt_card_id: provider.root_role }
          : {}),
        idempotency_key: actionKey.current,
        confirm: true,
      });
      actionKey.current = "";
      setTaskText("");
      await onChanged();
      setOpen(false);
      toast.success("Runtime запущен");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Runtime не запущен",
      );
    } finally {
      setBusy(false);
    }
  };

  const facts = [
    ["репозиторий", project?.repo_path || "—"],
    ["эпик", epic?.title || "—"],
    ["исполнитель", provider?.id || "—"],
    [
      "маршрут",
      taskScale === "staged"
        ? `${provider?.root_role || "orchestrator-stage"} — medium/complex этап`
        : "нейтральный корень — simple/mechanical без этапа и субагента",
    ],
    ["свежий судья", judgeFact],
    [
      "гейт Done",
      reviewRequired
        ? "задача не закроется без принятого вердикта или явного решения пользователя"
        : "не изменяется: ревью для этой задачи не требуется",
    ],
    ["долговременный план", planFact],
    ["write zone", writeZone.trim() || "не задана"],
    [
      "платное действие",
      `один ход ${provider?.id || "runtime"} по вашей подписке; ничего не запускается до кнопки «Старт»`,
    ],
  ];

  return (
    <Dialog onOpenChange={setOpen} open={open}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] overflow-y-auto rounded-lg sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Подтвердите запуск runtime</DialogTitle>
          <DialogDescription>
            Запуск расходует лимит подписки. До кнопки «Старт» модель не
            вызывается.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid gap-2 rounded-xl bg-surface-low p-3 text-sm sm:grid-cols-2">
          {facts.map(([term, value]) => (
            <div className="min-w-0 rounded-lg bg-card p-2.5" key={term}>
              <dt className="text-xs text-muted-foreground">{term}</dt>
              <dd className="mt-1 break-words">{value}</dd>
            </div>
          ))}
        </dl>
        <form className="space-y-3" id="workspace-start-form" onSubmit={submit}>
          <Field htmlFor="workspace-start-provider" label="Исполнитель">
            <Select
              className="rounded-lg"
              id="workspace-start-provider"
              onChange={(event) => setProviderId(event.target.value)}
              value={providerId}
            >
              {available.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id}
                </option>
              ))}
            </Select>
          </Field>
          <Field htmlFor="workspace-start-issue" label="Beads issue">
            <Input
              className="rounded-lg"
              id="workspace-start-issue"
              onChange={(event) => setIssueId(event.target.value)}
              value={issueId}
            />
          </Field>
          <Field htmlFor="workspace-start-scale" label="Масштаб задачи">
            <Select
              className="rounded-lg"
              id="workspace-start-scale"
              onChange={(event) =>
                setTaskScale(event.target.value as "simple" | "staged")
              }
              value={taskScale}
            >
              <option value="simple">Simple / mechanical — без этапа</option>
              <option value="staged">
                Medium / complex — orchestrator-stage
              </option>
            </Select>
          </Field>
          <Field htmlFor="workspace-start-write-zone" label="Write zone">
            <Input
              className="rounded-lg"
              id="workspace-start-write-zone"
              onChange={(event) => setWriteZone(event.target.value)}
              placeholder="web/src/features/workspace"
              value={writeZone}
            />
          </Field>
          <Field htmlFor="workspace-start-task" label="Задача">
            <Textarea
              className="min-h-24"
              id="workspace-start-task"
              onChange={(event) => setTaskText(event.target.value)}
              placeholder="Одна связная цель"
              required
              value={taskText}
            />
          </Field>
          <Field htmlFor="workspace-start-verification" label="Проверка">
            <Input
              className="rounded-lg"
              id="workspace-start-verification"
              onChange={(event) => setVerification(event.target.value)}
              placeholder="какие проверки считаются достаточными"
              value={verification}
            />
          </Field>
          <label
            className="flex items-start gap-2 text-sm"
            htmlFor="workspace-start-review"
          >
            <Checkbox
              checked={reviewRequired}
              className="mt-1"
              id="workspace-start-review"
              onChange={(event) => setReviewRequired(event.target.checked)}
            />
            <span>Требуется кросс-провайдерное ревью перед Done</span>
          </label>
        </form>
        <DialogFooter>
          <Button
            onClick={() => setOpen(false)}
            type="button"
            variant="outline"
          >
            Отмена
          </Button>
          <Button
            disabled={!enabled || busy || !available.length}
            form="workspace-start-form"
            type="submit"
          >
            {busy ? "Запускаем…" : "Старт"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  children,
  htmlFor,
  label,
}: {
  children: React.ReactNode;
  htmlFor: string;
  label: string;
}) {
  return (
    <div className="text-sm">
      <label className="mb-1.5 block text-muted-foreground" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  );
}

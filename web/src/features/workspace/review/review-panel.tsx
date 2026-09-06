import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";
import { ReviewGate } from "@/features/workspace/review/review-panel-gate";
import { ReviewRound } from "@/features/workspace/review/review-round";
import { postJson } from "@/shared/api/client";
import type { CoordinationReviewExecutor } from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";

function actionKey(ref: React.MutableRefObject<string>) {
  if (!ref.current) ref.current = `browser-review:${crypto.randomUUID()}`;
  return ref.current;
}

export function ReviewPanel({
  entry,
  maxRounds,
  onChanged,
}: {
  entry: CoordinationReviewExecutor;
  maxRounds: number;
  onChanged: () => Promise<unknown>;
}) {
  const keyRef = useRef("");
  const [busy, setBusy] = useState(false);
  const [requirements, setRequirements] = useState("");
  const [receiptPath, setReceiptPath] = useState("");
  const [diffRefs, setDiffRefs] = useState("");
  const [reason, setReason] = useState("");

  if (!entry.review_required && entry.rounds.length === 0) {
    return (
      <section className="mt-4 rounded-xl border border-border-soft p-4">
        <h4 className="font-semibold">Кросс-провайдерное ревью</h4>
        <p className="mt-2 text-sm text-muted-foreground">
          Политика задачи его не требует, поэтому Done не заблокирован.
        </p>
      </section>
    );
  }

  const act = async (path: string, body: Record<string, unknown>) => {
    setBusy(true);
    try {
      await postJson(path, body);
      keyRef.current = "";
      await onChanged();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Действие ревью не выполнено",
      );
    } finally {
      setBusy(false);
    }
  };

  const requestReview = (event: FormEvent) => {
    event.preventDefault();
    void act("/api/coordination/reviews", {
      executor_dispatch_id: entry.dispatch_id,
      requirements: requirements.trim(),
      receipt_path: receiptPath.trim(),
      diff_refs: diffRefs
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
      idempotency_key: actionKey(keyRef),
      confirm: true,
    });
  };

  return (
    <section
      className="mt-4 space-y-3 rounded-xl border border-border-soft p-4"
      data-current={entry.is_current}
    >
      <h4 className="font-semibold">Кросс-провайдерное ревью</h4>
      <ReviewGate entry={entry} />
      {entry.rounds.length ? (
        entry.rounds.map((round) => (
          <ReviewRound
            key={round.review_id}
            maxRounds={maxRounds}
            round={round}
          />
        ))
      ) : (
        <p className="text-sm text-muted-foreground">Вердиктов пока нет.</p>
      )}
      {!entry.is_current ? (
        <p className="text-sm text-muted-foreground">
          Действия ревью доступны только на текущем прогоне задачи.
        </p>
      ) : entry.next_action === "request_review" ? (
        <form className="space-y-3" onSubmit={requestReview}>
          <p className="text-sm text-muted-foreground">
            Раунд {entry.rounds.length + 1}: свежая read-only сессия другого
            провайдера.
          </p>
          <Textarea
            aria-label="Требования для судьи"
            className="min-h-24 rounded-lg p-3 text-sm"
            onChange={(event) => setRequirements(event.target.value)}
            placeholder="Критерии, по которым судья выносит вердикт"
            required
            value={requirements}
          />
          <Input
            aria-label="Расписка приёмки"
            className="rounded-lg text-sm"
            onChange={(event) => setReceiptPath(event.target.value)}
            placeholder=".codex/stages/<stage>/acceptance-receipt.json"
            required
            value={receiptPath}
          />
          <Textarea
            aria-label="Ссылки на диф"
            className="min-h-20 rounded-lg p-3 text-sm"
            onChange={(event) => setDiffRefs(event.target.value)}
            placeholder="Одна ссылка или команда на строку"
            value={diffRefs}
          />
          <p className="text-sm text-warning">
            Платное действие: один ход судьи по подписке.
          </p>
          <Button disabled={busy} type="submit">
            Запросить судью
          </Button>
        </form>
      ) : entry.next_action === "return_findings" ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Находки вернутся в ту же сессию исполнителя.
          </p>
          <p className="text-sm text-warning">
            Платное действие: один ход {entry.executor_provider}.
          </p>
          <Button
            disabled={busy}
            onClick={() =>
              void act("/api/coordination/reviews/findings-return", {
                executor_dispatch_id: entry.dispatch_id,
                idempotency_key: actionKey(keyRef),
                confirm: true,
              })
            }
            type="button"
          >
            Вернуть находки исполнителю
          </Button>
        </div>
      ) : entry.next_action === "escalate" ? (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            const submitter = (event.nativeEvent as SubmitEvent)
              .submitter as HTMLButtonElement;
            void act("/api/coordination/reviews/decision", {
              executor_dispatch_id: entry.dispatch_id,
              decision:
                submitter.value === "rejected" ? "rejected" : "accepted",
              reason: reason.trim(),
              idempotency_key: actionKey(keyRef),
            });
          }}
        >
          <p className="text-sm text-muted-foreground">
            Цикл исчерпан: третьего вызова модели не будет — решение за вами.
          </p>
          <Input
            aria-label="Причина решения"
            className="rounded-lg"
            onChange={(event) => setReason(event.target.value)}
            required
            value={reason}
          />
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} type="submit" value="accepted">
              Принять результат
            </Button>
            <Button
              disabled={busy}
              type="submit"
              value="rejected"
              variant="outline"
            >
              Отклонить результат
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}

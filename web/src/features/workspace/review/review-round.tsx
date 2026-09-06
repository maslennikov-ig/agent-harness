import type { CoordinationReviewRound } from "@/shared/api/types";

const outcomeLabels: Record<string, string> = {
  accepted: "принято",
  changes_requested: "запрошены правки",
  unreadable: "вердикт не прочитан",
};
const severityLabels: Record<string, string> = {
  blocker: "блокер",
  major: "существенно",
  minor: "мелочь",
  note: "заметка",
};

export function ReviewRound({
  maxRounds,
  round,
}: {
  maxRounds: number;
  round: CoordinationReviewRound;
}) {
  return (
    <article
      className="rounded-lg bg-surface-low p-3"
      data-outcome={round.outcome}
    >
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-muted-foreground">
          {round.decided_by === "user"
            ? "после цикла"
            : `раунд ${round.round} из ${maxRounds}`}
        </span>
        <span>
          {round.decided_by === "user"
            ? "решение пользователя"
            : `судья ${round.judge_provider}`}
        </span>
        <span className="rounded-md bg-runtime-accent-soft px-2 py-1 text-primary">
          {outcomeLabels[round.outcome] ?? round.outcome}
        </span>
        {round.revision_returned ? (
          <span className="rounded-md bg-copy-accent-soft px-2 py-1 text-secondary">
            находки возвращены
          </span>
        ) : null}
      </header>
      <p className="mt-2 text-sm">{round.summary}</p>
      {round.findings.length ? (
        <ul className="mt-3 space-y-2">
          {round.findings.map((finding) => (
            <li
              className="rounded-md border border-border-soft p-2 text-sm"
              key={finding.id}
            >
              <span className="mr-2 font-medium">
                {severityLabels[finding.severity] ?? finding.severity}
              </span>
              <span className="mr-2 font-mono text-xs text-muted-foreground">
                {finding.id}
              </span>
              {finding.summary}
              {!finding.actionable ? (
                <span className="ml-2 text-xs text-muted-foreground">
                  не требует правки
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {round.judge_session_id ? (
        <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
          свежая сессия {round.judge_session_id}
        </p>
      ) : null}
    </article>
  );
}

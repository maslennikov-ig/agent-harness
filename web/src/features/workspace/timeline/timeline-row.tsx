import { FileText } from "lucide-react";
import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";
import { MarkdownContent } from "@/shared/ui/markdown";

const kindLabels: Record<string, string> = {
  answer: "ответ",
  blocker: "блокер",
  checkpoint: "чекпойнт",
  decision: "решение",
  message: "сообщение",
  question: "вопрос",
  result: "результат",
  review: "ревью",
};

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function TimelineRow({ event }: { event: CoordinationEvent }) {
  return (
    <article className="min-w-0 py-2" data-event-id={event.event_id}>
      <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span className="rounded-md bg-surface-mid px-1.5 py-0.5 font-medium text-foreground/80">
          {kindLabels[event.event_kind] ?? event.event_kind}
        </span>
        {event.beads_issue_id ? (
          <span className="font-mono">{event.beads_issue_id}</span>
        ) : null}
        <time dateTime={event.created_at}>{formatTime(event.created_at)}</time>
        <span className="font-mono">#{event.seq}</span>
      </div>
      <MarkdownContent source={event.body_text} />
      {event.artifact_refs.length ? (
        <ul className="mt-3 space-y-1.5" aria-label="Артефакты">
          {event.artifact_refs.map((artifact) => (
            <li
              className="flex min-w-0 items-center gap-2 rounded-lg border border-border-soft bg-surface-low px-3 py-2 text-xs"
              key={`${artifact.path}:${artifact.digest}`}
            >
              <FileText
                aria-hidden="true"
                className="size-3.5 shrink-0 text-primary"
              />
              <code className="truncate">{artifact.path}</code>
              <span className="ml-auto shrink-0 font-mono text-muted-foreground">
                {artifact.digest.slice(0, 12)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

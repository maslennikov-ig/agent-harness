import { Bot, CircleUserRound, Cog } from "lucide-react";
import type { TimelineGroupEntry } from "@/features/workspace/lib/formatTimelineMessages";
import { TimelineRow } from "@/features/workspace/timeline/timeline-row";

const authorLabels: Record<string, string> = {
  claude: "Claude",
  codex: "Codex",
  system: "Панель",
  user: "Вы",
};

function AuthorIcon({ kind }: { kind: string }) {
  if (kind === "user") return <CircleUserRound aria-hidden="true" />;
  if (kind === "system") return <Cog aria-hidden="true" />;
  return <Bot aria-hidden="true" />;
}

export function TimelineGroup({ group }: { group: TimelineGroupEntry }) {
  return (
    <section
      className="mx-3 my-1 flex min-w-0 gap-3 rounded-2xl px-3 py-3 transition-colors hover:bg-surface-low/70 sm:mx-4"
      data-author={group.authorKind}
      data-timeline-group={group.key}
    >
      <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl border border-border-soft bg-surface-mid text-primary [&_svg]:size-4">
        <AuthorIcon kind={group.authorKind} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">
          {authorLabels[group.authorKind] ?? group.authorKind}
        </p>
        <div className="divide-y divide-border-soft/60">
          {group.events.map((event) => (
            <TimelineRow event={event} key={event.event_id} />
          ))}
        </div>
      </div>
    </section>
  );
}

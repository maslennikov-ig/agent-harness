import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import {
  DocsDependencies,
  filterDependencies,
} from "@/features/docs-context/docs-dependencies";
import { DocsSyncPlan } from "@/features/docs-context/docs-sync-plan";
import type {
  DocsContextPayload,
  DocsFilter,
} from "@/features/docs-context/types";
import { useProjectionQuery } from "@/shared/api/projection";
import { Button } from "@/shared/ui/button";
import { RawInspector } from "@/shared/ui/raw-inspector";
import { FilterBar, ToneBadge } from "@/shared/ui/projection";

const screen = screenById("docs-context");
const filters: Array<{ label: string; value: DocsFilter }> = [
  { label: "Все", value: "all" },
  { label: "Fallback", value: "fallback" },
  { label: "Missing", value: "missing" },
  { label: "Stale", value: "stale" },
  { label: "OK", value: "ok" },
];

export function DocsContextScreen() {
  const { query, refresh } =
    useProjectionQuery<DocsContextPayload>("/api/docs-context");
  const [filter, setFilter] = useState<DocsFilter>("all");
  const data = query.data;
  const rows = useMemo(
    () => filterDependencies(data?.dependencies || [], filter),
    [data?.dependencies, filter],
  );
  const copy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      toast.success("Команда скопирована");
    } catch {
      toast.error("Не удалось скопировать");
    }
  };
  const counts = data?.summary.status_counts || {};
  const planCounts = data?.sync_plan?.summary?.status_counts || {};
  const context7 = data?.context7?.status || "unknown";
  const inlineKey = data?.context7?.inline_key_in_codex_config
    ? "inline-key warning"
    : "env-only";
  return (
    <ScreenFrame
      actions={
        <Button onClick={refresh} size="sm" type="button" variant="outline">
          <RefreshCw aria-hidden="true" /> Обновить
        </Button>
      }
      marker={{ kind: "native", id: "docs-context" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Загружаем docs context…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          {query.error instanceof Error
            ? query.error.message
            : "Docs context недоступен"}
        </p>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <ToneBadge>projects {data.summary.projects}</ToneBadge>
            <ToneBadge>deps {data.summary.dependencies}</ToneBadge>
            <ToneBadge>tracks {data.summary.tracks}</ToneBadge>
            <ToneBadge tone={counts.missing ? "warn" : "muted"}>
              missing {counts.missing || 0}
            </ToneBadge>
            <ToneBadge tone={counts.stale ? "warn" : "muted"}>
              stale {counts.stale || 0}
            </ToneBadge>
            <ToneBadge tone={planCounts.future ? "warn" : "muted"}>
              future-docs {planCounts.future || 0}
            </ToneBadge>
            <ToneBadge tone={context7 === "ok" ? "neutral" : "warn"}>
              Context7 {context7} · {inlineKey}
            </ToneBadge>
            <span className="break-all font-mono text-xs text-muted-foreground">
              {data.summary.stack_path}
            </span>
          </div>
          <DocsSyncPlan data={data} onCopy={copy} />
          <FilterBar label="Фильтр документации">
            {filters.map((item) => (
              <Button
                aria-pressed={filter === item.value}
                key={item.value}
                onClick={() => setFilter(item.value)}
                size="sm"
                type="button"
                variant={filter === item.value ? "default" : "outline"}
              >
                {item.label}
              </Button>
            ))}
          </FilterBar>
          <DocsDependencies onCopy={copy} rows={rows} />
          <RawInspector data={data} />
        </div>
      ) : null}
    </ScreenFrame>
  );
}

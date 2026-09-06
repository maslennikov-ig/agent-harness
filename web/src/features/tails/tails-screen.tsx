import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import type { BeadsPayload } from "@/features/beads/types";
import { RepoRadar } from "@/features/tails/radar";
import { TailBranchRow } from "@/features/tails/tail-branch";
import { TailGroupCard } from "@/features/tails/tail-group";
import {
  filterTails,
  groupTails,
  sortTails,
  tailKey,
  type TailSort,
} from "@/features/tails/tails-lib";
import type { Tail, TailPrPayload, TailsPayload } from "@/features/tails/types";
import { requestJson } from "@/shared/api/client";
import { useProjectionQuery } from "@/shared/api/projection";
import { LIST_REFRESH_INTERVAL_MS } from "@/shared/api/queries";
import { Button } from "@/shared/ui/button";
import { Checkbox } from "@/shared/ui/checkbox";
import { Freshness } from "@/shared/ui/freshness";
import { Input } from "@/shared/ui/input";
import { FilterBar, ToneBadge } from "@/shared/ui/projection";
import { Select } from "@/shared/ui/select";
import { RawInspector } from "@/shared/ui/raw-inspector";

const screen = screenById("tails");

function toggleSet(value: Set<string>, key: string) {
  const next = new Set(value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

export function TailsScreen() {
  const { query, refresh } = useProjectionQuery<TailsPayload>(
    "/api/tails?days=5",
    {
      refetchInterval: LIST_REFRESH_INTERVAL_MS,
    },
  );
  const beads = useQuery({
    queryKey: ["tails", "beads-counts"],
    queryFn: () => requestJson<BeadsPayload>("/api/beads"),
  });
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<"all" | Tail["kind"]>("all");
  const [minimumAge, setMinimumAge] = useState(5);
  const [sort, setSort] = useState<TailSort>("oldest");
  const [grouped, setGrouped] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState(new Set<string>());
  const [expandedTails, setExpandedTails] = useState(new Set<string>());
  const [expandedRadar, setExpandedRadar] = useState(new Set<string>());
  const [prStatuses, setPrStatuses] = useState<Record<string, TailPrPayload>>(
    {},
  );
  const [loadingPr, setLoadingPr] = useState(new Set<string>());
  const data = query.data;
  const filtered = useMemo(
    () => filterTails(data?.tails || [], search, kind, minimumAge),
    [data?.tails, kind, minimumAge, search],
  );
  const sorted = useMemo(() => sortTails(filtered, sort), [filtered, sort]);
  const groups = useMemo(() => groupTails(filtered, sort), [filtered, sort]);
  const localCount = filtered.filter((tail) => tail.kind === "local").length;
  const beadCounts = useMemo(
    () =>
      new Map(
        (beads.data?.repos || []).map((repo) => [repo.repo_path, repo.counts]),
      ),
    [beads.data?.repos],
  );

  const copy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      toast.success("Команда скопирована");
    } catch {
      toast.error("Не удалось скопировать");
    }
  };

  const checkPr = async (repoPath: string) => {
    if (loadingPr.has(repoPath)) return;
    setLoadingPr((current) => new Set(current).add(repoPath));
    try {
      const params = new URLSearchParams({ repo: repoPath });
      if (prStatuses[repoPath]) params.set("fresh", "1");
      const status = await requestJson<TailPrPayload>(
        `/api/tails/prs?${params.toString()}`,
      );
      setPrStatuses((current) => ({ ...current, [repoPath]: status }));
      if (!status.available)
        toast.warning(status.error || "PR-статусы недоступны");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "PR-статусы недоступны",
      );
    } finally {
      setLoadingPr((current) => {
        const next = new Set(current);
        next.delete(repoPath);
        return next;
      });
    }
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
      marker={{ kind: "native", id: "tails" }}
      screen={screen}
    >
      {query.isLoading ? (
        <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
          Загружаем хвосты…
        </p>
      ) : query.error ? (
        <p className="rounded-xl border border-destructive p-5 text-destructive">
          {query.error instanceof Error
            ? query.error.message
            : "Хвосты недоступны"}
        </p>
      ) : data ? (
        <div className="space-y-4">
          <RepoRadar
            beadCounts={beadCounts}
            expanded={expandedRadar}
            onCopy={copy}
            onToggle={(key) =>
              setExpandedRadar((value) => toggleSet(value, key))
            }
            rows={data.radar || []}
          />
          <FilterBar>
            <label
              className="min-w-[16rem] flex-1 text-xs font-medium text-muted-foreground"
              htmlFor="tail-search"
            >
              Поиск
              <Input
                aria-label="Поиск по хвостам"
                className="mt-1"
                id="tail-search"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Фильтр project / branch / subject"
                type="search"
                value={search}
              />
            </label>
            <label
              className="text-xs font-medium text-muted-foreground"
              htmlFor="tail-kind"
            >
              Тип
              <Select
                aria-label="Тип ветки"
                className="text-sm"
                containerClassName="mt-1"
                id="tail-kind"
                onChange={(event) => setKind(event.target.value as typeof kind)}
                value={kind}
              >
                <option value="all">All</option>
                <option value="local">Local</option>
                <option value="remote">Remote</option>
              </Select>
            </label>
            <label
              className="text-xs font-medium text-muted-foreground"
              htmlFor="tail-age"
            >
              Возраст
              <Select
                aria-label="Минимальный возраст"
                className="text-sm"
                containerClassName="mt-1"
                id="tail-age"
                onChange={(event) => setMinimumAge(Number(event.target.value))}
                value={minimumAge}
              >
                {[5, 14, 30, 90].map((age) => (
                  <option key={age} value={age}>
                    {age}+ дней
                  </option>
                ))}
              </Select>
            </label>
            <label
              className="text-xs font-medium text-muted-foreground"
              htmlFor="tail-sort"
            >
              Порядок
              <Select
                aria-label="Сортировка"
                className="text-sm"
                containerClassName="mt-1"
                id="tail-sort"
                onChange={(event) => setSort(event.target.value as TailSort)}
                value={sort}
              >
                <option value="oldest">Самые старые</option>
                <option value="count">Больше хвостов</option>
                <option value="project">По проекту</option>
              </Select>
            </label>
            <label
              className="flex h-control items-center gap-2 text-sm"
              htmlFor="tail-grouped"
            >
              <Checkbox
                checked={grouped}
                id="tail-grouped"
                onChange={(event) => setGrouped(event.target.checked)}
              />
              Группировать
            </label>
          </FilterBar>
          <div
            className="flex flex-wrap gap-2"
            aria-label="Сводка по хвостам"
            role="status"
          >
            <ToneBadge>
              {filtered.length} из {data.tails.length} хвостов
            </ToneBadge>
            <ToneBadge>
              {groups.length} проектов из {data.repo_count}
            </ToneBadge>
            <ToneBadge tone="muted">{localCount} local</ToneBadge>
            <ToneBadge tone="muted">
              {filtered.length - localCount} remote
            </ToneBadge>
          </div>
          <section aria-label="Список хвостов">
            {!filtered.length ? (
              <p className="rounded-xl bg-surface-low p-5 text-muted-foreground">
                Нет хвостов под выбранные фильтры.
              </p>
            ) : grouped ? (
              <div className="grid gap-3">
                {groups.map((group) => (
                  <TailGroupCard
                    expanded={expandedGroups.has(group.key)}
                    expandedTails={expandedTails}
                    group={group}
                    key={group.key}
                    loadingPr={loadingPr.has(group.repo_path)}
                    onCheckPr={() => checkPr(group.repo_path)}
                    onCopy={copy}
                    onToggle={() =>
                      setExpandedGroups((value) => toggleSet(value, group.key))
                    }
                    onToggleTail={(key) =>
                      setExpandedTails((value) => toggleSet(value, key))
                    }
                    prStatus={prStatuses[group.repo_path]}
                  />
                ))}
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-border-soft bg-card">
                {sorted.map((tail) => {
                  const key = tailKey(tail);
                  return (
                    <TailBranchRow
                      expanded={expandedTails.has(key)}
                      key={key}
                      onCopy={copy}
                      onToggle={() =>
                        setExpandedTails((value) => toggleSet(value, key))
                      }
                      prStatus={prStatuses[tail.repo_path]}
                      tail={tail}
                    />
                  );
                })}
              </div>
            )}
          </section>
          <RawInspector data={data} />
        </div>
      ) : null}
    </ScreenFrame>
  );
}

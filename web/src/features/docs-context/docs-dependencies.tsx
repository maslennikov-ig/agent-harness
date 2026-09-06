import type { DocsDependency, DocsFilter } from "@/features/docs-context/types";
import { Button } from "@/shared/ui/button";
import { ToneBadge } from "@/shared/ui/projection";

export function filterDependencies(rows: DocsDependency[], filter: DocsFilter) {
  if (filter === "all") return rows;
  if (filter === "fallback") return rows.filter((row) => row.fallback);
  if (filter === "ok") {
    return rows.filter((row) => row.status === "ok" || row.status === "future");
  }
  return rows.filter((row) => row.status === filter);
}

export function DocsDependencies({
  onCopy,
  rows,
}: {
  onCopy: (command: string) => void;
  rows: DocsDependency[];
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border-soft bg-card">
      <table className="w-full min-w-[64rem] text-left text-sm">
        <thead className="bg-surface-low text-xs text-muted-foreground">
          <tr>
            {[
              "Project",
              "Dependency",
              "Used",
              "Docs",
              "Status",
              "Source",
              "Commands",
            ].map((label) => (
              <th className="px-3 py-2 font-medium" key={label} scope="col">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-soft">
          {rows.length ? (
            rows.map((row) => {
              const status =
                row.status === "future" ? "future-docs" : row.status;
              const queryable = row.status === "ok" || row.status === "future";
              const command = queryable
                ? row.commands?.query || ""
                : row.commands?.install || "";
              return (
                <tr
                  key={`${row.project}:${row.ecosystem}:${row.dependency}:${row.used_version}`}
                >
                  <td className="px-3 py-2">{row.project}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {row.ecosystem}/{row.dependency}
                  </td>
                  <td className="px-3 py-2">{row.used_version}</td>
                  <td className="px-3 py-2">
                    {row.docs_package || row.dependency}@
                    {row.docs_version || row.docs_target_version}
                  </td>
                  <td className="px-3 py-2">
                    <ToneBadge tone={row.status === "ok" ? "ok" : "warn"}>
                      {status}
                    </ToneBadge>
                  </td>
                  <td className="px-3 py-2">
                    <ToneBadge tone={row.fallback ? "warn" : "neutral"}>
                      {row.fallback ? "L2" : "L1"}
                    </ToneBadge>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <Button
                        onClick={() => onCopy(command)}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        {queryable ? "query" : "install"}
                      </Button>
                      <Button
                        onClick={() => onCopy(row.commands?.add_template || "")}
                        size="sm"
                        type="button"
                        variant="outline"
                      >
                        add
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })
          ) : (
            <tr>
              <td className="px-3 py-4 text-muted-foreground" colSpan={7}>
                Нет зависимостей под выбранный фильтр.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

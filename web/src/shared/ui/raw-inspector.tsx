import { DataInspector } from "@/shared/ui/data-inspector";

export function RawInspector({ data }: { data: unknown }) {
  return (
    <details
      className="min-w-0 rounded-xl border border-border-soft bg-surface-low"
      data-raw-inspector
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-muted-foreground">
        Сырые данные
      </summary>
      <div className="border-t border-border-soft p-3">
        <DataInspector data={data} />
      </div>
    </details>
  );
}

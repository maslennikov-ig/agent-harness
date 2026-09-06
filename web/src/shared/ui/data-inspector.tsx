import type { ReactNode } from "react";

function primitive(value: unknown): ReactNode {
  if (value === null)
    return <span className="text-muted-foreground">null</span>;
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function Node({
  depth,
  label,
  value,
}: {
  depth: number;
  label: string;
  value: unknown;
}) {
  if (typeof value !== "object" || value === null) {
    return (
      <div className="grid min-w-0 gap-1 py-1 sm:grid-cols-[minmax(8rem,0.35fr)_1fr]">
        <dt className="break-words font-mono text-xs text-muted-foreground">
          {label}
        </dt>
        <dd className="min-w-0 break-words text-sm">{primitive(value)}</dd>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value);
  const total = Array.isArray(value) ? value.length : entries.length;
  return (
    <details
      className="min-w-0 rounded-lg border border-border-soft bg-card"
      open
    >
      <summary className="cursor-pointer break-words px-3 py-2 font-mono text-xs text-muted-foreground">
        {label} · {total}
      </summary>
      <dl className="min-w-0 border-t border-border-soft px-3 py-1">
        {entries.map(([key, item]) => (
          <Node
            depth={depth + 1}
            key={`${depth}:${key}`}
            label={key}
            value={item}
          />
        ))}
      </dl>
    </details>
  );
}

export function DataInspector({ data }: { data: unknown }) {
  return (
    <div className="grid min-w-0 gap-2" data-data-inspector>
      <Node depth={0} label="payload" value={data} />
    </div>
  );
}

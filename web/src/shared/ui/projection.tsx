import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import { Badge } from "@/shared/ui/badge";

export function SectionList({
  actions,
  children,
  className,
  description,
  title,
}: {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  description?: ReactNode;
  title: ReactNode;
}) {
  return (
    <section
      className={cn(
        "min-w-0 rounded-xl border border-border-soft bg-card",
        className,
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border-soft px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-semibold">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions}
      </header>
      <div className="divide-y divide-border-soft">{children}</div>
    </section>
  );
}

export function LabelledRow({
  children,
  className,
  label,
}: {
  children: ReactNode;
  className?: string;
  label: ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid min-w-0 gap-1 px-4 py-3 sm:grid-cols-[minmax(8rem,0.35fr)_1fr]",
        className,
      )}
    >
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="min-w-0 break-words text-sm">{children}</div>
    </div>
  );
}

const toneClasses = {
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  muted: "border-border-soft bg-muted/10 text-muted-foreground",
  neutral: "border-border-soft bg-surface-low text-foreground",
  ok: "border-secondary/40 bg-secondary/10 text-secondary",
  warn: "border-warning/40 bg-warning/10 text-warning",
} as const;

export function ToneBadge({
  children,
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  tone?: keyof typeof toneClasses;
}) {
  return (
    <Badge
      className={cn(toneClasses[tone], className)}
      variant="outline"
      {...props}
    >
      {children}
    </Badge>
  );
}

export function FilterBar({
  children,
  className,
  label = "Фильтры",
}: {
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <fieldset
      className={cn(
        "flex min-w-0 flex-wrap items-end gap-3 rounded-xl border border-border-soft bg-surface-low p-3",
        className,
      )}
    >
      <legend className="sr-only">{label}</legend>
      {children}
    </fieldset>
  );
}

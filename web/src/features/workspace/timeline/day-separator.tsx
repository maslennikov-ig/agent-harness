export function TimelineDaySeparator({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <hr className="h-px flex-1 border-0 bg-border-soft" />
      <span className="rounded-full border border-border-soft bg-background/80 px-3 py-1 text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <hr className="h-px flex-1 border-0 bg-border-soft" />
    </div>
  );
}

export function TimelineUnreadDivider({ count }: { count: number }) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-2"
      data-testid="unread-divider"
    >
      <span className="h-px flex-1 bg-primary/70" />
      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
        Непрочитанные · {count}
      </span>
      <span className="h-px flex-1 bg-primary/70" />
    </div>
  );
}

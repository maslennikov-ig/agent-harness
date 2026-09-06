import type { ReactNode } from "react";
import type { ScreenDescriptor } from "@/app/navigation";

export function ScreenFrame({
  screen,
  actions,
  children,
  marker,
}: {
  screen: ScreenDescriptor;
  actions?: ReactNode;
  children: ReactNode;
  marker: { kind: "native" | "legacy"; id: string };
}) {
  const markerProps =
    marker.kind === "native"
      ? { "data-native-screen": marker.id }
      : { "data-legacy-screen": marker.id };

  return (
    <section
      className="w-full px-4 py-6 sm:px-6 lg:px-10 lg:py-9"
      {...markerProps}
    >
      <header className="mb-7 flex flex-col gap-4 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-primary">
            {screen.group}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            {screen.title}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
            {screen.description}
          </p>
        </div>
        {actions ? (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        ) : null}
      </header>
      {children}
    </section>
  );
}

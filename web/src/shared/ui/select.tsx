import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/shared/lib/cn";

/**
 * Native `<select>` at the shared control height. Screens pass `<option>`
 * children; the chevron is decorative and sits above the native arrow, which
 * `appearance-none` removes so the control matches `Input` and `Button`.
 */
const Select = React.forwardRef<
  HTMLSelectElement,
  React.ComponentProps<"select"> & {
    /**
     * Layout classes for the positioning wrapper (width caps, margins). They
     * belong there rather than on the control, which is always `w-full`.
     */
    containerClassName?: string;
  }
>(({ className, containerClassName, children, ...props }, ref) => {
  return (
    <span className={cn("relative block min-w-0", containerClassName)}>
      <select
        className={cn(
          "flex h-control w-full min-w-0 appearance-none rounded-md border border-input bg-transparent py-1 pl-3 pr-8 text-base text-foreground shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          className,
        )}
        ref={ref}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </span>
  );
});
Select.displayName = "Select";

export { Select };

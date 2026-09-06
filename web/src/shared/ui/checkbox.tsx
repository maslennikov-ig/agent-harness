import * as React from "react";

import { cn } from "@/shared/lib/cn";

/**
 * Native checkbox/radio at one size and accent. These are not text controls,
 * so they keep the browser's own box instead of the `Input` geometry; the
 * point of the wrapper is that no screen retypes the size or accent colour.
 */
type ToggleProps = Omit<React.ComponentProps<"input">, "type">;

const toggleClasses =
  "size-4 shrink-0 accent-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

const Checkbox = React.forwardRef<HTMLInputElement, ToggleProps>(
  ({ className, ...props }, ref) => (
    <input
      className={cn(toggleClasses, className)}
      ref={ref}
      type="checkbox"
      {...props}
    />
  ),
);
Checkbox.displayName = "Checkbox";

const Radio = React.forwardRef<HTMLInputElement, ToggleProps>(
  ({ className, ...props }, ref) => (
    <input
      className={cn(toggleClasses, className)}
      ref={ref}
      type="radio"
      {...props}
    />
  ),
);
Radio.displayName = "Radio";

export { Checkbox, Radio };

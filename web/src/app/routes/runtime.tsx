import { createFileRoute } from "@tanstack/react-router";
import { RuntimeScreen } from "@/features/runtime/runtime-screen";

export const Route = createFileRoute("/runtime")({
  component: RuntimeScreen,
});

import { createFileRoute } from "@tanstack/react-router";
import { TailsScreen } from "@/features/tails/tails-screen";

export const Route = createFileRoute("/tails")({
  component: TailsScreen,
});

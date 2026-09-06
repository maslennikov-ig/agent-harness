import { createFileRoute } from "@tanstack/react-router";
import { PromptsScreen } from "@/features/prompts/prompts-screen";

export const Route = createFileRoute("/prompts")({
  component: PromptsScreen,
});

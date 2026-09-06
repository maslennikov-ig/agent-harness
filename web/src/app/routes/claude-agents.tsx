import { createFileRoute } from "@tanstack/react-router";
import { ClaudeAgentsScreen } from "@/features/claude-agents/claude-agents-screen";

export const Route = createFileRoute("/claude-agents")({
  component: ClaudeAgentsScreen,
});

import { createFileRoute } from "@tanstack/react-router";
import { WorkspaceScreen } from "@/features/workspace/workspace-screen";

export const Route = createFileRoute("/workspace/")({
  component: WorkspaceScreen,
});

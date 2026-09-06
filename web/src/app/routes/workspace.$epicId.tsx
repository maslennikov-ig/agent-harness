import { createFileRoute } from "@tanstack/react-router";
import { WorkspaceScreen } from "@/features/workspace/workspace-screen";

export const Route = createFileRoute("/workspace/$epicId")({
  component: WorkspaceEpicRoute,
});

function WorkspaceEpicRoute() {
  const { epicId } = Route.useParams();
  return <WorkspaceScreen epicId={epicId} />;
}

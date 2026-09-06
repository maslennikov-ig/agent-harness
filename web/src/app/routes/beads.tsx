import { createFileRoute } from "@tanstack/react-router";
import { BeadsScreen } from "@/features/beads/beads-screen";

export const Route = createFileRoute("/beads")({
  component: BeadsScreen,
});

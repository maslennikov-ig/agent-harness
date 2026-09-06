import { createFileRoute } from "@tanstack/react-router";
import { EnvironmentScreen } from "@/features/environment/environment-screen";

export const Route = createFileRoute("/environment")({
  component: EnvironmentScreen,
});

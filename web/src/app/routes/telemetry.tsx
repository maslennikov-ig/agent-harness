import { createFileRoute } from "@tanstack/react-router";
import { TelemetryScreen } from "@/features/telemetry/telemetry-screen";

export const Route = createFileRoute("/telemetry")({
  component: TelemetryScreen,
});

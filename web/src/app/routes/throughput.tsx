import { createFileRoute } from "@tanstack/react-router";
import { ThroughputScreen } from "@/features/throughput/throughput-screen";

export const Route = createFileRoute("/throughput")({
  component: ThroughputScreen,
});

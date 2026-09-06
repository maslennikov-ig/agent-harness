import { createFileRoute } from "@tanstack/react-router";
import { DocsContextScreen } from "@/features/docs-context/docs-context-screen";

export const Route = createFileRoute("/docs-context")({
  component: DocsContextScreen,
});

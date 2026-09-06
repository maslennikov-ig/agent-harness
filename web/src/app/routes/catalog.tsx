import { createFileRoute } from "@tanstack/react-router";
import { CatalogScreen } from "@/features/catalog/catalog-screen";

export const Route = createFileRoute("/catalog")({ component: CatalogScreen });

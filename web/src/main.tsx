import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { router } from "@/app/router";
import { queryClient } from "@/shared/api/query-client";
import { AppearanceProvider } from "@/shared/theme/appearance-provider";
import "@/shared/styles/globals.css";

const container = document.getElementById("root");

if (!(container instanceof HTMLElement)) {
  throw new Error("Missing #root container");
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppearanceProvider>
        <RouterProvider router={router} />
      </AppearanceProvider>
    </QueryClientProvider>
  </StrictMode>,
);

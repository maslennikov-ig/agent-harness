import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Coming back to the console should not show data from the last session.
      refetchOnWindowFocus: true,
      retry: false,
    },
    mutations: { retry: false },
  },
});

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { requestJson } from "@/shared/api/client";

const projectionQueryKey = (endpoint: string) =>
  ["projection", endpoint] as const;

function freshEndpoint(endpoint: string) {
  return `${endpoint}${endpoint.includes("?") ? "&" : "?"}fresh=1`;
}

/**
 * `refetchInterval` polls only while the query is mounted and the tab is
 * visible: React Query pauses the timer for background tabs unless
 * `refetchIntervalInBackground` is set, which is deliberately left off.
 */
export function useProjectionQuery<T>(
  endpoint: string,
  options: { refetchInterval?: number } = {},
) {
  const queryClient = useQueryClient();
  const freshRequest = useRef(false);
  const queryKey = projectionQueryKey(endpoint);
  const query = useQuery({
    queryKey,
    queryFn: () =>
      requestJson<T>(freshRequest.current ? freshEndpoint(endpoint) : endpoint),
    refetchInterval: options.refetchInterval,
  });

  const refresh = async () => {
    freshRequest.current = true;
    try {
      await queryClient.invalidateQueries({ queryKey });
    } finally {
      freshRequest.current = false;
    }
  };

  return { query, refresh };
}

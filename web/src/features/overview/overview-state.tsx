import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { overviewQuery } from "@/shared/api/queries";
import type { OverviewPayload } from "@/shared/api/types";
import { Card, CardContent } from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";

export function OverviewState({
  children,
}: {
  children: (data: OverviewPayload) => ReactNode;
}) {
  const query = useQuery(overviewQuery);
  if (query.isPending) {
    return (
      <div
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
        role="status"
        aria-label="Загрузка данных"
      >
        {["one", "two", "three", "four", "five", "six"].map((key) => (
          <Skeleton key={key} className="h-32 rounded-xl" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="py-6 text-sm text-destructive">
          Не удалось загрузить `/api/overview`: {query.error.message}
        </CardContent>
      </Card>
    );
  }
  return children(query.data);
}

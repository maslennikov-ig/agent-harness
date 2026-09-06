import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { queryKeys } from "@/shared/api/queries";
import { Button } from "@/shared/ui/button";

export function RefreshOverviewButton() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const refresh = async () => {
    setPending(true);
    try {
      await queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      await queryClient.refetchQueries({
        queryKey: queryKeys.overview,
        type: "active",
      });
      toast.success("Данные обновлены");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Не удалось обновить данные",
      );
    } finally {
      setPending(false);
    }
  };
  return (
    <Button variant="outline" onClick={refresh} disabled={pending}>
      <RefreshCw aria-hidden="true" className={pending ? "animate-spin" : ""} />
      {pending ? "Обновляю" : "Обновить"}
    </Button>
  );
}

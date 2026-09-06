import type { CoordinationDispatch } from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

export function ExecutorConfirmation({
  dispatch,
  onConfirm,
  onOpenChange,
  open,
  sending,
}: {
  dispatch: CoordinationDispatch | null;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  sending: boolean;
}) {
  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Отправить сообщение исполнителю?</DialogTitle>
          <DialogDescription>
            Это запустит оплачиваемый модельный вызов в существующей сессии.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid gap-2 rounded-lg border border-border-soft bg-surface-low p-3 font-mono text-xs">
          <div className="grid grid-cols-[5.5rem_1fr] gap-2">
            <dt className="text-muted-foreground">provider</dt>
            <dd>{dispatch?.provider ?? "—"}</dd>
          </div>
          <div className="grid grid-cols-[5.5rem_1fr] gap-2">
            <dt className="text-muted-foreground">dispatch</dt>
            <dd className="break-all">{dispatch?.dispatch_id ?? "—"}</dd>
          </div>
          <div className="grid grid-cols-[5.5rem_1fr] gap-2">
            <dt className="text-muted-foreground">действие</dt>
            <dd>один новый turn в этой runtime-сессии</dd>
          </div>
        </dl>
        <DialogFooter>
          <DialogClose asChild>
            <Button disabled={sending} type="button" variant="outline">
              Отмена
            </Button>
          </DialogClose>
          <Button
            disabled={!dispatch || sending}
            onClick={onConfirm}
            type="button"
          >
            Подтвердить платный вызов
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

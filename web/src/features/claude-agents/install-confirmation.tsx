import type { ClaudeAgentCandidate } from "@/features/claude-agents/types";
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

export function AgentInstallConfirmation({
  candidate,
  onConfirm,
  onOpenChange,
  sending,
}: {
  candidate: ClaudeAgentCandidate | null;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  sending: boolean;
}) {
  return (
    <Dialog onOpenChange={onOpenChange} open={Boolean(candidate)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Добавить Claude agent?</DialogTitle>
          <DialogDescription>
            Это запишет один локальный Markdown agent в выбранный scope. Команды
            dry-run и install cmd не выполняются.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid gap-2 rounded-lg border border-border-soft bg-surface-low p-3 font-mono text-xs">
          <div className="grid grid-cols-[5.5rem_1fr] gap-2">
            <dt className="text-muted-foreground">agent</dt>
            <dd>{candidate?.name || "—"}</dd>
          </div>
          <div className="grid grid-cols-[5.5rem_1fr] gap-2">
            <dt className="text-muted-foreground">scope</dt>
            <dd>project</dd>
          </div>
          <div className="grid grid-cols-[5.5rem_1fr] gap-2">
            <dt className="text-muted-foreground">target</dt>
            <dd className="break-all">
              {candidate?.project_install_target || "—"}
            </dd>
          </div>
        </dl>
        <DialogFooter>
          <DialogClose asChild>
            <Button disabled={sending} type="button" variant="outline">
              Отмена
            </Button>
          </DialogClose>
          <Button
            disabled={!candidate || sending}
            onClick={onConfirm}
            type="button"
          >
            {sending ? "Добавляю…" : "Установить в project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

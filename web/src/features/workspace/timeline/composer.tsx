import { SendHorizontal } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";
import { ExecutorConfirmation } from "@/features/workspace/timeline/executor-confirmation";
import { postJson } from "@/shared/api/client";
import type { CoordinationDispatch } from "@/shared/api/types";
import { Button } from "@/shared/ui/button";
import { Select } from "@/shared/ui/select";
import { Textarea } from "@/shared/ui/textarea";

type ComposerAction = {
  body: string;
  eventKind: string;
  key: string;
  signature: string;
  target: string;
};

const inputStates = new Set(["needs_input", "awaiting_review", "blocked"]);

export function TimelineComposer({
  enabled,
  dispatches,
  epicId,
  onDispatchChanged,
  onStored,
  projectId,
}: {
  dispatches: CoordinationDispatch[];
  enabled: boolean;
  epicId: string;
  onDispatchChanged: () => void;
  onStored: (event: CoordinationEvent) => void;
  projectId: string;
}) {
  const [body, setBody] = useState("");
  const [eventKind, setEventKind] = useState("message");
  const [sending, setSending] = useState(false);
  const [target, setTarget] = useState("journal");
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [pending, setPending] = useState<ComposerAction | null>(null);
  const actionRef = useRef<ComposerAction | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const availableDispatches = dispatches.filter(
    (dispatch) =>
      dispatch.role === "executor" &&
      Boolean(dispatch.runtime_session_id) &&
      inputStates.has(dispatch.state),
  );
  const selectedDispatch =
    availableDispatches.find((dispatch) => dispatch.dispatch_id === target) ??
    null;

  useEffect(() => {
    if (target === "journal" || selectedDispatch) return;
    setTarget("journal");
    actionRef.current = null;
  }, [selectedDispatch, target]);

  const resize = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 176)}px`;
  }, []);

  const actionFor = (text: string) => {
    const signature = `${target}\u0000${eventKind}\u0000${text}`;
    if (actionRef.current?.signature === signature) {
      return actionRef.current;
    }
    const action = {
      body: text,
      eventKind,
      key: `browser:${crypto.randomUUID()}`,
      signature,
      target,
    };
    actionRef.current = action;
    return action;
  };

  const send = async (action: ComposerAction) => {
    setSending(true);
    try {
      const executorAction = action.target !== "journal";
      const executor = dispatches.find(
        (dispatch) => dispatch.dispatch_id === action.target,
      );
      if (executorAction && !executor) {
        throw new Error("Выбранная сессия исполнителя больше недоступна");
      }
      const stored = await postJson<CoordinationEvent>(
        executorAction
          ? "/api/coordination/dispatches/message"
          : "/api/coordination/messages",
        executorAction
          ? {
              dispatch_id: executor?.dispatch_id,
              body_text: action.body,
              idempotency_key: action.key,
              confirm: true,
            }
          : {
              project_id: projectId,
              epic_id: epicId,
              body_text: action.body,
              event_kind: action.eventKind,
              idempotency_key: action.key,
            },
      );
      actionRef.current = null;
      setBody("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
      onStored(stored);
      if (executorAction) onDispatchChanged();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Сообщение не отправлено",
      );
    } finally {
      setSending(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = body.trim();
    if (!text || sending || !enabled) return;
    const action = actionFor(text);
    if (selectedDispatch) {
      setPending(action);
      setConfirmationOpen(true);
      return;
    }
    void send(action);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    )
      return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  };

  return (
    <form
      className="border-t border-border-soft bg-card/95 p-3 backdrop-blur sm:p-4"
      onSubmit={submit}
    >
      <ExecutorConfirmation
        dispatch={selectedDispatch}
        onConfirm={() => {
          setConfirmationOpen(false);
          if (pending) void send(pending);
        }}
        onOpenChange={setConfirmationOpen}
        open={confirmationOpen}
        sending={sending}
      />
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-2 sm:flex">
        <label className="sr-only" htmlFor="timeline-target">
          Адресат
        </label>
        <Select
          aria-label="Адресат"
          className="rounded-lg text-xs md:text-xs"
          containerClassName="w-full sm:max-w-44"
          id="timeline-target"
          onChange={(event) => {
            setTarget(event.target.value);
            actionRef.current = null;
          }}
          value={target}
        >
          <option value="journal">Журнал · бесплатно</option>
          {availableDispatches.map((dispatch) => (
            <option key={dispatch.dispatch_id} value={dispatch.dispatch_id}>
              {dispatch.provider} · {dispatch.dispatch_id.slice(0, 12)} · платно
            </option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="timeline-event-kind">
          Тип сообщения
        </label>
        <Select
          className="rounded-lg text-xs md:text-xs"
          id="timeline-event-kind"
          disabled={Boolean(selectedDispatch)}
          onChange={(event) => setEventKind(event.target.value)}
          value={eventKind}
        >
          <option value="message">Сообщение</option>
          <option value="question">Вопрос</option>
          <option value="decision">Решение</option>
          <option value="blocker">Блокер</option>
        </Select>
        <Textarea
          aria-label={
            selectedDispatch
              ? `Сообщение исполнителю ${selectedDispatch.provider}`
              : "Сообщение в общий поток эпика"
          }
          className="max-h-44 min-h-control min-w-0 resize-none rounded-xl py-2.5"
          disabled={!enabled}
          onChange={(event) => {
            setBody(event.target.value);
            resize();
          }}
          onKeyDown={onKeyDown}
          placeholder={
            enabled && selectedDispatch
              ? `Сообщение ${selectedDispatch.provider} · потребуется подтверждение`
              : enabled
                ? "Сообщение в журнал эпика"
                : "Запись выключена в настройках сервера"
          }
          ref={textareaRef}
          rows={1}
          value={body}
        />
        <Button
          aria-label="Отправить сообщение"
          className="size-10 shrink-0 rounded-xl p-0"
          disabled={!enabled || sending || !body.trim()}
          type="submit"
        >
          <SendHorizontal aria-hidden="true" />
        </Button>
      </div>
      <p className="mt-2 pl-1 text-xs text-muted-foreground">
        Enter — отправить · Shift+Enter — новая строка ·{" "}
        {selectedDispatch
          ? "исполнитель: платный вызов только после подтверждения"
          : "журнал бесплатный"}
      </p>
    </form>
  );
}

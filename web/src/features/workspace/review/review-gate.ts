import type { CoordinationReviewExecutor } from "@/shared/api/types";

export function reviewGateText(entry: CoordinationReviewExecutor) {
  if (!entry.is_current) {
    return "Прогон заменён более новым: Done решается по текущему прогону задачи.";
  }
  if (entry.done_allowed) return "Done открыт: принятый вердикт есть.";
  const last = entry.rounds.at(-1);
  if (!last) return "Done закрыт: вердикта судьи ещё нет.";
  if (last.decided_by === "user") {
    return "Done закрыт: вы отклонили результат после цикла ревью.";
  }
  if (last.outcome === "unreadable") {
    return `Done закрыт: судья ${last.judge_provider} ответил без читаемого вердикта в раунде ${last.round}.`;
  }
  return `Done закрыт: судья ${last.judge_provider} запросил правки в раунде ${last.round}. Нужен принятый вердикт или ваше явное решение.`;
}

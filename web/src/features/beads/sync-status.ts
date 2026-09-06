export interface SyncStatus {
  canonical_repo: string;
  enrolled: boolean;
  exclusion_reason: "" | "configured" | "no_github_origin";
  hooks_installed: boolean;
  inflight: boolean;
  inflight_age: number | null;
  inflight_started_at: string | null;
  inflight_stale: boolean;
  last_error: string;
  last_result: string;
  last_run: number;
  last_success: string | null;
  oldest_pending_age: number | null;
  pending_count: number;
  pin_mismatch: string;
  pin_valid: boolean | null;
  requested_repo: string;
  resolution_status: string;
  state_error: string;
  state_status: string;
}

export interface SyncStatusView {
  className: "text-destructive" | "text-muted-foreground" | "text-warning";
  role?: "alert";
  text: string;
}

const STALE_QUEUE_SECONDS = 15 * 60;

export function syncStatusQueryErrorView(): SyncStatusView {
  return {
    className: "text-destructive",
    role: "alert",
    text: "Не удалось получить статус синхронизации с GitHub.",
  };
}

/** Translate the backend contract into safe, stable operator copy. */
export function syncStatusView(status: SyncStatus): SyncStatusView {
  if (
    status.state_status === "error" ||
    status.state_error ||
    status.last_error
  ) {
    return {
      className: "text-destructive",
      role: "alert",
      text: "Синхронизация с GitHub: ошибка. Проверьте журнал.",
    };
  }
  if (status.state_status === "excluded") {
    return {
      className: "text-muted-foreground",
      text:
        status.exclusion_reason === "no_github_origin"
          ? "Синхронизация с GitHub: репозиторий намеренно исключён — не задан GitHub origin."
          : "Синхронизация с GitHub: репозиторий намеренно исключён.",
    };
  }
  if (
    !status.enrolled ||
    status.state_status === "legacy" ||
    status.state_status === "reenrollment_required" ||
    status.pin_valid === false ||
    status.pin_mismatch ||
    !status.hooks_installed
  ) {
    return {
      className: "text-warning",
      text: "Синхронизация с GitHub: требуется повторное подключение.",
    };
  }
  if (status.inflight) {
    if (status.inflight_stale) {
      return {
        className: "text-warning",
        text: "Синхронизация с GitHub задержалась и требует внимания.",
      };
    }
    return {
      className: "text-muted-foreground",
      text: "Синхронизация с GitHub: синхронизация выполняется.",
    };
  }
  if (status.pending_count > 0) {
    const stale =
      status.oldest_pending_age !== null &&
      status.oldest_pending_age > STALE_QUEUE_SECONDS;
    return {
      className: stale ? "text-warning" : "text-muted-foreground",
      text: stale
        ? `Синхронизация с GitHub: в очереди ${status.pending_count}, обработка задерживается.`
        : `Синхронизация с GitHub: в очереди ${status.pending_count}.`,
    };
  }
  return {
    className: "text-muted-foreground",
    text: "Синхронизация с GitHub: синхронизация работает.",
  };
}

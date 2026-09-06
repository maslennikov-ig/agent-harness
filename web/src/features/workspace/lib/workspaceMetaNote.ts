import type { CoordinationOverviewPayload } from "@/shared/api/types";

type MetaSource = Pick<
  CoordinationOverviewPayload,
  "enabled" | "flag" | "schema_version"
>;

// Legacy renderWorkspaceMeta named the schema and, when writes were off, the
// flag that turns them on. The read-only badge states the condition; without
// this note the operator is never told what to do about it.
export function workspaceMetaNote(overview?: MetaSource): string {
  if (!overview) return "";
  const schema = `Схема ${overview.schema_version}.`;
  return overview.enabled
    ? `${schema} Запуск runtime — только явным подтверждением; это платное действие.`
    : `${schema} Мутации выключены: запустите панель с ${overview.flag}=1.`;
}

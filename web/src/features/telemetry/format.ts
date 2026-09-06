export function formatTelemetryDuration(value: unknown) {
  if (value === null || value === undefined) return "unavailable";
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "unavailable";
  if (seconds < 60) {
    return `${Number.isInteger(seconds) ? seconds : seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

export function formatTelemetryCount(value: unknown) {
  if (value === null || value === undefined) return "unavailable";
  const count = Number(value);
  return Number.isFinite(count) && count >= 0 ? String(count) : "unavailable";
}

export function formatTelemetryBreakdown(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return "unavailable";
  }
  const entries = Object.entries(value);
  if (!entries.length) return "unavailable";
  return entries
    .map(([name, count]) => `${name}: ${formatTelemetryCount(count)}`)
    .join(" · ");
}

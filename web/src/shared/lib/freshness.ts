/**
 * Russian wording for the age of the data on screen. Kept separate from the
 * component so the wording is unit-testable without a DOM.
 */
export function formatFreshness(ageSeconds: number) {
  if (ageSeconds < 5) return "обновлено только что";
  if (ageSeconds < 60) return `обновлено ${ageSeconds} с назад`;
  const minutes = Math.floor(ageSeconds / 60);
  if (minutes < 60) return `обновлено ${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `обновлено ${hours} ч назад`;
  return `обновлено ${Math.floor(hours / 24)} дн назад`;
}

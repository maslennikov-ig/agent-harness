import type { Tail, TailGroup } from "@/features/tails/types";

export type TailSort = "oldest" | "count" | "project";

export function tailKey(tail: Tail) {
  return `${tail.repo_path}::${tail.branch}::${tail.commit}`;
}

export function filterTails(
  tails: Tail[],
  query: string,
  kind: "all" | Tail["kind"],
  minimumAge: number,
) {
  const needle = query.toLowerCase();
  return tails.filter((tail) => {
    const searchable =
      `${tail.project} ${tail.repo_path} ${tail.branch} ${tail.commit} ${tail.subject} ${tail.base}`.toLowerCase();
    return (
      (kind === "all" || tail.kind === kind) &&
      Number(tail.age_days) >= minimumAge &&
      (!needle || searchable.includes(needle))
    );
  });
}

export function sortTails(tails: Tail[], sort: TailSort) {
  return [...tails].sort((left, right) =>
    sort === "project"
      ? left.project.localeCompare(right.project) ||
        right.age_days - left.age_days
      : right.age_days - left.age_days ||
        left.project.localeCompare(right.project),
  );
}

export function groupTails(tails: Tail[], sort: TailSort): TailGroup[] {
  const grouped = new Map<string, TailGroup>();
  for (const tail of tails) {
    const current = grouped.get(tail.repo_path) ?? {
      base: tail.base,
      count: 0,
      key: tail.repo_path,
      local: 0,
      oldest: 0,
      project: tail.project,
      remote: 0,
      repo_path: tail.repo_path,
      tails: [],
    };
    current.tails.push(tail);
    current.count += 1;
    current.local += tail.kind === "local" ? 1 : 0;
    current.remote += tail.kind === "remote" ? 1 : 0;
    current.oldest = Math.max(current.oldest, Number(tail.age_days));
    grouped.set(tail.repo_path, current);
  }
  const result = [...grouped.values()];
  for (const group of result) {
    group.tails.sort(
      (left, right) =>
        right.age_days - left.age_days ||
        left.branch.localeCompare(right.branch),
    );
  }
  if (sort === "count") {
    result.sort(
      (left, right) =>
        right.count - left.count ||
        right.oldest - left.oldest ||
        left.project.localeCompare(right.project),
    );
  } else if (sort === "project") {
    result.sort((left, right) => left.project.localeCompare(right.project));
  } else {
    result.sort(
      (left, right) =>
        right.oldest - left.oldest ||
        right.count - left.count ||
        left.project.localeCompare(right.project),
    );
  }
  return result;
}

function shellQuote(value: string) {
  return `'${value.replaceAll("'", `'"'"'`)}'`;
}

export function diagnosticCommands(tail: Tail) {
  const repo = shellQuote(tail.repo_path);
  return [
    `git -C ${repo} log --oneline ${tail.base}..${tail.branch}`,
    `git -C ${repo} show --stat ${tail.commit}`,
    `git -C ${repo} branch --contains ${tail.commit}`,
  ];
}

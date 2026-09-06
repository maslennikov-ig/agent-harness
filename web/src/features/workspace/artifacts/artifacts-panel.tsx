import { artifactRows } from "@/features/workspace/artifacts/artifact-rows";
import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";

export function ArtifactsPanel({ events }: { events: CoordinationEvent[] }) {
  const artifacts = artifactRows(events);

  if (!artifacts.length) {
    return (
      <div className="rounded-xl border border-dashed border-border-soft p-6 text-sm text-muted-foreground">
        Ссылок на артефакты пока нет. Здесь появятся путь и digest файлов из
        рабочего дерева; сами документы остаются в Git.
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border-soft rounded-xl border border-border-soft bg-surface-low">
      {artifacts.map(({ artifact, key }) => (
        <li className="p-4" key={key}>
          <code className="block break-all text-sm">{artifact.path}</code>
          <div className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-muted-foreground">
            <span>{artifact.digest.slice(0, 12)}</span>
            <span>{artifact.media_type}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

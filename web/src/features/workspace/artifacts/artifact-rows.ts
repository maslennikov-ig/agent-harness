import type { CoordinationEvent } from "@/features/workspace/lib/formatTimelineMessages";

type ArtifactReference = CoordinationEvent["artifact_refs"][number];

export type ArtifactRow = { artifact: ArtifactReference; key: string };

// The store keeps artifact_refs without a UNIQUE constraint and reads them
// ORDER BY id, so one event can carry the same reference twice and two events
// can carry the same reference each. Every reference gets a row in source
// order; the occurrence counter is what keeps those rows distinct.
export function artifactRows(events: CoordinationEvent[]): ArtifactRow[] {
  return events.flatMap((event) => {
    const occurrences = new Map<string, number>();
    return event.artifact_refs.map((artifact) => {
      const identity = `${artifact.path}:${artifact.digest}:${artifact.media_type}`;
      const occurrence = (occurrences.get(identity) ?? 0) + 1;
      occurrences.set(identity, occurrence);
      return {
        artifact,
        key: `${event.event_id}:${identity}:${occurrence}`,
      };
    });
  });
}

import { ScreenFrame } from "@/app/components/screen-frame";
import { screenById } from "@/app/navigation";
import { OverviewState } from "@/features/overview/overview-state";
import { RefreshOverviewButton } from "@/features/overview/refresh-overview-button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

export function NotesScreen() {
  const screen = screenById("notes");
  return (
    <ScreenFrame
      screen={screen}
      actions={<RefreshOverviewButton />}
      marker={{ kind: "native", id: screen.id }}
    >
      <OverviewState>
        {(data) => (
          <Card className="border-border/70 bg-card/80">
            <CardHeader>
              <CardTitle className="break-all font-mono text-sm text-muted-foreground">
                {data.notes.path}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-code-bg p-4 font-mono text-sm leading-6 text-code-fg">
                {data.notes.preview || "No notes found."}
              </pre>
            </CardContent>
          </Card>
        )}
      </OverviewState>
    </ScreenFrame>
  );
}

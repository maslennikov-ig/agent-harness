import { Link, Outlet } from "@tanstack/react-router";
import { Check, Menu, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { navigationGroups, screens } from "@/app/navigation";
import { useAppearance } from "@/shared/theme/appearance-provider";
import { Button } from "@/shared/ui/button";
import { Separator } from "@/shared/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/shared/ui/sheet";
import { Toaster } from "@/shared/ui/sonner";

function AppearanceControls() {
  const { runtime, setRuntime, theme, setTheme } = useAppearance();
  return (
    <div className="space-y-2">
      <div>
        <fieldset className="grid grid-cols-2 gap-1 rounded-lg border border-sidebar-border bg-background/35 p-1">
          <legend className="sr-only">Runtime</legend>
          {(["codex", "claude"] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={runtime === item}
              className="flex min-h-control items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium capitalize text-muted-foreground transition-colors hover:text-foreground aria-pressed:bg-primary aria-pressed:text-primary-foreground"
              onClick={() => setRuntime(item)}
            >
              {runtime === item ? (
                <Check className="size-3.5" aria-hidden="true" />
              ) : null}
              {item}
            </button>
          ))}
        </fieldset>
      </div>
      <div>
        <fieldset className="grid grid-cols-2 gap-1 rounded-lg border border-sidebar-border bg-background/35 p-1">
          <legend className="sr-only">Тема</legend>
          <button
            type="button"
            aria-pressed={theme === "light"}
            className="flex min-h-control items-center justify-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:text-foreground aria-pressed:bg-sidebar-accent aria-pressed:text-foreground"
            onClick={() => setTheme("light")}
          >
            <Sun className="size-3.5" aria-hidden="true" /> Светлая
          </button>
          <button
            type="button"
            aria-pressed={theme === "dark"}
            className="flex min-h-control items-center justify-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:text-foreground aria-pressed:bg-sidebar-accent aria-pressed:text-foreground"
            onClick={() => setTheme("dark")}
          >
            <Moon className="size-3.5" aria-hidden="true" /> Тёмная
          </button>
        </fieldset>
      </div>
    </div>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav
      aria-label="Основная навигация"
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-3"
    >
      {navigationGroups.map((group) => (
        <div key={group}>
          <p className="mb-0.5 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground/75">
            {group}
          </p>
          <div className="space-y-0.5">
            {screens
              .filter((screen) => screen.group === group)
              .map((screen) => {
                const Icon = screen.icon;
                return (
                  <Link
                    key={screen.id}
                    to={screen.path}
                    activeOptions={{ exact: screen.id !== "workspace" }}
                    onClick={onNavigate}
                    className="flex min-h-control items-center gap-3 rounded-lg px-3 text-sm font-medium text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground [&.active]:bg-primary [&.active]:text-primary-foreground"
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0" />
                    <span>{screen.label}</span>
                  </Link>
                );
              })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex min-h-14 items-center gap-3 px-5">
        <img
          src="/logo.svg"
          alt=""
          width="40"
          height="40"
          className="size-10"
        />
        <div className="min-w-0">
          <p className="truncate font-semibold tracking-tight">Local Nodes</p>
          <p className="truncate text-xs text-muted-foreground">
            Orchestration Console
          </p>
        </div>
      </div>
      <Separator className="bg-sidebar-border" />
      <Navigation onNavigate={onNavigate} />
      <Separator className="bg-sidebar-border" />
      <div className="px-3 pb-3 pt-2">
        <AppearanceControls />
      </div>
    </div>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="min-h-screen bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-sidebar-border lg:block">
        <SidebarContent />
      </aside>
      <div className="sticky top-0 z-20 flex min-h-16 items-center justify-between border-b border-border/70 bg-topbar-bg px-4 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2.5">
          <img
            src="/logo.svg"
            alt=""
            width="32"
            height="32"
            className="size-8"
          />
          <span className="font-semibold">Local Nodes</span>
        </div>
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button
              variant="outline"
              size="icon"
              aria-label="Открыть навигацию"
            >
              <Menu aria-hidden="true" />
            </Button>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-72 border-sidebar-border bg-sidebar p-0"
          >
            <SheetTitle className="sr-only">Навигация</SheetTitle>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>
      <main className="min-h-screen lg:pl-64">
        <Outlet />
      </main>
      <Toaster closeButton richColors />
    </div>
  );
}

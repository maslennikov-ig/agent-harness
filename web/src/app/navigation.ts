import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  Bot,
  Boxes,
  ChartNoAxesCombined,
  CircleHelp,
  FileClock,
  Gauge,
  Library,
  ListChecks,
  MessageSquareText,
  NotebookText,
  ServerCog,
  Settings2,
} from "lucide-react";

export type ScreenId =
  | "workspace"
  | "prompts"
  | "beads"
  | "telemetry"
  | "throughput"
  | "tails"
  | "runtime"
  | "environment"
  | "docs-context"
  | "catalog"
  | "claude-agents"
  | "help"
  | "notes";

export interface ScreenDescriptor {
  id: ScreenId;
  path: string;
  label: string;
  title: string;
  description: string;
  group: "Работа" | "Наблюдение" | "Справка";
  icon: LucideIcon;
}

export const screens = [
  {
    id: "workspace",
    path: "/workspace",
    label: "Workspace",
    title: "Epic workspace",
    description: "События, задачи, артефакты и запуски одного epic.",
    group: "Работа",
    icon: MessageSquareText,
  },
  {
    id: "prompts",
    path: "/prompts",
    label: "Промпты",
    title: "Рабочие промпты",
    description: "Карточки запуска для Codex и Claude.",
    group: "Работа",
    icon: Library,
  },
  {
    id: "beads",
    path: "/beads",
    label: "Задачи",
    title: "Задачи",
    description: "Beads-задачи по локальным репозиториям.",
    group: "Работа",
    icon: ListChecks,
  },
  {
    id: "telemetry",
    path: "/telemetry",
    label: "Телеметрия",
    title: "Телеметрия",
    description: "Наблюдаемые затраты и длительности этапов.",
    group: "Наблюдение",
    icon: Activity,
  },
  {
    id: "throughput",
    path: "/throughput",
    label: "Throughput",
    title: "Throughput",
    description: "Фактическая пропускная способность оркестрации.",
    group: "Наблюдение",
    icon: ChartNoAxesCombined,
  },
  {
    id: "tails",
    path: "/tails",
    label: "Хвосты",
    title: "Хвосты",
    description: "Старые ветки, worktree и сигналы для очистки.",
    group: "Наблюдение",
    icon: FileClock,
  },
  {
    id: "runtime",
    path: "/runtime",
    label: "Runtime",
    title: "Runtime",
    description: "Состояние локальных адаптеров исполнителей.",
    group: "Наблюдение",
    icon: ServerCog,
  },
  {
    id: "environment",
    path: "/environment",
    label: "Статус",
    title: "Статус окружения",
    description: "Пути, инструменты и локальные зависимости консоли.",
    group: "Наблюдение",
    icon: Gauge,
  },
  {
    id: "docs-context",
    path: "/docs-context",
    label: "Документация",
    title: "L1/L2 документация",
    description: "Локальное покрытие документации зависимостей.",
    group: "Справка",
    icon: BookOpen,
  },
  {
    id: "catalog",
    path: "/catalog",
    label: "Каталог",
    title: "Каталог и маршрутизация",
    description: "Доступные skills, agents и runtime-ассеты.",
    group: "Справка",
    icon: Boxes,
  },
  {
    id: "claude-agents",
    path: "/claude-agents",
    label: "Claude Agents",
    title: "Claude Agents",
    description: "Локальная библиотека Claude subagents.",
    group: "Справка",
    icon: Bot,
  },
  {
    id: "help",
    path: "/help",
    label: "Помощь",
    title: "Как пользоваться панелью",
    description: "Порядок работы: от проекта до закрытой задачи.",
    group: "Справка",
    icon: CircleHelp,
  },
  {
    id: "notes",
    path: "/notes",
    label: "Память",
    title: "Локальная память консоли",
    description: "Операторский контекст и заметки восстановления.",
    group: "Справка",
    icon: NotebookText,
  },
] as const satisfies readonly ScreenDescriptor[];

export const screenById = (id: ScreenId) => {
  const screen = screens.find((candidate) => candidate.id === id);
  if (!screen) throw new Error(`Unknown screen: ${id}`);
  return screen;
};

export const navigationGroups = ["Работа", "Наблюдение", "Справка"] as const;

export const settingsIcon = Settings2;

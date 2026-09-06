import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type ThemeMode = "light" | "dark";
export type RuntimeMode = "codex" | "claude";

const THEME_STORE_KEY = "orch-prompts.theme-mode";
const RUNTIME_STORE_KEY = "orch-prompts.active-runtime";

interface AppearanceValue {
  theme: ThemeMode;
  runtime: RuntimeMode;
  setTheme: (theme: ThemeMode) => void;
  setRuntime: (runtime: RuntimeMode) => void;
}

const AppearanceContext = createContext<AppearanceValue | null>(null);

function storedValue<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
) {
  try {
    const value = localStorage.getItem(key);
    return allowed.includes(value as T) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(() =>
    storedValue(THEME_STORE_KEY, ["light", "dark"], "dark"),
  );
  const [runtime, setRuntime] = useState<RuntimeMode>(() =>
    storedValue(RUNTIME_STORE_KEY, ["codex", "claude"], "codex"),
  );

  useEffect(() => {
    document.body.dataset.theme = theme;
    document.body.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(THEME_STORE_KEY, theme);
    } catch {
      // Storage is optional; the selected theme remains active for this session.
    }
  }, [theme]);

  useEffect(() => {
    document.body.dataset.runtime = runtime;
    try {
      localStorage.setItem(RUNTIME_STORE_KEY, runtime);
    } catch {
      // Storage is optional; the selected runtime remains active for this session.
    }
  }, [runtime]);

  const value = useMemo(
    () => ({ theme, runtime, setTheme, setRuntime }),
    [runtime, theme],
  );

  return (
    <AppearanceContext.Provider value={value}>
      {children}
    </AppearanceContext.Provider>
  );
}

export function useAppearance() {
  const context = useContext(AppearanceContext);
  if (!context)
    throw new Error("useAppearance must be used inside AppearanceProvider");
  return context;
}

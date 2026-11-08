/**
 * ThemeProvider.tsx
 * 
 * Manages themes the user can pick from in their settings.
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@clerk/nextjs";

export type Theme =
  | "light"
  | "dark"
  | "navy"
  | "pink"
  | "lavender"
  | "forest"
  | "confetti"
  | "red-void";

export type ThemeSelection = Theme | "systematic";

export type TextColor = "off" | "white" | "off-white" | "black";

export type Preferences = {
  theme: ThemeSelection;
  dayTheme: Theme;
  nightTheme: Theme;
  dayStart: string;
  nightStart: string;
  textColor: TextColor;
};

type ThemeContextType = {
  preferences: Preferences;
  ready: boolean;
  saving: boolean;
  error: string;
  updatePreferences: (changes: Partial<Preferences>) => Promise<void>;
};

const API =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const THEMES: { id: Theme; name: string }[] = [
  { id: "light", name: "Light Mode" },
  { id: "dark", name: "Dark Mode" },
  { id: "navy", name: "Navy Blue Mode" },
  { id: "pink", name: "Pink Mode" },
  { id: "lavender", name: "Lavender Mode" },
  { id: "forest", name: "Forest Green Mode" },
  { id: "confetti", name: "Confetti" },
  { id: "red-void", name: "Red Void" },
];

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "dark",
  dayTheme: "light",
  nightTheme: "dark",
  dayStart: "07:00",
  nightStart: "19:00",
  textColor: "off",
};

const ThemeContext = createContext<ThemeContextType | null>(null);

function isTheme(value: unknown): value is Theme {
  return THEMES.some((item) => item.id === value);
}

function isThemeSelection(value: unknown): value is ThemeSelection {
  return value === "systematic" || isTheme(value);
}

/**
 * Used for Adjustments 
 * User can choose whether they want all text colors to be:
 *        - All Black
 *        - All White
 *        - Off Colored White
 *        - Follow The Theme Selected
 */
function isTextColor(value: unknown): value is TextColor {
  return (
    value === "off" ||
    value === "white" ||
    value === "off-white" ||
    value === "black"
  );
}

function validTime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^([01]\d|2[0-3]):[0-5]\d$/.test(value)
  );
}

function getLocalMinutes(): number {
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes();
}

function timeToMinutes(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

/**
 * Manages Scheduled Themes
 * 
 * @param preferences User can customize themes to be their daytime or nighttime theme.
 * @returns 
 */
function getScheduledTheme(preferences: Preferences): Theme {
  const now = getLocalMinutes();
  const dayStart = timeToMinutes(preferences.dayStart);
  const nightStart = timeToMinutes(preferences.nightStart);

  let isDaytime: boolean;

  // daytime 07:00 to nighttime 19:00
  if (dayStart < nightStart) {
    isDaytime = now >= dayStart && now < nightStart;
  } else if (dayStart > nightStart) {
    // Also supports schedules that cross midnight.
    isDaytime = now >= dayStart || now < nightStart;
  } else {
    // If both times are identical, use the daytime theme.
    isDaytime = true;
  }

  return isDaytime
    ? preferences.dayTheme
    : preferences.nightTheme;
}

function applyPreferences(preferences: Preferences) {
  const actualTheme =
    preferences.theme === "systematic"
      ? getScheduledTheme(preferences)
      : preferences.theme;

  const root = document.documentElement;

  root.dataset.theme = actualTheme;
  root.dataset.textColor = preferences.textColor;
}

function normalizePreferences(data: Record<string, unknown>): Preferences {
  return {
    theme: isThemeSelection(data.theme)
      ? data.theme
      : DEFAULT_PREFERENCES.theme,

    dayTheme: isTheme(data.day_theme)
      ? data.day_theme
      : DEFAULT_PREFERENCES.dayTheme,

    nightTheme: isTheme(data.night_theme)
      ? data.night_theme
      : DEFAULT_PREFERENCES.nightTheme,

    dayStart: validTime(data.day_start)
      ? data.day_start
      : DEFAULT_PREFERENCES.dayStart,

    nightStart: validTime(data.night_start)
      ? data.night_start
      : DEFAULT_PREFERENCES.nightStart,

    textColor: isTextColor(data.text_color)
      ? data.text_color
      : DEFAULT_PREFERENCES.textColor,
  };
}

function toApiPreferences(preferences: Preferences) {
  return {
    theme: preferences.theme,
    day_theme: preferences.dayTheme,
    night_theme: preferences.nightTheme,
    day_start: preferences.dayStart,
    night_start: preferences.nightStart,
    text_color: preferences.textColor,
  };
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [preferences, setPreferences] =
    useState<Preferences>(DEFAULT_PREFERENCES);

  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Load the saved settings after Clerk confirms authentication.
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function loadPreferences() {
      try {
        const token = await getToken();

        if (!token) {
          throw new Error("Your session expired. Please sign in again.");
        }

        const response = await fetch(`${API}/preferences`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error("Could not load your saved preferences.");
        }

        const data = await response.json();
        const loaded = normalizePreferences(data);

        if (!cancelled) {
          setPreferences(loaded);
          applyPreferences(loaded);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load your saved preferences.",
          );
          applyPreferences(DEFAULT_PREFERENCES);
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    }

    void loadPreferences();

    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn]);

  // Keep the selected systematic theme updated as local time changes
  useEffect(() => {
    if (!ready) return;

    const updateScheduledTheme = () => {
      applyPreferences(preferences);
    };

    updateScheduledTheme();

    const interval = window.setInterval(
      updateScheduledTheme,
      30_000,
    );

    document.addEventListener(
      "visibilitychange",
      updateScheduledTheme,
    );

    return () => {
      window.clearInterval(interval);
      document.removeEventListener(
        "visibilitychange",
        updateScheduledTheme,
      );
    };
  }, [preferences, ready]);

  const updatePreferences = useCallback(
    async (changes: Partial<Preferences>) => {
      const previous = preferences;
      const updated = { ...previous, ...changes };

      setPreferences(updated);
      applyPreferences(updated);
      setSaving(true);
      setError("");

      try {
        const token = await getToken();

        if (!token) {
          throw new Error("Your session expired. Please sign in again.");
        }

        const response = await fetch(`${API}/preferences`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(toApiPreferences(updated)),
          cache: "no-store",
        });

        if (!response.ok) {
          const data = await response.json().catch(() => ({}));

          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "Could not save your preferences.",
          );
        }
      } catch (err) {
        setPreferences(previous);
        applyPreferences(previous);

        setError(
          err instanceof Error
            ? err.message
            : "Could not save your preferences.",
        );
      } finally {
        setSaving(false);
      }
    },
    [getToken, preferences],
  );

  const value = useMemo(
    () => ({
      preferences,
      ready,
      saving,
      error,
      updatePreferences,
    }),
    [preferences, ready, saving, error, updatePreferences],
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemePreferences() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error(
      "useThemePreferences must be used inside ThemeProvider.",
    );
  }

  return context;
}

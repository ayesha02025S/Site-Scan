/**
 * AppearanceSettings.tsx
 * 
 * Displays The Appearance Tab
 */
"use client";

import { useThemePreferences, THEMES } from "./ThemeProvider";

const themeDescriptions: Record<string, string> = {
  light: "A bright appearance with soft neutral colors.",
  dark: "A dark charcoal appearance with muted accents.",
  navy: "A deep blue appearance with cool blue accents.",
  pink: "A soft pink appearance with warm rose accents.",
  lavender: "A gentle lavender appearance with purple accents.",
  forest: "A deep green appearance.",
  confetti: "A cream background decorated with colorful dots.",
  "red-void": "A void-like appearance with bold red accents.",
};

export default function AppearanceSettings() {
  const {
    preferences,
    ready,
    saving,
    error,
    updatePreferences,
  } = useThemePreferences();

  if (!ready) {
    return <p className="settings-loading">Loading appearance settings...</p>;
  }

  const systematic = preferences.theme === "systematic";

  return (
    <section className="settings-page">
      <div className="settings-title">
        <h2>Appearance</h2>
        <p>Customize the appearance of your workspace.</p>
      </div>

      <div className="settings-group">
        <label>Choose a Theme</label>

        <p className="settings-description">
          Select the appearance you want to use for your workspace.
        </p>

        <div className="theme-options">
          {THEMES.map((theme) => (
            <button
              key={theme.id}
              type="button"
              className={`theme-option ${
                preferences.theme === theme.id ? "selected" : ""
              }`}
              onClick={() =>
                void updatePreferences({
                  theme: theme.id,
                })
              }
              disabled={saving}
              aria-pressed={preferences.theme === theme.id}
            >
              <span
                className={`theme-color-preview ${theme.id}`}
                aria-hidden="true"
              />

              <span className="theme-option-text">
                <strong>{theme.name}</strong>
                <small>{themeDescriptions[theme.id]}</small>
              </span>

              {preferences.theme === theme.id && (
                <span className="theme-option-check" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          ))}

          <button
            type="button"
            className={`theme-option ${
              systematic ? "selected" : ""
            }`}
            onClick={() =>
              void updatePreferences({
                theme: "systematic",
              })
            }
            disabled={saving}
            aria-pressed={systematic}
          >
            <span
              className="theme-color-preview systematic"
              aria-hidden="true"
            />

            <span className="theme-option-text">
              <strong>Systematic Theme</strong>
              <small>
                Automatically switch between two selected themes from daytime to nighttime.
              </small>
            </span>

            {systematic && (
              <span className="theme-option-check" aria-hidden="true">
                ✓
              </span>
            )}
          </button>
        </div>
      </div>

      <div
        className={`systematic-settings ${
          systematic ? "enabled" : "disabled"
        }`}
        aria-disabled={!systematic}
      >
        <div className="settings-group">
          <h3>Systematic Theme</h3>

          <p className="settings-description">
            Automatically change your workspace theme from daytime
            to nighttime according to your local device time.
          </p>
        </div>

        <div className="systematic-row">
          <div className="settings-group">
            <label htmlFor="day-theme">Daytime theme</label>

            <select
              id="day-theme"
              value={preferences.dayTheme}
              disabled={!systematic || saving}
              onChange={(event) =>
                void updatePreferences({
                  dayTheme: event.target.value as typeof preferences.dayTheme,
                })
              }
            >
              {THEMES.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {theme.name}
                </option>
              ))}
            </select>
          </div>

          <div className="settings-group">
            <label htmlFor="night-theme">Nighttime theme</label>

            <select
              id="night-theme"
              value={preferences.nightTheme}
              disabled={!systematic || saving}
              onChange={(event) =>
                void updatePreferences({
                  nightTheme: event.target.value as typeof preferences.nightTheme,
                })
              }
            >
              {THEMES.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {theme.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="systematic-row">
          <div className="settings-group">
            <label htmlFor="day-start">Daytime starts</label>

            <input
              id="day-start"
              type="time"
              value={preferences.dayStart}
              disabled={!systematic || saving}
              onChange={(event) =>
                void updatePreferences({
                  dayStart: event.target.value,
                })
              }
            />
          </div>

          <div className="settings-group">
            <label htmlFor="night-start">Nighttime starts</label>

            <input
              id="night-start"
              type="time"
              value={preferences.nightStart}
              disabled={!systematic || saving}
              onChange={(event) =>
                void updatePreferences({
                  nightStart: event.target.value,
                })
              }
            />
          </div>
        </div>

        <p className="settings-description">
          Default schedule: daytime begins at 7:00 AM and nighttime
          begins at 7:00 PM. The selected themes switch at those
          times. You can customize both times.
        </p>

        {!systematic && (
          <p className="settings-disabled-note">
            Select Systematic Theme above to enable these settings.
          </p>
        )}
      </div>

      {saving && (
        <p className="settings-status" role="status">
          Saving preferences...
        </p>
      )}

      {error && (
        <p className="settings-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

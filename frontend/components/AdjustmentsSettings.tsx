/**
 * AsjustmentsSettings.tsx
 * 
 * Displays The Adjustment Tab
 */
"use client";

import { useThemePreferences } from "./ThemeProvider";

/**
 * User can choose whether they want all text colors to be:
 *        - All Black
 *        - All White
 *        - Off Colored White
 *        - Follow The Theme Selected: DEFAULT
 */
const textOptions = [
  {
    id: "off",
    name: "No Adjustment",
    description: "Use the selected theme's normal text colors.",
  },
  {
    id: "white",
    name: "White",
    description: "Make all text white.",
  },
  {
    id: "off-white",
    name: "Off-white",
    description: "Use a soft cream-white text color.",
  },
  {
    id: "black",
    name: "Black",
    description: "Make all text black.",
  },
] as const;

export default function AdjustmentsSettings() {
  const {
    preferences,
    ready,
    saving,
    error,
    updatePreferences,
  } = useThemePreferences();

  if (!ready) {
    return <p className="settings-loading">Loading adjustments...</p>;
  }

  return (
    <section className="settings-page">
      <div className="settings-title">
        <h2>Adjustments</h2>
        <p>Customize how information is displayed.</p>
      </div>

      <div className="settings-group">
        <label htmlFor="text-color">Adjust Text Color</label>
        <p className="settings-description">
          Choose a text color for your workspace.
        </p>

        <div className="text-color-options">
          {textOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`text-color-option ${
                preferences.textColor === option.id ? "selected" : ""
              }`}
              onClick={() =>
                void updatePreferences({
                  textColor: option.id,
                })
              }
              disabled={saving}
              aria-pressed={preferences.textColor === option.id}
            >
              <span className={`text-color-preview ${option.id}`} />
              <span>
                <strong>{option.name}</strong>
                <small>{option.description}</small>
              </span>
              {preferences.textColor === option.id && (
                <span className="text-color-check" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {saving && (
        <p className="settings-status" role="status">
          Saving adjustments...
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

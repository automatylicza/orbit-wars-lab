/**
 * Global theme preference + resolution.
 *
 * Preference (stored in localStorage["ow-theme"]):
 *   "system" | "light" | "dark"  (default "system" when absent)
 *
 * Resolved theme (written to <html data-theme>):
 *   "light" | "dark"  (always concrete; "system" resolves via prefers-color-scheme)
 */

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "ow-theme";

export function getPreference(): ThemePreference {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

export function setPreference(pref: ThemePreference): void {
  if (pref === "system") {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, pref);
  }
  applyTheme();
}

export function getResolvedTheme(): ResolvedTheme {
  const pref = getPreference();
  if (pref === "light" || pref === "dark") return pref;
  // system
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }
  return "dark";
}

export function applyTheme(): void {
  const resolved = getResolvedTheme();
  document.documentElement.setAttribute("data-theme", resolved);
  document.dispatchEvent(new CustomEvent("ow-theme-changed", { detail: { resolved } }));
}

let initialized = false;

export function init(): void {
  if (initialized) return;
  initialized = true;

  applyTheme();

  // React to OS-level theme changes when preference is "system".
  if (typeof window !== "undefined" && window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const handler = () => {
      if (getPreference() === "system") applyTheme();
    };
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else if ((mq as any).addListener) (mq as any).addListener(handler);
  }

  // React to other tabs flipping the preference.
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEY) applyTheme();
  });
}

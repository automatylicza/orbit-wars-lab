/**
 * Three-state theme toggle button. Cycles: system → light → dark → system.
 * Mounted in header-nav. Icon reflects current preference (not resolved).
 */
import * as theme from "../theme";

const ICONS: Record<theme.ThemePreference, string> = {
  // monitor
  system: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect x="1.5" y="2.5" width="13" height="9" rx="1"/>
    <path d="M5 14h6M8 11.5v2.5"/>
  </svg>`,
  // sun
  light: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true">
    <circle cx="8" cy="8" r="3"/>
    <path d="M8 1.5v1.7M8 12.8v1.7M14.5 8h-1.7M3.2 8H1.5M12.6 3.4l-1.2 1.2M4.6 11.4l-1.2 1.2M12.6 12.6l-1.2-1.2M4.6 4.6l-1.2-1.2"/>
  </svg>`,
  // moon
  dark: `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true">
    <path d="M13 9.5A5.5 5.5 0 1 1 6.5 3a4.5 4.5 0 0 0 6.5 6.5Z"/>
  </svg>`,
};

const ORDER: theme.ThemePreference[] = ["system", "light", "dark"];

function nextPref(current: theme.ThemePreference): theme.ThemePreference {
  const i = ORDER.indexOf(current);
  return ORDER[(i + 1) % ORDER.length];
}

function labelFor(pref: theme.ThemePreference): string {
  if (pref === "system") {
    const resolved = theme.getResolvedTheme();
    return `Theme: system (${resolved})`;
  }
  return `Theme: ${pref}`;
}

export function mountThemeToggle(parent: HTMLElement): void {
  const btn = document.createElement("button");
  btn.className = "theme-toggle";
  btn.type = "button";

  const render = () => {
    const pref = theme.getPreference();
    btn.innerHTML = ICONS[pref];
    btn.title = labelFor(pref);
    btn.setAttribute("aria-label", labelFor(pref));
  };

  render();
  btn.addEventListener("click", () => {
    const pref = theme.getPreference();
    theme.setPreference(nextPref(pref));
    render();
  });

  const ac = new AbortController();
  document.addEventListener("ow-theme-changed", render, { signal: ac.signal });

  parent.appendChild(btn);

  // Abort listener when the button is detached (e.g. route change wipes the header).
  const observer = new MutationObserver(() => {
    if (!btn.isConnected) {
      ac.abort();
      observer.disconnect();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

/**
 * HTML + URL sanitization helpers.
 *
 * The viewer builds most of its UI via `innerHTML = \`…${value}…\``, so every
 * value that originates from the API, filesystem (agent.yaml), or URL must
 * pass through one of these before interpolation. Otherwise an attacker-
 * controlled string (malicious Kaggle team name, tampered agent.yaml,
 * crafted `#/replays?sub=<img onerror=…>`) executes inline scripts.
 */

/** Escape text for safe interpolation into HTML text nodes OR double-quoted attributes. */
export function escapeHtml(value: unknown): string {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Convert a candidate string to a safe `href` attribute value, or `null` if it isn't one we trust.
 *
 * Accepts only `http://`, `https://`, and `mailto:` schemes. Rejects `javascript:`,
 * `data:`, relative paths, and anything else. Returns the escaped string ready
 * for `href="${…}"` interpolation, or `null` to signal "don't render a link".
 */
export function safeHref(value: unknown): string | null {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  // Reject common bypasses: leading whitespace, newlines, control chars.
  if (/[\x00-\x1f]/.test(raw)) return null;
  const lower = raw.toLowerCase();
  if (
    lower.startsWith("http://") ||
    lower.startsWith("https://") ||
    lower.startsWith("mailto:")
  ) {
    return escapeHtml(raw);
  }
  return null;
}

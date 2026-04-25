import { AgentInfo, Rating } from "../api";
import { escapeHtml, safeHref } from "../utils/escape";

export function renderAgentCard(
  agent: AgentInfo,
  ratings: Record<"2p" | "4p", Rating>,
): string {
  const href = safeHref(agent.source_url);
  const sourceLink = href
    ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(agent.source_url)}</a>`
    : agent.source_url
      ? `<code>${escapeHtml(agent.source_url)}</code>` // present but rejected scheme — show verbatim, no link
      : "—";
  return `
    <div class="agent-card">
      <h2>${escapeHtml(agent.name)}</h2>
      <dl>
        <dt>ID</dt><dd>${escapeHtml(agent.id)}</dd>
        <dt>Bucket</dt><dd>${escapeHtml(agent.bucket)}</dd>
        <dt>Path</dt><dd><code>${escapeHtml(agent.path)}</code></dd>
        <dt>Description</dt><dd>${agent.description ? escapeHtml(agent.description) : "—"}</dd>
        <dt>Author</dt><dd>${agent.author ? escapeHtml(agent.author) : "—"}</dd>
        <dt>Source URL</dt><dd>${sourceLink}</dd>
        <dt>Version</dt><dd>${agent.version ? escapeHtml(agent.version) : "—"}</dd>
        <dt>Tags</dt><dd>${agent.tags.map(escapeHtml).join(", ") || "—"}</dd>
        <dt>Disabled</dt><dd>${agent.disabled}</dd>
        <dt>Rating 2p</dt><dd>μ=${ratings["2p"].mu.toFixed(1)} σ=${ratings["2p"].sigma.toFixed(1)} games=${ratings["2p"].games_played}</dd>
        <dt>Rating 4p</dt><dd>μ=${ratings["4p"].mu.toFixed(1)} σ=${ratings["4p"].sigma.toFixed(1)} games=${ratings["4p"].games_played}</dd>
      </dl>
    </div>
  `;
}

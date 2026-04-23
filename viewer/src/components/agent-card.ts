import { AgentInfo, Rating } from "../api";

export function renderAgentCard(
  agent: AgentInfo,
  ratings: Record<"2p" | "4p", Rating>,
): string {
  return `
    <div class="agent-card">
      <h2>${agent.name}</h2>
      <dl>
        <dt>ID</dt><dd>${agent.id}</dd>
        <dt>Bucket</dt><dd>${agent.bucket}</dd>
        <dt>Path</dt><dd><code>${agent.path}</code></dd>
        <dt>Description</dt><dd>${agent.description ?? "—"}</dd>
        <dt>Author</dt><dd>${agent.author ?? "—"}</dd>
        <dt>Source URL</dt><dd>${agent.source_url ? `<a href="${agent.source_url}" target="_blank">${agent.source_url}</a>` : "—"}</dd>
        <dt>Version</dt><dd>${agent.version ?? "—"}</dd>
        <dt>Tags</dt><dd>${agent.tags.join(", ") || "—"}</dd>
        <dt>Disabled</dt><dd>${agent.disabled}</dd>
        <dt>Rating 2p</dt><dd>μ=${ratings["2p"].mu.toFixed(1)} σ=${ratings["2p"].sigma.toFixed(1)} games=${ratings["2p"].games_played}</dd>
        <dt>Rating 4p</dt><dd>μ=${ratings["4p"].mu.toFixed(1)} σ=${ratings["4p"].sigma.toFixed(1)} games=${ratings["4p"].games_played}</dd>
      </dl>
    </div>
  `;
}

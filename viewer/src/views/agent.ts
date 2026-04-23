import { api } from "../api";
import { navigate } from "../router";
import { renderAgentCard } from "../components/agent-card";

export async function renderAgent(
  root: HTMLElement,
  agentId: string,
): Promise<void> {
  const agent = await api.getAgent(agentId);
  const [rating2p, rating4p] = await Promise.all([
    api.getRatings("2p").then((r) => r.find((x) => x.agent_id === agentId)),
    api.getRatings("4p").then((r) => r.find((x) => x.agent_id === agentId)),
  ]);

  const fakeRating = (agent_id: string) => ({
    agent_id,
    mu: 600.0,
    sigma: 200.0,
    conservative: 0.0,
    games_played: 0,
    rank: 0,
  });

  const ratings = {
    "2p": rating2p ?? fakeRating(agentId),
    "4p": rating4p ?? fakeRating(agentId),
  };

  root.innerHTML = `
    <header class="replay-header">
      <button id="back">← Back</button>
      <h1>${agent.name}</h1>
      <div class="meta">${agent.id}</div>
      <button id="delete-agent" class="scrape-btn cancel" style="margin-left: auto;">Delete agent</button>
    </header>
    <main class="agent-view">
      ${renderAgentCard(agent, ratings)}
    </main>
  `;
  document.getElementById("back")!.addEventListener("click", () => {
    navigate({ view: "leaderboard" });
  });
  document.getElementById("delete-agent")!.addEventListener("click", async () => {
    if (!confirm(`Delete agent "${agent.id}"?\n\nThis removes the agent folder from disk. TrueSkill ratings and replay history are kept.`)) return;
    try {
      await api.deleteAgent(agent.id);
      navigate({ view: "leaderboard" });
    } catch (e) {
      alert(`Delete failed: ${(e as Error).message}`);
    }
  });
}

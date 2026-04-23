/**
 * Hash-based SPA router. Routes:
 *   #/                                            → Quick Match (split-screen launcher)
 *   #/leaderboard                                 → TrueSkill leaderboard
 *   #/runs                                        → runs history (quick matches filtered out)
 *   #/replays                                     → replays list (local + Kaggle)
 *   #/replay/:runId/:matchId                      → standalone replay viewer (local)
 *   #/kreplay/:submissionId/:episodeId            → Kaggle replay viewer
 *   #/agent/:agentId                              → agent details
 */

export type Route =
  | { view: "quick-match" }
  | { view: "leaderboard" }
  | { view: "tournaments" }
  | { view: "tournament-detail"; runId: string }
  | { view: "replays" }
  | { view: "agents" }
  | { view: "replay"; runId: string; matchId: string }
  | { view: "kaggle-replay"; submissionId: string; episodeId: string }
  | { view: "agent"; agentId: string };

export function parseHash(hash: string): Route {
  const h = hash.startsWith("#") ? hash.slice(1) : hash;
  const path = h.startsWith("/") ? h.slice(1) : h;
  const parts = path.split("/").filter(Boolean);

  if (parts.length === 0) return { view: "quick-match" };

  if (parts[0] === "leaderboard") {
    return { view: "leaderboard" };
  }

  // Backwards compat: old #/runs → #/tournaments
  if (parts[0] === "tournaments" || parts[0] === "runs") {
    if (parts.length >= 2) {
      return { view: "tournament-detail", runId: parts[1] };
    }
    return { view: "tournaments" };
  }

  if (parts[0] === "replays") {
    return { view: "replays" };
  }

  if (parts[0] === "agents" && parts.length === 1) {
    return { view: "agents" };
  }

  if (parts[0] === "replay" && parts.length >= 3) {
    return {
      view: "replay",
      runId: parts[1],
      matchId: parts[2],
    };
  }

  if (parts[0] === "kreplay" && parts.length >= 3) {
    return {
      view: "kaggle-replay",
      submissionId: parts[1],
      episodeId: parts[2],
    };
  }

  if (parts[0] === "agent" && parts.length >= 2) {
    // agent_id may have slashes: mine/v1-foo → path was encoded as /agent/mine/v1-foo
    return {
      view: "agent",
      agentId: parts.slice(1).join("/"),
    };
  }

  return { view: "quick-match" };
}

export function navigate(route: Route): void {
  if (route.view === "quick-match") {
    location.hash = "#/";
  } else if (route.view === "leaderboard") {
    location.hash = "#/leaderboard";
  } else if (route.view === "tournaments") {
    location.hash = "#/tournaments";
  } else if (route.view === "tournament-detail") {
    location.hash = `#/tournaments/${route.runId}`;
  } else if (route.view === "replays") {
    location.hash = "#/replays";
  } else if (route.view === "agents") {
    location.hash = "#/agents";
  } else if (route.view === "replay") {
    location.hash = `#/replay/${route.runId}/${route.matchId}`;
  } else if (route.view === "kaggle-replay") {
    location.hash = `#/kreplay/${route.submissionId}/${route.episodeId}`;
  } else {
    location.hash = `#/agent/${route.agentId}`;
  }
}

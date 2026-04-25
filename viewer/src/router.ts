/**
 * Hash-based SPA router. Routes:
 *   #/                                            → Quick Match
 *   #/leaderboard                                 → TrueSkill leaderboard
 *   #/tournaments                                 → tournaments list
 *   #/tournaments/:runId                          → tournament detail
 *   #/replays                                     → replays list (all sources)
 *   #/replays?sub=<id>                            → replays filtered by submission
 *   #/submissions                                 → my Kaggle submissions
 *   #/agents                                      → agent zoo
 *   #/agent/:agentId                              → agent details
 *   #/replay/:runId/:matchId                      → standalone local replay
 *   #/kreplay/:submissionId/:episodeId            → standalone Kaggle replay
 *   #/settings                                    → settings (Kaggle token setup)
 */

export type Route =
  | { view: "quick-match" }
  | { view: "leaderboard" }
  | { view: "tournaments" }
  | { view: "tournament-detail"; runId: string }
  | { view: "replays"; subFilter?: string }
  | { view: "submissions" }
  | { view: "agents" }
  | { view: "replay"; runId: string; matchId: string }
  | { view: "kaggle-replay"; submissionId: string; episodeId: string }
  | { view: "agent"; agentId: string }
  | { view: "settings" };

function splitPathAndQuery(raw: string): { path: string; query: Record<string, string> } {
  const [pathPart, queryPart] = raw.split("?");
  const query: Record<string, string> = {};
  if (queryPart) {
    for (const pair of queryPart.split("&")) {
      const [k, v] = pair.split("=");
      if (k) query[decodeURIComponent(k)] = decodeURIComponent(v ?? "");
    }
  }
  return { path: pathPart, query };
}

export function parseHash(hash: string): Route {
  const h = hash.startsWith("#") ? hash.slice(1) : hash;
  const { path, query } = splitPathAndQuery(h.startsWith("/") ? h.slice(1) : h);
  const parts = path.split("/").filter(Boolean);

  if (parts.length === 0) return { view: "quick-match" };

  if (parts[0] === "leaderboard") return { view: "leaderboard" };

  // Backwards compat: old #/runs → #/tournaments
  if (parts[0] === "tournaments" || parts[0] === "runs") {
    if (parts.length >= 2) {
      return { view: "tournament-detail", runId: parts[1] };
    }
    return { view: "tournaments" };
  }

  if (parts[0] === "replays") {
    return { view: "replays", subFilter: query["sub"] || undefined };
  }

  if (parts[0] === "submissions") return { view: "submissions" };

  if (parts[0] === "agents" && parts.length === 1) return { view: "agents" };

  if (parts[0] === "replay" && parts.length >= 3) {
    return { view: "replay", runId: parts[1], matchId: parts[2] };
  }

  if (parts[0] === "kreplay" && parts.length >= 3) {
    return {
      view: "kaggle-replay",
      submissionId: parts[1],
      episodeId: parts[2],
    };
  }

  if (parts[0] === "agent" && parts.length >= 2) {
    return { view: "agent", agentId: parts.slice(1).join("/") };
  }

  if (parts[0] === "settings") return { view: "settings" };

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
    location.hash = route.subFilter
      ? `#/replays?sub=${encodeURIComponent(route.subFilter)}`
      : "#/replays";
  } else if (route.view === "submissions") {
    location.hash = "#/submissions";
  } else if (route.view === "agents") {
    location.hash = "#/agents";
  } else if (route.view === "replay") {
    location.hash = `#/replay/${route.runId}/${route.matchId}`;
  } else if (route.view === "kaggle-replay") {
    location.hash = `#/kreplay/${route.submissionId}/${route.episodeId}`;
  } else if (route.view === "settings") {
    location.hash = "#/settings";
  } else {
    location.hash = `#/agent/${route.agentId}`;
  }
}

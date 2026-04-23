import { parseHash, Route } from "./router";
import { renderQuickMatch } from "./views/quick-match";
import { renderLeaderboard } from "./views/leaderboard";
import { renderTournaments } from "./views/tournaments";
import { renderTournamentDetail } from "./views/tournament-detail";
import { renderAgents } from "./views/agents";
import { renderReplays } from "./views/replays";
import { renderReplay } from "./views/replay";
import { renderKaggleReplay } from "./views/kaggle-replay";
import { renderAgent } from "./views/agent";
// Kaggle's player base CSS (.player/.viewer/.controls flex layout).
// NOT auto-bundled because core is a workspace dependency and vite skips
// side-effect CSS imports from workspace packages in production build.
import "@kaggle-environments/core/dist/style.css";
import "./style.css";
import "./styles/dashboard.css";
import "./styles/header-nav.css";
import "./styles/agent-picker.css";
import "./styles/match-config-bar.css";
import "./styles/embedded-replay.css";
import "./styles/quick-match.css";
import "./styles/replays.css";
import "./styles/tournaments.css";
import "./styles/tournament-detail.css";
import * as theme from "./theme";

const app = document.getElementById("app");
if (!app) {
  throw new Error("No #app element in index.html");
}

theme.init();

function dispatch(route: Route) {
  if (route.view === "quick-match") {
    renderQuickMatch(app!);
  } else if (route.view === "leaderboard") {
    renderLeaderboard(app!);
  } else if (route.view === "tournaments") {
    renderTournaments(app!);
  } else if (route.view === "tournament-detail") {
    renderTournamentDetail(app!, route.runId);
  } else if (route.view === "replays") {
    renderReplays(app!);
  } else if (route.view === "agents") {
    renderAgents(app!);
  } else if (route.view === "replay") {
    renderReplay(app!, route.runId, route.matchId);
  } else if (route.view === "kaggle-replay") {
    renderKaggleReplay(app!, route.submissionId, route.episodeId);
  } else {
    renderAgent(app!, route.agentId);
  }
}

window.addEventListener("hashchange", () => dispatch(parseHash(location.hash)));
dispatch(parseHash(location.hash || "#/"));

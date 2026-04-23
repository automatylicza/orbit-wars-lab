/**
 * Persistent header nav — Quick Match / Leaderboard / Runs / Powtórki.
 * Insert at top of every view (except standalone replay viewer).
 */
import { mountThemeToggle } from "./theme-toggle";

export type NavRoute =
  | "quick-match"
  | "leaderboard"
  | "tournaments"
  | "replays"
  | "agents"
  | "agent";

export function installHeaderNav(root: HTMLElement, active: NavRoute): void {
  const nav = document.createElement("header");
  nav.className = "header-nav";
  nav.innerHTML = `
    <div class="nav-brand">orbit-wars-lab</div>
    <nav class="nav-links">
      <a href="#/" class="nav-link ${active === "quick-match" ? "active" : ""}">Quick Match</a>
      <a href="#/tournaments" class="nav-link ${active === "tournaments" ? "active" : ""}">Tournaments</a>
      <a href="#/replays" class="nav-link ${active === "replays" ? "active" : ""}">Replays</a>
      <a href="#/agents" class="nav-link ${active === "agents" ? "active" : ""}">Agents</a>
      <a href="#/leaderboard" class="nav-link ${active === "leaderboard" ? "active" : ""}">Leaderboard</a>
    </nav>
    <div class="nav-actions"></div>
  `;
  root.prepend(nav);

  const actions = nav.querySelector<HTMLElement>(".nav-actions")!;
  mountThemeToggle(actions);
}

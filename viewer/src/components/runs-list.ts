import { api, RunSummary } from "../api";
import { navigate } from "../router";

export async function mountRunsList(
  el: HTMLElement,
  opts?: { excludeQuickMatch?: boolean },
): Promise<void> {
  const runs = await api.listRuns(opts);
  el.innerHTML = `
    <ul class="runs">
      ${runs
        .map(
          (r: RunSummary) => `
        <li data-run-id="${r.id}">
          <span class="run-id">${r.id}</span>
          <span class="run-meta">${r.mode} · ${r.format} · ${r.matches_done}/${r.total_matches}</span>
          <span class="run-status status-${r.status}">${r.status}</span>
        </li>
      `,
        )
        .join("")}
    </ul>
  `;
  el.querySelectorAll<HTMLLIElement>("li").forEach((li) => {
    li.addEventListener("click", async () => {
      const runId = li.getAttribute("data-run-id");
      if (!runId) return;
      const details = await api.getRun(runId);
      const matches = details.results?.matches ?? [];
      // Expand inline: show match list
      const ul = document.createElement("ul");
      ul.className = "matches";
      matches.forEach((m) => {
        const mli = document.createElement("li");
        mli.dataset.matchId = m.match_id;
        mli.innerHTML = `<span>${m.match_id}</span> <span>${m.agent_ids.join(" vs ")}</span> <span>${m.winner ?? "draw"}</span>`;
        mli.addEventListener("click", (e) => {
          e.stopPropagation();
          navigate({ view: "replay", runId, matchId: m.match_id });
        });
        ul.appendChild(mli);
      });
      // Insert or toggle
      const next = li.nextElementSibling;
      if (next && next.classList.contains("matches")) {
        next.remove();
      } else {
        li.after(ul);
      }
    });
  });
}

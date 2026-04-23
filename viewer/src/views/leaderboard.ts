import { mountRatingsTable, RatingsFormat } from "../components/ratings-table";
import { installHeaderNav } from "../components/header-nav";
import { api } from "../api";

let pollInterval: number | null = null;

const TITLES: Record<RatingsFormat, string> = {
  "2p": "TrueSkill ratings — 2p",
  "4p": "TrueSkill ratings — 4p",
  all: "TrueSkill ratings — wszystko",
};

export async function renderLeaderboard(root: HTMLElement): Promise<void> {
  let currentFormat: RatingsFormat = "2p";

  root.innerHTML = `
    <main class="dashboard">
      <section>
        <div class="section-head">
          <h2 id="lb-title">${TITLES[currentFormat]}</h2>
          <div class="lb-format-pills">
            <button class="settings-pill" data-format="2p">2p</button>
            <button class="settings-pill" data-format="4p">4p</button>
            <button class="settings-pill" data-format="all">wszystko</button>
          </div>
          <button id="reset-lb" class="scrape-btn cancel">Reset leaderboard</button>
        </div>
        <div id="ratings"></div>
      </section>
    </main>
  `;
  installHeaderNav(root, "leaderboard");

  const ratingsEl = document.getElementById("ratings")!;
  const titleEl = document.getElementById("lb-title")!;

  function updatePillState() {
    root.querySelectorAll<HTMLButtonElement>(".lb-format-pills .settings-pill").forEach((b) => {
      b.classList.toggle("on", b.dataset.format === currentFormat);
    });
  }

  async function refresh() {
    if (document.hidden) return;
    titleEl.textContent = TITLES[currentFormat];
    updatePillState();
    await mountRatingsTable(ratingsEl, currentFormat);
  }

  root.querySelectorAll<HTMLButtonElement>(".lb-format-pills .settings-pill").forEach((b) => {
    b.addEventListener("click", () => {
      const f = b.dataset.format as RatingsFormat | undefined;
      if (!f || f === currentFormat) return;
      currentFormat = f;
      void refresh();
    });
  });

  await refresh();

  document.getElementById("reset-lb")!.addEventListener("click", async () => {
    const target = currentFormat;
    const label =
      target === "all"
        ? "Reset TrueSkill ratings for ALL formats (2p + 4p)?"
        : `Reset TrueSkill ratings for ${target}?`;
    if (!confirm(
      `${label}\n\nEvery agent's μ/σ goes back to default (600 / 200, 0 games). ` +
      `Tournament history is kept.`
    )) return;
    try {
      await api.resetRatings(target);
      await refresh();
    } catch (e) {
      alert(`Reset failed: ${(e as Error).message}`);
    }
  });

  if (pollInterval !== null) window.clearInterval(pollInterval);
  pollInterval = window.setInterval(refresh, 5000);
}

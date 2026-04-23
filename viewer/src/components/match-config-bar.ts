/**
 * Match config bar — inline pill toggles for games / mode / seed / format.
 * Emits onChange(config) on each change.
 */

export interface MatchConfig {
  games: number;
  mode: "fast" | "faithful";
  seed: "random" | 42;
  format: "2p" | "4p";
}

export interface MatchConfigHandle {
  getConfig(): MatchConfig;
}

export function mountMatchConfigBar(
  root: HTMLElement,
  onChange: (cfg: MatchConfig) => void,
): MatchConfigHandle {
  const config: MatchConfig = {
    games: 1,
    mode: "fast",
    seed: "random",
    format: "2p",
  };

  function render() {
    root.innerHTML = `
      <div class="config-bar">
        <div class="config-group">
          <span class="config-label">format</span>
          <button class="config-pill ${config.format === "2p" ? "on" : ""}" data-k="format" data-v="2p">2p</button>
          <button class="config-pill ${config.format === "4p" ? "on" : ""}" data-k="format" data-v="4p">4p</button>
        </div>
        <div class="config-group">
          <span class="config-label">games</span>
          ${[1, 3, 5]
            .map(
              (n) =>
                `<button class="config-pill ${config.games === n ? "on" : ""}" data-k="games" data-v="${n}">${n}</button>`,
            )
            .join("")}
        </div>
        <div class="config-group">
          <span class="config-label">mode</span>
          <button class="config-pill ${config.mode === "fast" ? "on" : ""}" data-k="mode" data-v="fast">fast</button>
          <button class="config-pill ${config.mode === "faithful" ? "on" : ""}" data-k="mode" data-v="faithful">faithful</button>
        </div>
        <div class="config-group">
          <span class="config-label">seed</span>
          <button class="config-pill ${config.seed === "random" ? "on" : ""}" data-k="seed" data-v="random">random</button>
          <button class="config-pill ${config.seed === 42 ? "on" : ""}" data-k="seed" data-v="42">42</button>
        </div>
      </div>
    `;

    root.querySelectorAll<HTMLButtonElement>(".config-pill").forEach((el) => {
      el.addEventListener("click", () => {
        const k = el.dataset.k as keyof MatchConfig;
        const v = el.dataset.v!;
        if (k === "games") config.games = parseInt(v, 10);
        else if (k === "mode") config.mode = v as "fast" | "faithful";
        else if (k === "seed") config.seed = v === "42" ? 42 : "random";
        else if (k === "format") config.format = v as "2p" | "4p";
        onChange({ ...config });
        render();
      });
    });
  }

  render();
  return { getConfig: () => ({ ...config }) };
}

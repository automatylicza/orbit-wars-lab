/**
 * Pure HTML-string renderers for the Quick Match View sidebar
 * (Selected Planet + Selected Fleet cards, owner pill, placeholder).
 *
 * Pure in/out — no DOM queries, no listeners, no state. Consumers wire
 * click handlers + storage events themselves and call these to generate
 * markup for innerHTML.
 */

export function resetPanel(el: HTMLElement, placeholder: string): void {
  el.classList.add("qm-view-empty");
  el.textContent = placeholder;
}

export function ownerLabel(owner: number, playerColors: readonly string[]): string {
  if (owner < 0) return "neutral";
  const color = playerColors[owner] ?? "#666";
  return `<span class="color-dot" style="background-color:${color}"></span>P${owner + 1}`;
}

export function planetCard(
  d: {
    id: number;
    owner: number;
    ships: number;
    production: number;
    x: number;
    y: number;
    radius: number;
    isComet: boolean;
    inbound: Array<{ owner: number; ships: number; eta: number; fromPlanetId: number }>;
  },
  playerColors: readonly string[],
  removable: boolean,
): string {
  const inboundHtml = d.inbound.length === 0
    ? `<div class="qm-sel-muted">No fleets incoming.</div>`
    : `<ul class="qm-inbound">${
        d.inbound.map((f) =>
          `<li>
            <span class="color-dot" style="background-color:${playerColors[f.owner] ?? "#666"}"></span>
            <span class="qm-inbound-ships">${Math.floor(f.ships)}</span>
            <span class="qm-inbound-eta">ETA ${f.eta}t</span>
            <span class="qm-inbound-from">from #${f.fromPlanetId}</span>
          </li>`,
        ).join("")
      }</ul>`;
  const removeBtn = removable
    ? `<button class="qm-sel-remove" data-kind="planet" data-id="${d.id}" title="Remove from selection">×</button>`
    : "";
  return `
    <div class="qm-sel-card">
      ${removeBtn}
      <dl class="qm-sel-stats">
        <dt>id</dt><dd>#${d.id}${d.isComet ? " (comet)" : ""}</dd>
        <dt>owner</dt><dd>${ownerLabel(d.owner, playerColors)}</dd>
        <dt>ships</dt><dd>${Math.floor(d.ships)}</dd>
        <dt>prod</dt><dd>+${d.production}/t</dd>
        <dt>pos</dt><dd>${d.x.toFixed(1)}, ${d.y.toFixed(1)}</dd>
        <dt>radius</dt><dd>${d.radius.toFixed(1)}</dd>
      </dl>
      <div class="qm-sel-section-label">Inbound fleets (${d.inbound.length})</div>
      ${inboundHtml}
    </div>
  `;
}

export function fleetCard(
  d: {
    id: number;
    owner: number;
    ships: number;
    speed: number;
    x: number;
    y: number;
    fromPlanetId: number;
    target: null | {
      planetId: number;
      planetOwner: number;
      eta: number;
      distance: number;
    };
  },
  playerColors: readonly string[],
  removable: boolean,
): string {
  const target = d.target;
  const targetHtml = target
    ? `<dl class="qm-sel-stats">
        <dt>dest</dt><dd>#${target.planetId} (${ownerLabel(target.planetOwner, playerColors)})</dd>
        <dt>eta</dt><dd><span class="qm-inbound-eta">${target.eta}t</span></dd>
        <dt>dist</dt><dd>${target.distance.toFixed(1)}u</dd>
      </dl>`
    : `<div class="qm-sel-muted">No planet on trajectory.</div>`;
  const removeBtn = removable
    ? `<button class="qm-sel-remove" data-kind="fleet" data-id="${d.id}" title="Remove from selection">×</button>`
    : "";
  return `
    <div class="qm-sel-card">
      ${removeBtn}
      <dl class="qm-sel-stats">
        <dt>id</dt><dd>#${d.id}</dd>
        <dt>owner</dt><dd>${ownerLabel(d.owner, playerColors)}</dd>
        <dt>ships</dt><dd>${Math.floor(d.ships)}</dd>
        <dt>speed</dt><dd>${d.speed.toFixed(2)} u/t</dd>
        <dt>pos</dt><dd>${d.x.toFixed(1)}, ${d.y.toFixed(1)}</dd>
        <dt>from</dt><dd>#${d.fromPlanetId}</dd>
      </dl>
      <div class="qm-sel-section-label">Target</div>
      ${targetHtml}
    </div>
  `;
}

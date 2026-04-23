/**
 * Agent picker — N slots (2 for 2p, 4 for 4p) + shared agent list
 * with search + bucket filter + active-slot auto-advance.
 *
 * Emits onChange(slots) on each change. `slots` is string[] length = numSlots,
 * with `null` for empty positions (represented as empty string in the array).
 */

import { api, AgentInfo, Rating } from "../api";

export type PickerSelection = (string | null)[];

type BucketFilter =
  | "all"
  | "baselines"
  | "ext-rule"
  | "ext-nn"
  | "mine";

/**
 * Split "external" bucket into "ext-nn" (tagged neural-network) and
 * "ext-rule" (everything else). Baselines/mine buckets pass through.
 */
function agentCategory(a: AgentInfo): Exclude<BucketFilter, "all"> {
  if (a.bucket === "external") {
    return a.tags.includes("neural-network") ? "ext-nn" : "ext-rule";
  }
  return a.bucket;
}

const CATEGORY_LABELS: Record<Exclude<BucketFilter, "all">, string> = {
  baselines: "baselines",
  "ext-rule": "ext · rule",
  "ext-nn": "ext · nn",
  mine: "mine",
};

export interface AgentPickerHandle {
  reset(): void;
  getSelection(): PickerSelection;
  refreshRatings(): Promise<void>;
  setNumSlots(n: number): void;
}

export async function mountAgentPicker(
  root: HTMLElement,
  onChange: (sel: PickerSelection) => void,
  initialSlots: number = 2,
): Promise<AgentPickerHandle> {
  const [agents, ratings] = await Promise.all([
    api.listAgents(),
    api.getRatings("2p"),
  ]);
  const ratingMap = new Map(ratings.map((r: Rating) => [r.agent_id, r.mu]));

  let numSlots = initialSlots;
  let slots: (string | null)[] = new Array(numSlots).fill(null);
  let activeIdx = 0;
  let searchTerm = "";
  let bucketFilter: BucketFilter = "all";

  function slotLabel(i: number): string {
    if (numSlots === 2) return i === 0 ? "LEFT" : "RIGHT";
    return `P${i + 1}`;
  }

  function render() {
    const filtered = agents.filter((a) => {
      if (a.disabled) return false;
      if (bucketFilter !== "all" && agentCategory(a) !== bucketFilter) return false;
      if (searchTerm) {
        const t = searchTerm.toLowerCase();
        if (
          !a.id.toLowerCase().includes(t) &&
          !a.name.toLowerCase().includes(t)
        )
          return false;
      }
      return true;
    });

    const slotHtml = slots
      .map((id, i) => {
        const agent = id ? agents.find((a) => a.id === id) : null;
        const active = i === activeIdx;
        const picked = !!id;
        const cls = `picker-slot ${active ? "active" : ""} ${picked ? "picked" : "empty"}`;
        const inner =
          id && agent
            ? `<span class="slot-name">${agent.name}</span>
               <span class="slot-meta">${slotLabel(i)} · μ ${(ratingMap.get(id) ?? 0).toFixed(0)}</span>`
            : `+ pick ${slotLabel(i)}`;
        return `<div class="${cls}" data-slot="${i}">${inner}</div>`;
      })
      .join("");

    root.innerHTML = `
      <div class="picker-slots picker-slots-${numSlots}">
        ${slotHtml}
      </div>
      <div class="picker-filters">
        <input class="picker-search" type="text" placeholder="search agents…" value="${searchTerm}">
        <div class="picker-tags">
          <button class="picker-pill ${bucketFilter === "all" ? "on" : ""}" data-bucket="all">all</button>
          <button class="picker-pill ${bucketFilter === "baselines" ? "on" : ""}" data-bucket="baselines">baselines</button>
          <button class="picker-pill ${bucketFilter === "ext-rule" ? "on" : ""}" data-bucket="ext-rule">ext · rule</button>
          <button class="picker-pill ${bucketFilter === "ext-nn" ? "on" : ""}" data-bucket="ext-nn">ext · nn</button>
          <button class="picker-pill ${bucketFilter === "mine" ? "on" : ""}" data-bucket="mine">mine</button>
        </div>
      </div>
      <ul class="picker-list">
        ${
          filtered.length === 0
            ? `<li class="picker-empty">No agents match this filter.</li>`
            : filtered
                .map((a) => {
                  const mu = ratingMap.get(a.id);
                  const muStr = mu !== undefined ? `μ ${mu.toFixed(0)}` : "—";
                  const picked = slots.includes(a.id);
                  return `
                    <li class="picker-agent ${picked ? "picked" : ""}" data-agent-id="${a.id}">
                      <span class="agent-name">${a.name}</span>
                      <span class="agent-bucket">${CATEGORY_LABELS[agentCategory(a)]}</span>
                      <span class="agent-mu">${muStr}</span>
                    </li>
                  `;
                })
                .join("")
        }
      </ul>
    `;

    root.querySelectorAll<HTMLDivElement>(".picker-slot").forEach((el) => {
      el.addEventListener("click", () => {
        activeIdx = parseInt(el.dataset.slot!, 10);
        render();
      });
    });

    const searchInput = root.querySelector<HTMLInputElement>(".picker-search")!;
    // Restore focus after render() rebuilt innerHTML — otherwise typing a
    // single letter "kicks the user out" of the search box.
    if (searchTerm) {
      searchInput.focus();
      const end = searchInput.value.length;
      searchInput.setSelectionRange(end, end);
    }
    searchInput.addEventListener("input", (e) => {
      searchTerm = (e.target as HTMLInputElement).value;
      render();
    });

    root.querySelectorAll<HTMLButtonElement>("[data-bucket]").forEach((el) => {
      el.addEventListener("click", () => {
        bucketFilter = el.dataset.bucket as typeof bucketFilter;
        render();
      });
    });

    root.querySelectorAll<HTMLLIElement>(".picker-agent").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.agentId!;
        slots[activeIdx] = id;
        // Auto-advance to next empty slot (or wrap to 0)
        activeIdx = (activeIdx + 1) % numSlots;
        onChange([...slots]);
        render();
      });
    });
  }

  render();

  return {
    reset() {
      slots = new Array(numSlots).fill(null);
      activeIdx = 0;
      onChange([...slots]);
      render();
    },
    getSelection() {
      return [...slots];
    },
    async refreshRatings() {
      const fresh = await api.getRatings("2p");
      ratingMap.clear();
      for (const r of fresh) ratingMap.set(r.agent_id, r.mu);
      render();
    },
    setNumSlots(n: number) {
      if (n === numSlots) return;
      numSlots = n;
      // Keep existing picks, truncate or pad
      if (slots.length > n) slots = slots.slice(0, n);
      while (slots.length < n) slots.push(null);
      activeIdx = Math.min(activeIdx, n - 1);
      onChange([...slots]);
      render();
    },
  };
}

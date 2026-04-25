/** Typed API client. Uses /api prefix (Vite dev proxy or prod same-origin). */

export interface AgentInfo {
  id: string;
  name: string;
  bucket: "baselines" | "external" | "mine";
  description?: string | null;
  author?: string | null;
  source_url?: string | null;
  version?: string | null;
  date_fetched?: string | null;
  tags: string[];
  disabled: boolean;
  has_yaml: boolean;
  path: string;
  last_error?: string | null;
}

export interface Rating {
  agent_id: string;
  mu: number;
  sigma: number;
  conservative: number;
  games_played: number;
  rank: number;
}

export interface RunSummary {
  id: string;
  started_at: string;
  finished_at?: string | null;
  mode: "fast" | "faithful";
  format: "2p" | "4p";
  status: "running" | "completed" | "aborted";
  total_matches: number;
  matches_done: number;
  is_quick_match?: boolean;
}

export interface KaggleSubmission {
  submission_id: number;
  description: string;
  date: string;
  status: string;
  mu: number | null;
  sigma: number | null;
  rank: number | null;
  games_played: number | null;
}

export interface AgentLogsResponse {
  submission_id: number;
  episode_id: number;
  agent_idx: number;
  text: string;
}

export interface ScrapeJob {
  job_id: string;
  submission_id: number;
  count: number;
  status: "pending" | "running" | "completed" | "failed";
  total: number;
  downloaded: number;
  error: string | null;
}

export interface MatchResult {
  match_id: string;
  agent_ids: string[];
  winner: string | null;
  scores: number[];
  turns: number;
  duration_s: number;
  status: string;
  seed: number;
  replay_path: string;
}

async function j<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, opts);
  if (!r.ok) {
    const err = new Error(
      `${r.status} ${r.statusText}: ${opts?.method ?? "GET"} /api${path}`,
    ) as Error & { status?: number };
    err.status = r.status;
    throw err;
  }
  return r.json();
}

export const api = {
  listAgents: () => j<AgentInfo[]>("/agents"),
  getAgent: (id: string) => j<AgentInfo>(`/agents/${id}`),
  getRatings: (format: "2p" | "4p" = "2p") =>
    j<Rating[]>(`/ratings?format=${format}`),
  listRuns: (opts?: { excludeQuickMatch?: boolean }) => {
    const qs = opts?.excludeQuickMatch ? "?exclude_quick_match=true" : "";
    return j<RunSummary[]>(`/runs${qs}`);
  },
  getRun: (id: string) => j<{
    id: string;
    config?: any;
    results?: { matches: MatchResult[]; summary: any; total_matches: number };
    trueskill?: any;
    run?: RunSummary;
  }>(`/runs/${id}`),
  getRunProgress: (id: string) =>
    j<{ status: string; matches_done: number; total_matches: number }>(
      `/runs/${id}/progress`,
    ),
  getReplay: (runId: string, matchId: string) =>
    j<any>(`/replays/${runId}/${matchId}`),
  startTournament: (cfg: {
    agents: string[];
    games_per_pair: number;
    mode: string;
    format: string;
    parallel?: number;
    seed_base?: number;
    is_quick_match?: boolean;
    shape?: "round-robin" | "gauntlet";
    challenger_id?: string | null;
  }) =>
    j<{ run_id: string; status: string }>("/tournaments", {
      method: "POST",
      body: JSON.stringify(cfg),
      headers: { "Content-Type": "application/json" },
    }),
  deleteLocalReplay: (runId: string, matchId: string) =>
    j<{ deleted: boolean }>(`/replays/${runId}/${matchId}`, { method: "DELETE" }),
  deleteKaggleReplay: (submissionId: number, episodeId: number) =>
    j<{ deleted: boolean }>(`/kaggle-replays/${submissionId}/${episodeId}`, {
      method: "DELETE",
    }),
  deleteRun: (runId: string) =>
    j<{ deleted: boolean }>(`/runs/${runId}`, { method: "DELETE" }),
  deleteAgent: (agentId: string) =>
    j<{ deleted: boolean }>(`/agents/${agentId}`, { method: "DELETE" }),
  resetRatings: (format: "2p" | "4p" | "all" = "all") =>
    j<{ reset: boolean }>(`/ratings/reset?format=${format}`, { method: "POST" }),
  listKaggleSubmissions: () =>
    j<KaggleSubmission[]>(`/kaggle-submissions`),
  submitKaggleAgent: (agentId: string, description: string) =>
    j<{ ok: boolean; message: string }>(`/kaggle-submissions`, {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, description }),
      headers: { "Content-Type": "application/json" },
    }),
  getAgentLogs: (submissionId: number, episodeId: number) =>
    j<AgentLogsResponse>(
      `/kaggle-submissions/${submissionId}/episodes/${episodeId}/logs`,
    ),
  startScrape: (submissionId: number, count: number) =>
    j<{ job_id: string; status: string }>(`/replays/scrape`, {
      method: "POST",
      body: JSON.stringify({ submission_id: submissionId, count }),
      headers: { "Content-Type": "application/json" },
    }),
  getScrapeStatus: (jobId: string) => j<ScrapeJob>(`/replays/scrape/${jobId}`),
  getKaggleAuthStatus: () => j<KaggleAuthStatus>(`/kaggle-auth`),
  saveKaggleAuth: (token: string, signal?: AbortSignal) =>
    j<KaggleAuthStatus>(`/kaggle-auth`, {
      method: "POST",
      body: JSON.stringify({ token }),
      headers: { "Content-Type": "application/json" },
      signal,
    }),
  clearKaggleAuth: () =>
    j<KaggleAuthStatus>(`/kaggle-auth`, { method: "DELETE" }),
};

export interface KaggleAuthStatus {
  connected: boolean;
  username: string | null;
  source: "file" | "env" | null;
  shadowed?: boolean;
  saved_username?: string | null;
  deleted?: boolean;
}

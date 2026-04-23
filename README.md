# Orbit Wars Lab

Local tournament runner + visualizer for the
[Orbit Wars Kaggle competition](https://www.kaggle.com/competitions/orbit-wars).

Ships with 9 agents out-of-the-box (3 baselines + 5 curated rule-based from
public Kaggle notebooks + 1 PPO RL agent) and a pre-seeded TrueSkill
leaderboard. Adds a browser UI on top of the official Kaggle replay player:
live stats sidebar, click-to-select planets/fleets, multi-selection with
inbound-fleet ETAs, light/dark mode, and separate tournament formats
(round-robin + gauntlet).

*(screenshot placeholder — add one before making the repo public)*

---

## Quick start

### Option 1: Docker (recommended)

```bash
git clone https://github.com/automatylicza/orbit-wars-lab.git
cd orbit-wars-lab
docker compose up
```

Open <http://localhost:6001>. Done.

First run builds the image (~3-5 min, pulls pytorch CPU). Subsequent `up`
is instant.

### Option 2: Native dev (faster iteration)

Requires **Python 3.12** + **pnpm** (`npm i -g pnpm`).

```bash
git clone https://github.com/automatylicza/orbit-wars-lab.git
cd orbit-wars-lab
bash scripts/dev.sh
```

Script creates `.venv`, installs deps, and starts backend (:8000) + Vite
viewer (:6001) with hot-reload. Open <http://localhost:6001>.

---

## What you get

- **9 agents ready to play** (see [`agents/`](agents/))
  - `baselines/{random,starter,nearest-sniper}` — reference agents shipped
    by Kaggle
  - `external/pilkwang-structured` — 120 votes, LB claim ~1000, most
    rule-layered reference
  - `external/tamrazov-starwars` — LB claim 1224, simulation-based
  - `external/sigmaborov-{starter,reinforce}` — rule-based with comet/sun
    awareness
  - `external/yuriygreben-architect` — physics-aware multi-phase
  - `external/kashiwaba-rl` — PPO neural-net policy (2000 updates
    checkpoint)
- **Pre-seeded TrueSkill leaderboard** (`runs/trueskill.json`) — 360 2p
  games + 350 4p games already computed, so you can compare new agents
  immediately against a stable ranking.
- **Quick Match UI** — pick 2 or 4 agents, play a game, view replay with a
  live-stats sidebar (select any planet/fleet to see ships, production,
  inbound fleets + ETA, destination, speed).
- **Tournaments** — two formats:
  - *Round-robin* (every pair ×K games)
  - *Gauntlet* (one challenger vs the rest ×K games) — useful when you add
    your own agent and want fast relative rating.
- **Replay library** — combined view of local tournament replays + any
  Kaggle episodes you import (paste a Kaggle URL).

Everything lives in one Python process (FastAPI backend) serving the Vite
frontend as static files — no separate node runtime in production.

---

## Adding your own agent

```bash
cp -r agents/baselines/starter agents/mine/v1-my-bot
# edit agents/mine/v1-my-bot/main.py — replace the `def agent(obs)` body
```

Then in the viewer, pick it in *Quick Match → Picker → mine* and hit Play.
For a full benchmark, run a Gauntlet tournament with your agent as the
challenger (`Tournaments → Shape: gauntlet → Challenger: mine/v1-my-bot`).

CLI equivalent:

```bash
python -m orbit_wars_app.tournament gauntlet mine/v1-my-bot --games-per-pair 10
```

---

## Architecture

```
viewer/              Vite + TypeScript SPA (vanilla DOM, no framework)
orbit_wars_app/      FastAPI backend + tournament runner (Python 3.12)
web/core/            Vendored @kaggle-environments/core (React replay player)
agents/
  baselines/         Reference agents (tracked in git)
  external/          Curated public notebooks (tracked in git)
  mine/              Your agents go here
runs/
  trueskill.json     Persistent TrueSkill state (seeded snapshot)
```

`docker-compose.yml` runs a single multi-stage image:

1. Node builder → `viewer/dist`
2. Python runtime → serves both API and the static viewer on port 8000
   (published as 6001)

---

## Credits

Rule-based external agents are redistributed from their authors' public
Kaggle notebooks (links + versions in each agent's `agent.yaml`). Only the
vendored Kaggle core and viewer code are original to this repo.

If you're an author and want your agent removed, open an issue.

---

## License

MIT. See [`LICENSE`](LICENSE).

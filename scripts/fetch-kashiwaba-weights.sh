#!/usr/bin/env bash
# Fetch kashiwaba PPO weights for agents/external/kashiwaba-rl.
# Dataset: https://www.kaggle.com/datasets/kashiwaba/orbitwars-ppo-sample-weight
# 3 checkpoints × 1.86MB = ~5.6MB total.
set -euo pipefail

KAGGLE_BIN="${KAGGLE_BIN:-kaggle}"
TARGET="agents/external/kashiwaba-rl/weights"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT"
mkdir -p "$TARGET"

if [ -f "$TARGET/ckpt_002000.pt" ]; then
  echo "weights already present — skipping download."
  ls -la "$TARGET"
  exit 0
fi

echo "Downloading weights to $TARGET..."
"$KAGGLE_BIN" datasets download \
  kashiwaba/orbitwars-ppo-sample-weight \
  -p "$TARGET" --unzip

echo "Done:"
ls -la "$TARGET"

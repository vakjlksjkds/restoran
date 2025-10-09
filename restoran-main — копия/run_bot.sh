#!/usr/bin/env bash
# Run Telegram restaurant bot ensuring only one instance
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
# activate venv
if [[ -f ".venv/bin/activate" ]]; then
  source .venv/bin/activate
fi
# kill previous bot instances
pkill -f "python main.py" 2>/dev/null || true
# start new bot (long polling)
python main.py

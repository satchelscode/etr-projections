#!/usr/bin/env bash
set -euo pipefail

# Change into repo root (this script lives in scripts/)
cd "$(dirname "$0")/.."

# 1) Put today's ETR CSV into data/raw and master.parquet
#    Expect the file in ./inbox/todays.csv (you can change this path)
TODAY=$(TZ=America/New_York date +%F)
INBOX_CSV="inbox/todays.csv"   # <-- drop today's ETR export here before 5pm ET
if [[ ! -f "$INBOX_CSV" ]]; then
  echo "Missing $INBOX_CSV — put today's ETR CSV there." >&2
  exit 1
fi

python etr_add_daily.py --csv "$INBOX_CSV" --date "$TODAY"

# 2) Retrain from full history (or add --window-days 45 for rolling 45 days)
python train_from_history.py --min-minutes 6

# 3) Optionally commit artifacts so the app redeploys with latest
git add artifacts/*.csv artifacts/*.json data/master.parquet
git commit -m "daily train: $TODAY"
git push

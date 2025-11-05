#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TODAY=$(TZ=America/New_York date +%F)
INBOX_CSV="inbox/todays.csv"

if [[ ! -f "$INBOX_CSV" ]]; then
  echo "❌ ERROR: inbox/todays.csv not found — upload ETR CSV before midnight"
  exit 1
fi

echo "✅ Adding $INBOX_CSV for $TODAY"
python etr_add_daily.py --csv "$INBOX_CSV" --date "$TODAY"

echo "✅ Retraining model from full history"
python train_from_history.py --min-minutes 6

# OPTIONAL: commit + push the updated artifacts
git add artifacts/*.csv artifacts/*.json data/master.parquet || true
git commit -m "nightly model update $TODAY" || true
git push || true

# Cleanup inbox if you want
# rm inbox/todays.csv
echo "✅ Nightly job finished"

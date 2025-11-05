# No‑Juice Projections (Minutes → Stats)

A tiny Flask app that serves projections from reverse‑engineered artifacts. Pick a player + opponent, enter minutes, get stat projections instantly.

## Quick start (local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Put your daily ETR-like CSVs into ./data/
python train_artifacts.py   # generates artifacts/

python app.py
# open http://localhost:5005
```

## Deploy on Render

1) **Train locally** (as above) so `artifacts/` is populated.
2) Commit everything (including `artifacts/`) to GitHub.
3) Render → New → Web Service → pick repo. It will use `render.yaml`:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`

If you prefer auto-train on deploy, include your `data/` in the repo and change `buildCommand`:

```yaml
buildCommand: |
  pip install -r requirements.txt
  python train_artifacts.py
```

## Notes
- If artifacts are missing, the UI shows a friendly warning.
- Unseen players → median per‑minute rate. Unseen opponents → 0 adj.
- Projection: `intercept + minutes×player_rate + opp_adj`.

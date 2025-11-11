from flask import Blueprint, request, jsonify
from datetime import datetime
import os, glob
import pandas as pd

from gpt_core import fit_model, save_artifact, load_latest_artifact, predict_with_features

bp = Blueprint("gpt_api", __name__)

def _strip_dates(obj):
    if isinstance(obj, dict):
        obj.pop("Date", None); obj.pop("DateIdx", None); obj.pop("date", None)
        return {k: _strip_dates(v) for k,v in obj.items()}
    if isinstance(obj, list):
        return [_strip_dates(x) for x in obj]
    return obj

def _ensure_dirs():
    os.makedirs("data/etr", exist_ok=True)
    os.makedirs("artifacts", exist_ok=True)

@bp.get("/status")
def status():
    return jsonify(ok=True)

@bp.get("/models/latest")
def models_latest():
    paths = sorted(glob.glob("artifacts/*.pkl"), key=os.path.getmtime, reverse=True)
    latest = os.path.basename(paths[0]).replace(".pkl","") if paths else None
    return jsonify(ok=True, latest=latest)

@bp.post("/upload-etr")
def upload_etr():
    _ensure_dirs()
    f = request.files.get("file")
    if not f:
        return jsonify(ok=False, error="no file"), 400
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    path = os.path.join("data/etr", f"etr_{ts}.csv")
    f.save(path)
    return jsonify(ok=True, saved=path)

@bp.post("/train")
def train():
    _ensure_dirs()
    files = sorted(glob.glob("data/etr/*.csv"))
    if not files:
        return jsonify(ok=False, error="no ETR CSVs uploaded"), 400

    dfs = []
    for p in files:
        try:
            df = pd.read_csv(p)
        except Exception:
            df = pd.read_csv(p, encoding="latin-1")
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)

    cmap = {c.lower(): c for c in df.columns}
    def col(*alts):
        for a in alts:
            if a.lower() in cmap: return cmap[a.lower()]
        return None

    player_col  = col("Player","player","PLAYER")
    team_col    = col("Team","team","TEAM")
    opp_col     = col("Opp","Opponent","opp","OPP")
    minutes_col = col("Minutes","Min","mins","minutes","MIN")
    if not all([player_col, team_col, opp_col, minutes_col]):
        return jsonify(ok=False, error="CSV must include Player, Team, Opp, Minutes"), 400

    stat_candidates = ["PTS","REB","AST","3PM","STL","BLK","TOV","PRA"]
    stat_cols = [c for c in df.columns if c.upper() in stat_candidates]
    if not stat_cols:
        return jsonify(ok=False, error="no stat projection columns found"), 400

    long = df[[player_col, team_col, opp_col, minutes_col] + stat_cols].copy()
    long = long.rename(columns={
        player_col:"Player", team_col:"Team", opp_col:"Opp", minutes_col:"Minutes"
    })
    long = long.melt(id_vars=["Player","Team","Opp","Minutes"],
                     value_vars=stat_cols,
                     var_name="Stat", value_name="Projection")
    long = long.dropna(subset=["Player","Team","Opp","Minutes","Stat","Projection"])
    long["Minutes"] = pd.to_numeric(long["Minutes"], errors="coerce")
    long["Projection"] = pd.to_numeric(long["Projection"], errors="coerce")
    long = long.dropna(subset=["Minutes","Projection"])
    if long.empty:
        return jsonify(ok=False, error="no training rows after cleaning"), 400

    bundle = fit_model(long)
    model_id = f"model_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}"
    out_path = save_artifact(bundle, model_id)
    return jsonify(_strip_dates({"ok": True, "model_id": model_id, "saved": out_path}))

@bp.get("/predict")
def predict():
    player  = request.args.get("player")
    team    = request.args.get("team")
    opp     = request.args.get("opp")
    minutes = request.args.get("minutes", type=float, default=30)
    if not player or not team or not opp:
        return jsonify(ok=False, error="Missing player/team/opp"), 400
    try:
        bundle = load_latest_artifact()
    except Exception as e:
        return jsonify(ok=False, error=f"Model load failed: {e}"), 500
    try:
        preds = predict_with_features(bundle, player, team, opp, minutes)
        return jsonify(_strip_dates({"ok":True, "pred": preds}))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

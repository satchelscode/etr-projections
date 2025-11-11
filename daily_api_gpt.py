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

@bp.get("/debug/etr_columns")
def debug_etr_columns():
    files = sorted(glob.glob("data/etr/*.csv"))
    if not files:
        return jsonify(ok=False, error="no ETR CSVs uploaded"), 400
    import collections
    counts = collections.Counter()
    samples = {}
    for p in files:
        try:
            df = pd.read_csv(p, nrows=1)
        except Exception:
            df = pd.read_csv(p, nrows=1, encoding="latin-1")
        for c in df.columns:
            counts[c] += 1
            if c not in samples and not df.empty:
                samples[c] = str(df.iloc[0].get(c, ""))
    cols = [{"name": k, "count": v, "sample": samples.get(k, "")}
            for k, v in counts.most_common(300)]
    return jsonify(ok=True, files=len(files), columns=cols)

ALIASES = {
    # canonical -> list of possible CSV column names
    "PTS": ["PTS","Points","Proj Pts","Projected Points","Points Projection"],
    "REB": ["REB","Rebounds","Proj Reb","Projected Rebounds","Rebounds Projection"],
    "AST": ["AST","Assists","Proj Ast","Projected Assists","Assists Projection"],
    "3PM": ["3PM","3PTM","3PT FG Made","3PT Made","3-Pointers Made","3PT","3P Made"],
    "PRA": ["PRA","Pts+Reb+Ast","Points+Rebounds+Assists","Proj PRA"],
    "STL": ["STL","Steals","Projected Steals","Steals Projection"],
    "BLK": ["BLK","Blocks","Projected Blocks","Blocks Projection"],
    "TOV": ["TOV","Turnovers","Projected Turnovers","Turnovers Projection"],
}

def _find_present_stat_cols(df):
    present = {}
    lower_map = {c.lower(): c for c in df.columns}
    for canon, options in ALIASES.items():
        for opt in options:
            c = lower_map.get(opt.lower())
            if c:
                present[canon] = c
                break
    return present

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
            c = cmap.get(a.lower())
            if c: return c
        return None

    player_col  = col("Player","player","PLAYER")
    team_col    = col("Team","team","TEAM")
    opp_col     = col("Opp","Opponent","opp","OPP")
    minutes_col = col("Minutes","Min","mins","minutes","MIN")
    if not all([player_col, team_col, opp_col, minutes_col]):
        return jsonify(ok=False, error="CSV must include Player, Team, Opp, Minutes"), 400

    stat_map = _find_present_stat_cols(df)
    if not stat_map:
        return jsonify(ok=False, error="no recognizable stat projection columns found"), 400

    use_cols = [player_col, team_col, opp_col, minutes_col] + list(stat_map.values())
    long = df[use_cols].copy()
    long = long.rename(columns={
        player_col:"Player", team_col:"Team", opp_col:"Opp", minutes_col:"Minutes", **{v:k for k,v in stat_map.items()}
    })

    long = long.melt(id_vars=["Player","Team","Opp","Minutes"],
                     value_vars=list(stat_map.keys()),
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
    return jsonify(_strip_dates({"ok": True, "model_id": model_id, "saved": out_path,
                                 "stats_trained": sorted(list(stat_map.keys()))}))

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

# daily_api.py
# Upload a daily ETR projections CSV, append to history, and RETRAIN projections
# Retrain uses ALL uploaded CSVs: player EMAs + opponent defensive multipliers.
# Artifacts written to: data/artifacts/projections_latest.csv

from __future__ import annotations
import os, io, json, re, traceback
from datetime import datetime
from pathlib import Path
from typing import List
import pandas as pd
from flask import Blueprint, request, jsonify, send_file

bp = Blueprint("daily_api", __name__)

# --------- CONFIG ----------
DATA_DIR = Path("data")
ART_DIR = DATA_DIR / "artifacts"
HIST_CSV = DATA_DIR / "etr_history.csv"
ART_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Blend weights (adjust if you like)
W_ETR = 0.60      # weight on latest uploaded ETR value
W_CAL = 0.40      # weight on calibrated value (EMA * opp_adj)
EMA_HALFLIFE = 10 # days; recency emphasis for EMA

# Required columns (we'll normalize aliases)
REQ = {
    "Player": ["player", "name"],
    "Team": ["team"],
    "Opp": ["opp", "opponent"],
    "Minutes": ["minutes", "min", "mins"],
    "PTS": ["pts", "points"],
    "REB": ["reb", "rebs"],
    "AST": ["ast", "assists"],
    "3PM": ["3pm", "three_pm", "3pt_made", "3pt"],
    "STL": ["stl", "steals"],
    "BLK": ["blk", "blocks"],
    "TO":  ["to", "tov", "turnovers"],
    "PRA": ["pra"],
}

STAT_COLS = ["PTS","REB","AST","3PM","STL","BLK","TO","PRA"]

def _canonicalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {}
    lower = {c.lower(): c for c in df.columns}
    for canon, aliases in REQ.items():
        found = None
        for a in [canon] + aliases:
            if a.lower() in lower:
                found = lower[a.lower()]
                break
        if found is None:
            # allow missing non-core stats; core id columns must exist
            if canon in ["Player","Team","Opp"]:
                raise ValueError(f"Missing required column: {canon} (aliases: {aliases})")
            else:
                continue
        colmap[found] = canon
    out = df.rename(columns=colmap).copy()
    # Ensure stat columns present (fill if missing)
    for s in STAT_COLS:
        if s not in out.columns:
            out[s] = pd.NA
    # Strip names/teams/opps
    for c in ["Player","Team","Opp"]:
        if c in out.columns:
            out[c] = out[c].astype(str).str.strip()
    return out

def _parse_date_str(s: str) -> str:
    # Expect YYYY-MM-DD; accept common alternates
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m-%d-%Y","%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    # final attempt: today
    return datetime.now().strftime("%Y-%m-%d")

def _append_history(df_day: pd.DataFrame, day: str) -> None:
    df_day = df_day.copy()
    df_day["Date"] = day
    # Keep only canonical/order
    keep = ["Date","Player","Team","Opp","Minutes"] + STAT_COLS
    df_day = df_day[[c for c in keep if c in df_day.columns]]
    if HIST_CSV.exists():
        df_prev = pd.read_csv(HIST_CSV)
        df_all = pd.concat([df_prev, df_day], ignore_index=True)
    else:
        df_all = df_day
    # de-dup within (Date, Player) keeping last
    df_all = (df_all
              .sort_values(["Date","Player"])
              .drop_duplicates(["Date","Player"], keep="last"))
    df_all.to_csv(HIST_CSV, index=False)

def _exponential_weights(dates: pd.Series) -> pd.Series:
    # convert Date -> integer day index (0 oldest … n-1 newest)
    d = pd.to_datetime(dates)
    ranks = d.rank(method="dense").astype(int)
    # newer date => bigger rank
    # convert halflife to decay per rank step
    # weight = 0.5 ** ((max_rank - rank)/halflife)
    maxr = ranks.max()
    decay = (0.5) ** ((maxr - ranks) / EMA_HALFLIFE)
    return decay / decay.sum()

def _train_calibrations(df_hist: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Build:
       - player EMA per stat (Player -> stat -> value)
       - opponent defensive multipliers per stat (Opp -> stat -> multiplier)
    """
    df = df_hist.copy()
    df = df.dropna(subset=["Player"])
    df["Date"] = pd.to_datetime(df["Date"])

    # Player EMA
    player_ema_rows = []
    for stat in STAT_COLS:
        if stat not in df.columns: continue
        sub = df[["Date","Player",stat]].dropna(subset=[stat]).copy()
        if sub.empty: 
            continue
        # weights by date
        sub["w"] = _exponential_weights(sub["Date"])
        ema = sub.groupby("Player").apply(lambda g: (g[stat] * g["w"]).sum()).reset_index(name=stat)
        ema["stat"] = stat
        player_ema_rows.append(ema[["Player","stat",stat]])
    player_ema = pd.DataFrame(columns=["Player","stat"]+STAT_COLS)
    if player_ema_rows:
        player_ema = pd.concat(player_ema_rows, ignore_index=True)
    # pivot to wide: Player rows, stat columns
    if not player_ema.empty:
        player_ema_wide = player_ema.pivot(index="Player", columns="stat", values=player_ema.columns[-1]).reset_index().rename_axis(None, axis=1)
    else:
        player_ema_wide = pd.DataFrame(columns=["Player"]+STAT_COLS)

    # Opponent multipliers: for each stat, how “hard” is Opp relative to league average projection level?
    # We use within-history ratios: player value vs league mean that day, aggregated by Opp.
    opp_rows = []
    for stat in STAT_COLS:
        sub = df[["Date","Opp",stat]].dropna(subset=[stat]).copy()
        if sub.empty: 
            continue
        # compute day-level mean, then ratio = value / day_mean
        day_mean = sub.groupby("Date")[stat].transform("mean")
        sub["ratio"] = sub[stat] / day_mean.replace(0, 1e-9)
        # recency weight
        sub["w"] = _exponential_weights(sub["Date"])
        opp_mult = sub.groupby("Opp").apply(lambda g: (g["ratio"] * g["w"]).sum()).reset_index(name=stat)
        opp_mult["stat"] = stat
        opp_rows.append(opp_mult[["Opp","stat",stat]])
    if opp_rows:
        opp_mult_df = pd.concat(opp_rows, ignore_index=True)
        opp_mult_wide = opp_mult_df.pivot(index="Opp", columns="stat", values=opp_mult_df.columns[-1]).reset_index().rename_axis(None, axis=1)
        # normalize each stat so league avg = 1.0
        for stat in STAT_COLS:
            if stat in opp_mult_wide.columns:
                m = opp_mult_wide[stat].mean()
                if pd.notna(m) and m != 0:
                    opp_mult_wide[stat] = opp_mult_wide[stat] / m
    else:
        opp_mult_wide = pd.DataFrame(columns=["Opp"]+STAT_COLS)

    # summary
    summary = {
        "rows_in_history": int(len(df)),
        "distinct_players": int(df["Player"].nunique()),
        "distinct_dates": int(df["Date"].nunique()),
        "ema_halflife_days": EMA_HALFLIFE,
        "blend": {"W_ETR": W_ETR, "W_CAL": W_CAL},
    }
    return player_ema_wide, opp_mult_wide, summary

def _rebuild_latest_projections(df_hist: pd.DataFrame) -> pd.DataFrame:
    # Take the most recent date in history as "current slate" to project
    latest_date = pd.to_datetime(df_hist["Date"]).max()
    today_df = df_hist[pd.to_datetime(df_hist["Date"]) == latest_date].copy()

    player_ema, opp_mult, _ = _train_calibrations(df_hist)

    # Merge calibrations
    base = today_df.merge(player_ema, on="Player", how="left", suffixes=("","_EMA"))
    base = base.merge(opp_mult, on="Opp", how="left", suffixes=("","_OPP"))

    # For each stat: calibrated = EMA * opp_mult (fallbacks → latest ETR if missing)
    out = base.copy()
    for stat in STAT_COLS:
        ema_col = stat  # from player_ema wide pivot, the stat name is the column
        opp_col = stat  # from opp_mult wide pivot, same column name
        ema_vals = out[f"{ema_col}"].where(out[f"{ema_col}"].notna(), out[stat])
        opp_vals = out[f"{opp_col}"].where(out[f"{opp_col}"].notna(), 1.0)
        cal = ema_vals * opp_vals
        out[f"{stat}_CAL"] = cal
        out[f"{stat}_FINAL"] = (W_ETR * out[stat].astype(float)) + (W_CAL * cal.astype(float))

    # Output tidy frame
    keep = ["Date","Player","Team","Opp","Minutes"] + [f"{s}_FINAL" for s in STAT_COLS]
    out = out[keep].rename(columns={f"{s}_FINAL": s for s in STAT_COLS})
    out = out.sort_values(["Team","Player"]).reset_index(drop=True)
    out["Date"] = out["Date"].astype(str)
    return out

# ---------------- ROUTES ----------------

@bp.route("/api/daily/upload", methods=["POST"])
def upload_and_retrain():
    try:
        # 1) Parse input
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "No file part 'file'"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"ok": False, "error": "No selected file"}), 400
        date_str = (request.form.get("date") or "").strip()
        day = _parse_date_str(date_str) if date_str else datetime.now().strftime("%Y-%m-%d")

        # 2) Read CSV
        raw = pd.read_csv(io.BytesIO(f.read()))
        df = _canonicalize_cols(raw)

        # 3) Append to history
        _append_history(df, day)

        # 4) Retrain using ALL history
        df_hist = pd.read_csv(HIST_CSV)
        latest = _rebuild_latest_projections(df_hist)

        # 5) Write artifacts
        ART_DIR.mkdir(parents=True, exist_ok=True)
        latest_path = ART_DIR / "projections_latest.csv"
        latest.to_csv(latest_path, index=False)

        # calibration summary
        _, _, summary = _train_calibrations(df_hist)
        (ART_DIR / "calibration_summary.json").write_text(json.dumps(summary, indent=2))

        return jsonify({
            "ok": True,
            "date": day,
            "rows_uploaded": len(df),
            "history_rows": int(len(df_hist)),
            "artifacts": {
                "projections_latest_csv": str(latest_path),
                "calibration_summary_json": str(ART_DIR / "calibration_summary.json"),
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

@bp.route("/api/daily/library", methods=["GET"])
def list_library():
    if not HIST_CSV.exists():
        return jsonify({"ok": True, "items": []})
    df = pd.read_csv(HIST_CSV)
    df["Date"] = pd.to_datetime(df["Date"])
    sizes = (df.groupby("Date").size().reset_index(name="rows")
             .sort_values("Date", ascending=False))
    items = []
    for _, r in sizes.iterrows():
        items.append({
            "date": r["Date"].strftime("%Y-%m-%d"),
            "rows": int(r["rows"])
        })
    return jsonify({"ok": True, "items": items})

@bp.route("/api/daily/download/<date_str>", methods=["GET"])
def download_daily(date_str: str):
    if not HIST_CSV.exists():
        return jsonify({"ok": False, "error": "No history"}), 404
    df = pd.read_csv(HIST_CSV)
    out = df[df["Date"] == date_str]
    if out.empty:
        return jsonify({"ok": False, "error": f"No entries for date {date_str}"}), 404
    bio = io.BytesIO()
    out.to_csv(bio, index=False)
    bio.seek(0)
    return send_file(bio, mimetype="text/csv", as_attachment=True, download_name=f"etr_{date_str}.csv")

@bp.route("/api/daily/projections/latest.csv", methods=["GET"])
def projections_latest_csv():
    p = ART_DIR / "projections_latest.csv"
    if not p.exists():
        return jsonify({"ok": False, "error": "No projections artifact yet"}), 404
    return send_file(str(p), mimetype="text/csv", as_attachment=True, download_name="projections_latest.csv")

# Alias for compatibility with app.py
daily_bp = bp


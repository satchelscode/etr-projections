# daily_api.py
# Upload daily ETR CSV, append to persistent history, retrain using ALL history,
# and expose a library list compatible with the existing front-end.

from __future__ import annotations
import os, io, json, traceback
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import pandas as pd
from flask import Blueprint, request, jsonify, send_file, url_for

bp = Blueprint("daily_api", __name__)

# --------- CONFIG (supports Render Persistent Disk) ----------
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
ART_DIR = DATA_DIR / "artifacts"
HIST_CSV = DATA_DIR / "etr_history.csv"
ART_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Blend weights
W_ETR = 0.60
W_CAL = 0.40
EMA_HALFLIFE = 10

REQ = {
    "Player": ["player","name"],
    "Team": ["team"],
    "Opp": ["opp","opponent"],
    "Minutes": ["minutes","min","mins"],
    "PTS": ["pts","points"],
    "REB": ["reb","rebs"],
    "AST": ["ast","assists"],
    "3PM": ["3pm","three_pm","3pt_made","3pt"],
    "STL": ["stl","steals"],
    "BLK": ["blk","blocks"],
    "TO":  ["to","tov","turnovers"],
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
            if canon in ["Player","Team","Opp"]:
                raise ValueError(f"Missing required column: {canon} (aliases: {aliases})")
            else:
                continue
        colmap[found] = canon
    out = df.rename(columns=colmap).copy()
    for s in STAT_COLS:
        if s not in out.columns:
            out[s] = pd.NA
    for c in ["Player","Team","Opp"]:
        if c in out.columns:
            out[c] = out[c].astype(str).str.strip()
    return out

def _parse_date_str(s: str) -> str:
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m-%d-%Y","%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return datetime.now().strftime("%Y-%m-%d")

def _append_history(df_day: pd.DataFrame, day: str) -> None:
    df_day = df_day.copy()
    df_day["Date"] = day
    keep = ["Date","Player","Team","Opp","Minutes"] + STAT_COLS
    df_day = df_day[[c for c in keep if c in df_day.columns]]
    if HIST_CSV.exists():
        df_prev = pd.read_csv(HIST_CSV)
        df_all = pd.concat([df_prev, df_day], ignore_index=True)
    else:
        df_all = df_day
    df_all = df_all.sort_values(["Date","Player"]).drop_duplicates(["Date","Player"], keep="last")
    # Ensure directory exists (helpful if env changed)
    HIST_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_all.to_csv(HIST_CSV, index=False)

def _exponential_weights(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates)
    ranks = d.rank(method="dense").astype(int)
    maxr = ranks.max()
    decay = (0.5) ** ((maxr - ranks) / EMA_HALFLIFE)
    return decay / decay.sum()

def _train_calibrations(df_hist: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
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
        sub["w"] = _exponential_weights(sub["Date"])
        ema = sub.groupby("Player").apply(lambda g: (g[stat] * g["w"]).sum()).reset_index(name=stat)
        ema["stat"] = stat
        player_ema_rows.append(ema[["Player","stat",stat]])
    if player_ema_rows:
        player_ema = pd.concat(player_ema_rows, ignore_index=True)
        player_ema_wide = player_ema.pivot(index="Player", columns="stat", values=player_ema.columns[-1]).reset_index().rename_axis(None, axis=1)
    else:
        player_ema_wide = pd.DataFrame(columns=["Player"]+STAT_COLS)

    # Opponent multipliers
    opp_rows = []
    for stat in STAT_COLS:
        sub = df[["Date","Opp",stat]].dropna(subset=[stat]).copy()
        if sub.empty: 
            continue
        day_mean = sub.groupby("Date")[stat].transform("mean")
        sub["ratio"] = sub[stat] / day_mean.replace(0, 1e-9)
        sub["w"] = _exponential_weights(sub["Date"])
        opp_mult = sub.groupby("Opp").apply(lambda g: (g["ratio"] * g["w"]).sum()).reset_index(name=stat)
        opp_mult["stat"] = stat
        opp_rows.append(opp_mult[["Opp","stat",stat]])
    if opp_rows:
        opp_mult_df = pd.concat(opp_rows, ignore_index=True)
        opp_mult_wide = opp_mult_df.pivot(index="Opp", columns="stat", values=opp_mult_df.columns[-1]).reset_index().rename_axis(None, axis=1)
        for stat in STAT_COLS:
            if stat in opp_mult_wide.columns:
                m = opp_mult_wide[stat].mean()
                if pd.notna(m) and m != 0:
                    opp_mult_wide[stat] = opp_mult_wide[stat] / m
    else:
        opp_mult_wide = pd.DataFrame(columns=["Opp"]+STAT_COLS)

    summary = {
        "rows_in_history": int(len(df)),
        "distinct_players": int(df["Player"].nunique()),
        "distinct_dates": int(df["Date"].nunique()),
        "ema_halflife_days": EMA_HALFLIFE,
        "blend": {"W_ETR": W_ETR, "W_CAL": W_CAL},
    }
    return player_ema_wide, opp_mult_wide, summary

def _rebuild_latest_projections(df_hist: pd.DataFrame) -> pd.DataFrame:
    latest_date = pd.to_datetime(df_hist["Date"]).max()
    today_df = df_hist[pd.to_datetime(df_hist["Date"]) == latest_date].copy()

    player_ema, opp_mult, _ = _train_calibrations(df_hist)
    base = today_df.merge(player_ema, on="Player", how="left", suffixes=("","_EMA"))
    base = base.merge(opp_mult, on="Opp", how="left", suffixes=("","_OPP"))

    out = base.copy()
    for stat in STAT_COLS:
        ema_vals = out.get(stat)  # from player_ema pivot
        opp_vals = out.get(stat)  # from opp_mult pivot
        ema_vals = ema_vals.where(ema_vals.notna(), out[stat])
        opp_vals = opp_vals.where(opp_vals.notna(), 1.0)
        cal = ema_vals * opp_vals
        out[f"{stat}_CAL"] = cal
        out[f"{stat}_FINAL"] = (W_ETR * out[stat].astype(float)) + (W_CAL * cal.astype(float))

    keep = ["Date","Player","Team","Opp","Minutes"] + [f"{s}_FINAL" for s in STAT_COLS]
    out = out[keep].rename(columns={f"{s}_FINAL": s for s in STAT_COLS})
    out = out.sort_values(["Team","Player"]).reset_index(drop=True)
    out["Date"] = out["Date"].astype(str)
    return out

@bp.route("/api/daily/upload", methods=["POST"])
def upload_and_retrain():
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "No file part 'file'"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"ok": False, "error": "No selected file"}), 400
        date_str = (request.form.get("date") or "").strip()
        day = _parse_date_str(date_str) if date_str else datetime.now().strftime("%Y-%m-%d")

        raw = pd.read_csv(io.BytesIO(f.read()))
        df = _canonicalize_cols(raw)

        _append_history(df, day)

        df_hist = pd.read_csv(HIST_CSV)
        latest = _rebuild_latest_projections(df_hist)

        ART_DIR.mkdir(parents=True, exist_ok=True)
        latest_path = ART_DIR / "projections_latest.csv"
        latest.to_csv(latest_path, index=False)

        _, _, summary = _train_calibrations(df_hist)
        (ART_DIR / "calibration_summary.json").write_text(json.dumps(summary, indent=2))

        return jsonify({
            "ok": True,
            "date": day,
            "rows_uploaded": int(len(df)),
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
    try:
        if not HIST_CSV.exists():
            # Return empty but valid shape so the UI doesn't error
            return jsonify({"ok": True, "items": []})
        df = pd.read_csv(HIST_CSV)
        if df.empty or "Date" not in df.columns:
            return jsonify({"ok": True, "items": []})
        df["Date"] = pd.to_datetime(df["Date"])
        grp = df.groupby("Date")
        items = []
        for d, g in grp:
            # Estimate size as CSV bytes / KB for the single-day slice
            bio = io.BytesIO()
            g.to_csv(bio, index=False)
            kb = round(len(bio.getvalue()) / 1024, 1)
            date_str = d.strftime("%Y-%m-%d")
            items.append({
                "date": date_str,
                "size_kb": kb,
                "download_url": url_for("daily_api.download_daily", date_str=date_str)
            })
        # Most recent first
        items.sort(key=lambda x: x["date"], reverse=True)
        return jsonify({"ok": True, "items": items})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

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

# Backwards-compat alias expected by app.py
daily_bp = bp

# daily_api.py
# Upload a daily ETR projections CSV, append to history (CSV), retrain artifacts.
# Robust column resolver (Minutes OR Min, plus common aliases). No parquet deps.

from __future__ import annotations
import json, re, traceback
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, request, jsonify
import pandas as pd

daily_bp = Blueprint("daily", __name__)

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
RAW  = DATA / "raw"
MASTER = DATA / "master.csv"      # CSV (no pyarrow/fastparquet)
ART  = REPO / "artifacts"

RAW.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
ART.mkdir(parents=True, exist_ok=True)

STATS = [
    ("Points","PTS"),
    ("Rebounds","REB"),
    ("Assists","AST"),
    ("Three Pointers Made","3PM"),
    ("Steals","STL"),
    ("Blocks","BLK"),
    ("Turnovers","TO"),
    ("PRA","PRA"),
]

def _norm(s: str) -> str:
    # normalize header names: lowercase, remove non-alnum
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())

def _resolve_col(df: pd.DataFrame, target: str, aliases: list[str]) -> str:
    want = _norm(target)
    cols_norm = { _norm(c): c for c in df.columns }
    if want in cols_norm:
        return cols_norm[want]
    for a in aliases:
        na = _norm(a)
        if na in cols_norm:
            return cols_norm[na]
    raise ValueError(f"Missing required column: {target}. Found columns: {list(df.columns)}")

def _norm_df(df: pd.DataFrame) -> pd.DataFrame:
    minutes_col = _resolve_col(df, "Minutes", ["Min", "mins", "MINS", "Minute", "MIN"])
    req_map = {
        "Player":  _resolve_col(df, "Player", []),
        "Team":    _resolve_col(df, "Team", []),
        "Opp":     _resolve_col(df, "Opp",  ["Opponent"]),
        "Minutes": minutes_col,
        "PTS":     _resolve_col(df, "PTS",  []),
        "REB":     _resolve_col(df, "REB",  []),
        "AST":     _resolve_col(df, "AST",  []),
        "3PM":     _resolve_col(df, "3PM",  ["3pt", "3p", "threes", "three pointers made", "three_pointers_made"]),
        "STL":     _resolve_col(df, "STL",  []),
        "BLK":     _resolve_col(df, "BLK",  []),
        "TO":      _resolve_col(df, "TO",   ["TOV", "Turnovers"]),
        "PRA":     _resolve_col(df, "PRA",  []),
    }
    g = pd.DataFrame({k: df[v] for k, v in req_map.items()})
    # normalize values
    g["Player"] = g["Player"].astype(str).str.strip()
    g["Team"]   = g["Team"].astype(str).str.upper().str.strip()
    g["Opp"]    = g["Opp"].astype(str).str.upper().str.strip()
    for k in ["Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA"]:
        g[k] = pd.to_numeric(g[k], errors="coerce")
    g = g[(g["Minutes"] > 0) & g["Player"].ne("")]
    return g

def _train_full_history(df: pd.DataFrame, min_minutes: float = 6.0):
    df = df.copy()
    df["Minutes"] = pd.to_numeric(df["Minutes"], errors="coerce")
    df = df[(df["Minutes"] > 0) & df["Player"].ne("")]
    # ensure datetime exists
    if "Date" not in df.columns:
        raise ValueError("History has no Date column after merge.")
    df["Date"] = pd.to_datetime(df["Date"])

    for stat_name, stat_col in STATS:
        sub = df[df["Minutes"] >= min_minutes].copy()
        base = stat_name.replace(" ", "_").lower()

        if sub.empty:
            pd.DataFrame({"Player": [], "rate_per_min": []}).to_csv(ART / f"model_player_rates_{base}.csv", index=False)
            pd.DataFrame({"Opponent": [], "opp_adj": []}).to_csv(ART / f"model_opp_adj_{base}.csv", index=False)
            (ART / f"model_meta_{base}.json").write_text(
                json.dumps({"intercept": 0.0, "rows": 0, "as_of": datetime.now(timezone.utc).isoformat()}, indent=2),
                encoding="utf-8",
            )
            continue

        grp_p = sub.groupby("Player", as_index=False).agg(
            stat_sum=(stat_col, "sum"),
            min_sum=("Minutes","sum")
        )
        grp_p["rate_per_min"] = grp_p["stat_sum"] / grp_p["min_sum"]
        rates = grp_p[["Player","rate_per_min"]].sort_values("Player")

        merged = sub.merge(rates, on="Player", how="left")
        merged["pred0"]  = merged["rate_per_min"] * merged["Minutes"]
        merged["resid0"] = merged[stat_col] - merged["pred0"]
        intercept = float(merged["resid0"].mean())

        merged["resid1"] = merged["resid0"] - intercept
        opp_adj = (
            merged.groupby("Opp", as_index=False)["resid1"]
            .mean()
            .rename(columns={"Opp":"Opponent","resid1":"opp_adj"})
            .sort_values("Opponent")
        )

        rates.to_csv(ART / f"model_player_rates_{base}.csv", index=False)
        opp_adj.to_csv(ART / f"model_opp_adj_{base}.csv", index=False)
        (ART / f"model_meta_{base}.json").write_text(
            json.dumps({"intercept": round(intercept,6), "rows": int(len(sub)), "as_of": datetime.now(timezone.utc).isoformat()}, indent=2),
            encoding="utf-8",
        )

@daily_bp.get("/api/daily/status")
def daily_status():
    size = MASTER.stat().st_size if MASTER.exists() else 0
    return jsonify({"ok": True, "has_master": MASTER.exists(), "master_bytes": size})

@daily_bp.post("/api/daily/upload")
def daily_upload():
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "Missing file"}), 400
        date_str = (request.form.get("date") or "").strip() or datetime.now().strftime("%Y-%m-%d")

        f = request.files["file"]
        try:
            df = pd.read_csv(f)
            df = _norm_df(df)
        except Exception as e:
            return jsonify({"ok": False, "error": f"CSV parse error: {e}"}), 400

        df["Date"] = pd.to_datetime(date_str).normalize()

        # save raw
        out_raw = RAW / f"{date_str}.csv"
        df.to_csv(out_raw, index=False)

        # append to master CSV
        if MASTER.exists():
            m = pd.read_csv(MASTER)
            # make sure expected columns exist when merging
            for col in ["Player","Team","Opp","Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA","Date"]:
                if col not in m.columns:
                    m[col] = pd.Series(dtype=df[col].dtype if col in df.columns else "float64")
            m = pd.concat([m, df], ignore_index=True)
        else:
            m = df.copy()

        # de-dup by (Date, Player, Opp)
        m["Date"] = pd.to_datetime(m["Date"])
        m = m.sort_values(["Date","Player","Opp"]).drop_duplicates(subset=["Date","Player","Opp"], keep="last")
        m.to_csv(MASTER, index=False)

        # retrain
        _train_full_history(m)

        return jsonify({
            "ok": True,
            "date": date_str,
            "added_rows": int(len(df)),
            "master_rows": int(len(m)),
            "message": f"Uploaded {len(df)} rows for {date_str} and retrained artifacts."
        })

    except Exception as e:
        # Return JSON error with traceback snippet for debugging
        tb = traceback.format_exc(limit=2)
        return jsonify({"ok": False, "error": f"Internal error: {e}", "trace": tb}), 500

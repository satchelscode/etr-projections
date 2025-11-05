#!/usr/bin/env python3
"""
Train artifacts from historical ETR projections (data/master.parquet or data/raw/*.csv).

Outputs (in artifacts/):
  - model_player_rates_{stat}.csv          (Player, rate_per_min)
  - model_opp_adj_{stat}.csv               (Opponent, opp_adj)
  - model_meta_{stat}.json                 ({"intercept": float, "as_of": ISO, "rows": int, "window_days": int|None})

Default: use the FULL history. You can limit to a rolling window via --window-days.

Usage:
  python train_from_history.py --window-days 45 --min-minutes 6
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import json
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
ART  = REPO / "artifacts"
MASTER = DATA / "master.parquet"
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

def load_history():
    if MASTER.exists():
        df = pd.read_parquet(MASTER)
    else:
        raws = sorted((DATA / "raw").glob("*.csv"))
        if not raws:
            raise FileNotFoundError("No data found: expected data/master.parquet or data/raw/*.csv")
        parts = [pd.read_csv(p) for p in raws]
        df = pd.concat(parts, ignore_index=True)
    # Normalize types
    df["Date"] = pd.to_datetime(df["Date"])
    df["Player"] = df["Player"].astype(str).str.strip()
    df["Team"]   = df["Team"].astype(str).str.strip().str.upper()
    df["Opp"]    = df["Opp"].astype(str).str.strip().str.upper()
    for k in ["Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA"]:
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df[(df["Minutes"] > 0) & df["Player"].ne("")]
    return df

def rolling_filter(df: pd.DataFrame, window_days: int|None):
    if not window_days:
        return df
    max_day = df["Date"].max()
    cutoff = max_day - pd.Timedelta(days=window_days)
    return df[df["Date"] >= cutoff].copy()

def train_stat(df: pd.DataFrame, stat_name: str, stat_col: str, min_minutes: float):
    """
    Simple, robust model:
      - Player rate per minute = sum(stat)/sum(minutes) across history (weighted by minutes)
      - Intercept = mean(stat - minutes*rate) over all rows
      - Opp adj   = mean(stat - (intercept + minutes*rate)) grouped by Opp

    Optional: we drop rows where Minutes < min_minutes to reduce noise.
    """
    sub = df[df["Minutes"] >= min_minutes].copy()
    if sub.empty:
        # Return empty artifacts
        return (
            pd.DataFrame({"Player": [], "rate_per_min": []}),
            pd.DataFrame({"Opponent": [], "opp_adj": []}),
            {"intercept": 0.0, "as_of": datetime.now(timezone.utc).isoformat(), "rows": 0, "window_days": None}
        )

    # Player rates (weighted by minutes)
    grp_p = sub.groupby("Player", as_index=False).agg(
        stat_sum=(stat_col, "sum"),
        min_sum=("Minutes", "sum")
    )
    grp_p["rate_per_min"] = grp_p["stat_sum"] / grp_p["min_sum"]
    rates = grp_p[["Player","rate_per_min"]].sort_values("Player")

    # Intercept
    merged = sub.merge(rates, on="Player", how="left")
    merged["pred0"] = merged["rate_per_min"] * merged["Minutes"]
    merged["resid0"] = merged[stat_col] - merged["pred0"]
    intercept = float(merged["resid0"].mean())

    # Opponent adjustment
    merged["resid1"] = merged["resid0"] - intercept
    grp_o = merged.groupby("Opp", as_index=False)["resid1"].mean().rename(columns={"Opp":"Opponent","resid1":"opp_adj"})
    opp_adj = grp_o.sort_values("Opponent")

    meta = {
        "intercept": round(intercept, 6),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(sub)),
    }
    return rates, opp_adj, meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=None, help="If set, only use last N days of data.")
    ap.add_argument("--min-minutes", type=float, default=6.0, help="Drop rows with fewer than this many minutes.")
    args = ap.parse_args()

    df = load_history()
    dfw = rolling_filter(df, args.window_days)

    for stat_name, stat_col in STATS:
        rates, opp_adj, meta = train_stat(dfw, stat_name, stat_col, args.min_minutes)
        base = stat_name.replace(" ", "_").lower()

        rates.to_csv(ART / f"model_player_rates_{base}.csv", index=False)
        opp_adj.to_csv(ART / f"model_opp_adj_{base}.csv", index=False)

        meta["window_days"] = args.window_days
        (ART / f"model_meta_{base}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"[OK] {stat_name}: {len(rates)} players, {len(opp_adj)} opponents, intercept={meta['intercept']}")

if __name__ == "__main__":
    main()

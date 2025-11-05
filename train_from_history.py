#!/usr/bin/env python3
"""
Train artifacts from historical ETR projections (data/master.parquet or data/raw/*.csv).
Accepts Minutes/Min during raw CSV fallback path, but primary source is master.parquet.

Outputs:
  artifacts/model_player_rates_{stat}.csv
  artifacts/model_opp_adj_{stat}.csv
  artifacts/model_meta_{stat}.json

Usage:
  python train_from_history.py --min-minutes 6
"""

import argparse, json
from pathlib import Path
import pandas as pd
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

def resolve_col(df: pd.DataFrame, target: str, aliases: list[str]) -> str:
    want = target.lower()
    for c in df.columns:
        if c.strip().lower() == want:
            return c
    for a in aliases:
        a_norm = a.lower()
        for c in df.columns:
            if c.strip().lower() == a_norm:
                return c
    raise ValueError(f"Missing required column: {target}")

def load_history() -> pd.DataFrame:
    if MASTER.exists():
        df = pd.read_parquet(MASTER)
    else:
        raws = sorted((DATA / "raw").glob("*.csv"))
        if not raws:
            raise FileNotFoundError("No data found: expected data/master.parquet or data/raw/*.csv")
        parts = []
        for p in raws:
            tmp = pd.read_csv(p)
            # normalize minimal schema for fallback
            minutes_col = resolve_col(tmp, "Minutes", ["Min","mins","MINS"])
            colmap = {
                "Player": resolve_col(tmp, "Player", []),
                "Team":   resolve_col(tmp, "Team", []),
                "Opp":    resolve_col(tmp, "Opp", ["Opponent"]),
                "Minutes": minutes_col,
                "PTS": resolve_col(tmp, "PTS", []),
                "REB": resolve_col(tmp, "REB", []),
                "AST": resolve_col(tmp, "AST", []),
                "3PM": resolve_col(tmp, "3PM", ["3pt","3p","threes","three_pointers_made"]),
                "STL": resolve_col(tmp, "STL", []),
                "BLK": resolve_col(tmp, "BLK", []),
                "TO":  resolve_col(tmp, "TO",  ["TOV","Turnovers"]),
                "PRA": resolve_col(tmp, "PRA", []),
            }
            tmp = pd.DataFrame({k: tmp[v] for k, v in colmap.items()})
            tmp["Date"] = pd.to_datetime(p.stem, errors="coerce")  # try infer date from filename
            parts.append(tmp)
        df = pd.concat(parts, ignore_index=True)

    df["Date"] = pd.to_datetime(df["Date"])
    df["Player"] = df["Player"].astype(str).str.strip()
    df["Team"]   = df["Team"].astype(str).str.upper().str.strip()
    df["Opp"]    = df["Opp"].astype(str).str.upper().str.strip()
    for k in ["Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA"]:
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df[(df["Minutes"] > 0) & df["Player"].ne("")]
    return df

def train_stat(df: pd.DataFrame, stat_name: str, stat_col: str, min_minutes: float):
    sub = df[df["Minutes"] >= min_minutes].copy()
    base = stat_name.replace(" ", "_").lower()

    if sub.empty:
        return (
            pd.DataFrame({"Player": [], "rate_per_min": []}),
            pd.DataFrame({"Opponent": [], "opp_adj": []}),
            {"intercept": 0.0, "rows": 0, "as_of": datetime.now(timezone.utc).isoformat()}
        )

    grp_p = sub.groupby("Player", as_index=False).agg(
        stat_sum=(stat_col, "sum"),
        min_sum=("Minutes", "sum")
    )
    grp_p["rate_per_min"] = grp_p["stat_sum"] / grp_p["min_sum"]
    rates = grp_p[["Player","rate_per_min"]].sort_values("Player")

    merged = sub.merge(rates, on="Player", how="left")
    merged["pred0"]  = merged["rate_per_min"] * merged["Minutes"]
    merged["resid0"] = merged[stat_col] - merged["pred0"]
    intercept = float(merged["resid0"].mean())

    merged["resid1"] = merged["resid0"] - intercept
    opp_adj = merged.groupby("Opp", as_index=False)["resid1"].mean().rename(columns={"Opp":"Opponent","resid1":"opp_adj"}).sort_values("Opponent")

    meta = {"intercept": round(intercept,6), "rows": int(len(sub)), "as_of": datetime.now(timezone.utc).isoformat()}
    return rates, opp_adj, meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-minutes", type=float, default=6.0)
    args = ap.parse_args()

    df = load_history()

    for stat_name, stat_col in STATS:
        rates, opp_adj, meta = train_stat(df, stat_name, stat_col, args.min_minutes)
        base = stat_name.replace(" ", "_").lower()
        ART.mkdir(parents=True, exist_ok=True)
        rates.to_csv(ART / f"model_player_rates_{base}.csv", index=False)
        opp_adj.to_csv(ART / f"model_opp_adj_{base}.csv", index=False)
        (ART / f"model_meta_{base}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[OK] {stat_name}: players={len(rates)}, opps={len(opp_adj)}, intercept={meta['intercept']}")

if __name__ == "__main__":
    main()

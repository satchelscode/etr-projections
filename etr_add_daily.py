#!/usr/bin/env python3
"""
Append a daily ETR projections CSV into data/master.parquet and data/raw/YYYY-MM-DD.csv.
Accepts Minutes OR Min.

Usage:
  python etr_add_daily.py --csv /path/to/todays.csv --date 2025-11-05
"""

import argparse
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
RAW  = DATA / "raw"
MASTER = DATA / "master.parquet"
RAW.mkdir(parents=True, exist_ok=True)

NEEDED = ["Player","Team","Opp","Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA"]

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

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    minutes_col = resolve_col(df, "Minutes", ["Min", "mins", "MINS"])
    colmap = {
        "Player": resolve_col(df, "Player", []),
        "Team":   resolve_col(df, "Team", []),
        "Opp":    resolve_col(df, "Opp", ["Opponent"]),
        "Minutes": minutes_col,
        "PTS": resolve_col(df, "PTS", []),
        "REB": resolve_col(df, "REB", []),
        "AST": resolve_col(df, "AST", []),
        "3PM": resolve_col(df, "3PM", ["3pt", "3p", "threes", "three_pointers_made"]),
        "STL": resolve_col(df, "STL", []),
        "BLK": resolve_col(df, "BLK", []),
        "TO":  resolve_col(df, "TO",  ["TOV","Turnovers"]),
        "PRA": resolve_col(df, "PRA", []),
    }
    g = pd.DataFrame({k: df[v] for k, v in colmap.items()})
    g["Player"] = g["Player"].astype(str).str.strip()
    g["Team"]   = g["Team"].astype(str).str.upper().str.strip()
    g["Opp"]    = g["Opp"].astype(str).str.upper().str.strip()
    for k in ["Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA"]:
        g[k] = pd.to_numeric(g[k], errors="coerce")
    g = g[(g["Minutes"] > 0) & g["Player"].ne("")]
    return g

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (date of these projections)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    df = normalize_cols(df)
    df["Date"] = pd.to_datetime(args.date).normalize()

    out_raw = RAW / f"{args.date}.csv"
    df.to_csv(out_raw, index=False)

    if MASTER.exists():
        m = pd.read_parquet(MASTER)
        m = pd.concat([m, df], ignore_index=True)
    else:
        m = df.copy()

    m = m.sort_values(["Date","Player","Opp"])
    m = m.drop_duplicates(subset=["Date","Player","Opp"], keep="last")

    MASTER.parent.mkdir(parents=True, exist_ok=True)
    m.to_parquet(MASTER, index=False)
    print(f"[OK] Added {len(df)} rows for {args.date}. Master now: {len(m)} rows at {MASTER}")

if __name__ == "__main__":
    main()

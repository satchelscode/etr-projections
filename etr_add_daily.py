#!/usr/bin/env python3
"""
Append a daily ETR projections CSV into data/master.parquet and data/raw/YYYY-MM-DD.csv.

Usage:
  python etr_add_daily.py --csv /path/to/todays.csv --date 2025-11-05

Requirements:
  - CSV columns (case-insensitive ok): Player, Team, Opp, Minutes, PTS, REB, AST, 3PM, STL, BLK, TO, PRA
  - Minutes > 0 rows kept; others dropped.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
RAW  = DATA / "raw"
MASTER = DATA / "master.parquet"
RAW.mkdir(parents=True, exist_ok=True)

NEEDED = ["Player","Team","Opp","Minutes","PTS","REB","AST","3PM","STL","BLK","TO","PRA"]

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    m = {c.lower(): c for c in df.columns}
    out = {}
    for need in NEEDED:
        key = need.lower()
        found = None
        for c in df.columns:
            if c.strip().lower() == key:
                found = c
                break
        if found is None:
            raise ValueError(f"Missing required column: {need}")
        out[need] = df[found]
    g = pd.DataFrame(out)
    g["Player"] = g["Player"].astype(str).str.strip()
    g["Team"]   = g["Team"].astype(str).str.strip().str.upper()
    g["Opp"]    = g["Opp"].astype(str).str.strip().str.upper()
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

    # Save raw copy
    out_raw = RAW / f"{args.date}.csv"
    df.to_csv(out_raw, index=False)

    # Append/update master.parquet (dedupe on Date+Player+Opp)
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

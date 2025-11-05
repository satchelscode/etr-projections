#!/usr/bin/env python3
"""
Build players_master.csv (Player,Team) from your ETR daily CSVs.

It scans one or more input files/directories, finds CSVs that contain a Player
name column and a Team code column, aggregates the latest team per player, and
writes:
    artifacts/players_master.csv

Designed for your "NBA Full Stat Detail*.csv" files.
"""

import argparse
import sys
from pathlib import Path
import pandas as pd

# Candidate column names found in ETR-style files
PLAYER_COLS = ["Player", "PLAYER", "Name", "name", "player"]
TEAM_COLS = ["Team", "TEAM", "Tm", "tm", "team", "TEAM_CODE", "OppTeam"]

def find_col(cols, candidates):
    cols_lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None

def scan_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"[skip] {path} (read error: {e})")
        return pd.DataFrame(columns=["Player","Team"])
    if df.empty:
        return pd.DataFrame(columns=["Player","Team"])

    pcol = find_col(df.columns, PLAYER_COLS)
    tcol = find_col(df.columns, TEAM_COLS)
    if not pcol or not tcol:
        print(f"[skip] {path} (missing Player/Team columns)")
        return pd.DataFrame(columns=["Player","Team"])

    out = df[[pcol, tcol]].copy()
    out.columns = ["Player","Team"]
    out["Player"] = out["Player"].astype(str).str.strip()
    out["Team"] = out["Team"].astype(str).str.strip().str.upper()
    out = out[(out["Player"] != "") & (out["Team"] != "")]
    return out

def collect_sources(inputs):
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("**/*.csv")))
        elif p.suffix.lower() == ".csv" and p.exists():
            files.append(p)
        else:
            print(f"[warn] skipping non-existent or non-CSV: {p}")
    return files

def main():
    ap = argparse.ArgumentParser(
        description="Build artifacts/players_master.csv from ETR daily CSVs."
    )
    ap.add_argument(
        "inputs",
        nargs="+",
        help="CSV files or directories containing your ETR daily CSVs",
    )
    ap.add_argument(
        "--out",
        default="artifacts/players_master.csv",
        help="Output CSV path (default: artifacts/players_master.csv)",
    )
    args = ap.parse_args()

    files = collect_sources(args.inputs)
    if not files:
        print("No CSV files found. Provide at least one CSV or directory.")
        sys.exit(1)

    frames = []
    for f in files:
        df = scan_csv(f)
        if not df.empty:
            frames.append(df)

    if not frames:
        print("No usable rows found (no Player/Team columns detected).")
        sys.exit(2)

    all_df = pd.concat(frames, ignore_index=True)

    # Deduplicate to the latest occurrence per player (last seen team wins).
    # If you prefer majority vote across files, change this block.
    all_df = all_df.dropna(subset=["Player","Team"])
    # Normalize a few common stray values
    all_df["Team"] = (
        all_df["Team"]
        .str.upper()
        .str.replace("BRK", "BKN", regex=False)
        .str.replace("GS", "GSW", regex=False)
    )

    # Keep last seen entry per player
    master = all_df.groupby("Player", as_index=False).tail(1)

    # Basic clean of team code length (filter likely junk)
    master = master[master["Team"].str.len().between(2, 4)]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    master = master.sort_values(["Team","Player"]).reset_index(drop=True)
    master.to_csv(out_path, index=False)

    # Quick report
    by_team = master.groupby("Team")["Player"].count().sort_values(ascending=False)
    print(f"[ok] wrote {out_path} with {len(master)} players across {by_team.size} teams")
    print(by_team.to_string())

if __name__ == "__main__":
    main()

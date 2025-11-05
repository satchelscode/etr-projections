import glob
import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error

# -------------------- Paths --------------------
ART_DIR = Path("artifacts")
DATA_DIR = Path("data")
ART_DIR.mkdir(exist_ok=True)

# -------------------- Columns / Mappings --------------------
# Canonical columns we want to work with across daily files
CORE_COLS = [
    "Player", "PlayerID", "Position", "Team", "Opponent", "Minutes",
    "Points", "Assists", "Rebounds", "Three Pointers Made",
    "Turnovers", "Steals", "Blocks", "PRA", "Scenario"
]

# Common header variants seen in different dumps
RENAME_MAP = {
    "Opp": "Opponent",
    "MIN": "Minutes",
    "PTS": "Points",
    "AST": "Assists",
    "REB": "Rebounds",
    "3PM": "Three Pointers Made",
    "3pt": "Three Pointers Made",
    "3Pt": "Three Pointers Made",
    "Threes": "Three Pointers Made",
    "STL": "Steals",
    "BLK": "Blocks",
    "PRA ": "PRA",
    "PRA  ": "PRA",
    "Scenario ": "Scenario",
}

# Stats we will train per-minute rates + opponent adjustments for
STATS = [
    "Points", "Assists", "Rebounds", "Three Pointers Made",
    "Turnovers", "Steals", "Blocks", "PRA"
]


# -------------------- Helpers --------------------
def read_any(path: Path) -> pd.DataFrame:
    """Read CSV with a fallback encoding for odd files."""
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def load_all() -> pd.DataFrame:
    """Load and normalize all daily CSVs in ./data/ matching 'NBA Full Stat Detail*.csv'."""
    files = sorted(DATA_DIR.glob("NBA Full Stat Detail*.csv"))
    if not files:
        raise SystemExit(
            f"No files found in {DATA_DIR}/ — drop your daily 'NBA Full Stat Detail*.csv' there."
        )

    frames = []
    for f in files:
        df = read_any(f)
        # strip weird spaces from headers
        df.columns = [c.strip() for c in df.columns]

        # rename variants → canonical
        for k, v in RENAME_MAP.items():
            if k in df.columns and v not in df.columns:
                df = df.rename(columns={k: v})

        keep = [c for c in CORE_COLS if c in df.columns]
        df = df[keep].copy()

        # normalize string columns early
        for c in ["Player", "Team", "Opponent", "Position", "Scenario"]:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()

        # Uppercase teams/opponents to be consistent with UI codes
        if "Team" in df.columns:
            df["Team"] = df["Team"].str.upper()
        if "Opponent" in df.columns:
            df["Opponent"] = df["Opponent"].str.upper()

        frames.append(df.assign(__file__=f.name))

    out = pd.concat(frames, ignore_index=True)

    # Coerce numerics
    numeric_cols = [
        "Minutes", "Points", "Assists", "Rebounds", "Three Pointers Made",
        "Turnovers", "Steals", "Blocks", "PRA"
    ]
    for c in numeric_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    # Basic quality filter
    required = ["Player", "Team", "Opponent", "Minutes"]
    out = out.dropna(subset=[c for c in required if c in out.columns])
    if "Minutes" in out.columns:
        out = out.query("Minutes > 0")

    return out


def train_for_stat(df: pd.DataFrame, stat: str):
    """
    Fit a simple ridge model:
      y = intercept + (Player one-hot * Minutes) + Opponent fixed effects
    Then extract:
      - per-player rate_per_min (coef on Minutes×Player)
      - opponent_adj (opponent fixed effects)
      - intercept
    """
    if stat not in df.columns:
        return None

    sub = df.dropna(subset=[stat]).copy()
    if len(sub) < 400:
        # too few rows to be reliable
        return None

    # One-hot players, then interact with Minutes to get per-minute rates
    P = pd.get_dummies(sub["Player"], drop_first=False)
    X_player = P.mul(sub["Minutes"].values.reshape(-1, 1), axis=0)

    # Opponent fixed effects (drop_first to avoid multicollinearity)
    X_opp = pd.get_dummies(sub["Opponent"], drop_first=True)

    # Compose design matrix
    X = pd.concat([X_player, X_opp], axis=1)
    y = sub[stat].values

    ridge = Ridge(alpha=1.0, fit_intercept=True, random_state=0)
    ridge.fit(X.values, y)
    y_hat = ridge.predict(X.values)

    coefs = pd.Series(ridge.coef_, index=X.columns)
    player_rates = (
        coefs[X_player.columns]
        .rename("rate_per_min")
        .reset_index()
        .rename(columns={"index": "Player"})
    )
    opp_adj = (
        coefs[X_opp.columns]
        .rename("opp_adj")
        .reset_index()
        .rename(columns={"index": "Opponent"})
    )
    intercept = float(ridge.intercept_)

    # Save artifacts
    base = stat.replace(" ", "_").lower()
    pr_path = ART_DIR / f"model_player_rates_{base}.csv"
    oa_path = ART_DIR / f"model_opp_adj_{base}.csv"
    meta_path = ART_DIR / f"model_meta_{base}.json"

    player_rates.to_csv(pr_path, index=False)
    opp_adj.to_csv(oa_path, index=False)
    with meta_path.open("w") as f:
        json.dump(
            {
                "stat": stat,
                "intercept": intercept,
                "alpha": 1.0,
                "n_rows": int(len(sub)),
                "r2_in_sample": float(r2_score(y, y_hat)),
                "mae_in_sample": float(mean_absolute_error(y, y_hat)),
            },
            f,
            indent=2,
        )

    return {
        "stat": stat,
        "n_rows": int(len(sub)),
        "player_count": int(P.shape[1]),
        "opponent_count": int(X_opp.shape[1] + 1),
        "artifacts": {
            "player_rates": str(pr_path),
            "opp_adj": str(oa_path),
            "meta": str(meta_path),
        },
    }


# -------------------- Main --------------------
def main():
    df = load_all()
    print(f"Loaded {len(df):,} rows from {df['__file__'].nunique()} daily files…")

    summary = []
    for stat in STATS:
        if stat not in df.columns:
            print(f"[SKIP] Column missing for {stat}")
            continue
        res = train_for_stat(df, stat)
        if res:
            print(f"[OK] Trained {stat}: artifacts in artifacts/")
            summary.append(res)
        else:
            print(f"[SKIP] Not enough rows for {stat}")

    # --- NEW: export players master (Player -> most recent Team) ---
    try:
        pm = df.dropna(subset=["Player"]).copy()
        pm["Player"] = pm["Player"].astype(str)
        pm["Team"] = pm["Team"].astype(str).str.upper()
        players_master = (
            pm.groupby("Player", as_index=False).agg({"Team": "last"}).sort_values("Player")
        )
        players_master.to_csv(ART_DIR / "players_master.csv", index=False)
        print("Saved players master → artifacts/players_master.csv")
    except Exception as e:
        print(f"[WARN] Could not write players_master.csv: {e}")

    if summary:
        (ART_DIR / "training_summary.json").write_text(
            json.dumps(summary, indent=2)
        )
        print("Saved training summary → artifacts/training_summary.json")


if __name__ == "__main__":
    main()

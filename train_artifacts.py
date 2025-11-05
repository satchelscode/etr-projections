import pandas as pd
import glob
import json
from pathlib import Path
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error

ART_DIR = Path("artifacts")
DATA_DIR = Path("data")
ART_DIR.mkdir(exist_ok=True)

CORE_COLS = [
    "Player","PlayerID","Position","Team","Opponent","Minutes",
    "Points","Assists","Rebounds","Three Pointers Made","Turnovers","Steals","Blocks","PRA","Scenario"
]

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

STATS = [
    "Points","Assists","Rebounds","Three Pointers Made","Turnovers","Steals","Blocks","PRA"
]

def read_any(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")

def load_all() -> pd.DataFrame:
    files = sorted(DATA_DIR.glob("NBA Full Stat Detail*.csv"))
    if not files:
        raise SystemExit(f"No files found in {DATA_DIR}/ — drop your daily 'NBA Full Stat Detail*.csv' there.")
    frames = []
    for f in files:
        df = read_any(f)
        df.columns = [c.strip() for c in df.columns]
        for k, v in RENAME_MAP.items():
            if k in df.columns and v not in df.columns:
                df = df.rename(columns={k: v})
        keep = [c for c in CORE_COLS if c in df.columns]
        df = df[keep].copy()
        frames.append(df.assign(__file__=f.name))
    out = pd.concat(frames, ignore_index=True)
    # numerics
    for c in ["Minutes","Points","Assists","Rebounds","Three Pointers Made","Turnovers","Steals","Blocks","PRA"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["Player","Team","Opponent","Minutes"]).query("Minutes > 0")
    return out

def train_for_stat(df: pd.DataFrame, stat: str):
    sub = df.dropna(subset=[stat]).copy()
    if len(sub) < 400:
        return None
    # Player per-minute interaction
    P = pd.get_dummies(sub["Player"], drop_first=False)
    X_player = P.mul(sub["Minutes"].values.reshape(-1,1), axis=0)
    # Opponent fixed-effects
    X_opp = pd.get_dummies(sub["Opponent"], drop_first=True)
    X = pd.concat([X_player, X_opp], axis=1)
    y = sub[stat].values

    ridge = Ridge(alpha=1.0, fit_intercept=True)
    ridge.fit(X.values, y)
    y_hat = ridge.predict(X.values)

    # Extract
    coefs = pd.Series(ridge.coef_, index=X.columns)
    player_rates = coefs[X_player.columns].rename("rate_per_min").reset_index().rename(columns={"index":"Player"})
    opp_adj = coefs[X_opp.columns].rename("opp_adj").reset_index().rename(columns={"index":"Opponent"})
    intercept = float(ridge.intercept_)

    # Save
    base = stat.replace(" ", "_").lower()
    pr_path = ART_DIR / f"model_player_rates_{base}.csv"
    oa_path = ART_DIR / f"model_opp_adj_{base}.csv"
    meta_path = ART_DIR / f"model_meta_{base}.json"

    player_rates.to_csv(pr_path, index=False)
    opp_adj.to_csv(oa_path, index=False)
    with meta_path.open("w") as f:
        json.dump({
            "stat": stat,
            "intercept": intercept,
            "alpha": 1.0,
            "n_rows": int(len(sub)),
            "r2_in_sample": float(r2_score(y, y_hat)),
            "mae_in_sample": float(mean_absolute_error(y, y_hat)),
        }, f, indent=2)

    return {
        "stat": stat,
        "n_rows": int(len(sub)),
        "player_count": int(P.shape[1]),
        "opponent_count": int(X_opp.shape[1] + 1),
        "artifacts": {
            "player_rates": str(pr_path),
            "opp_adj": str(oa_path),
            "meta": str(meta_path)
        }
    }

def main():
    df = load_all()
    print(f"Loaded {len(df):,} rows from {df['__file__'].nunique()} daily files…")
    summary = []
    for stat in STATS:
        if stat not in df.columns:
            continue
        res = train_for_stat(df, stat)
        if res:
            print(f"[OK] Trained {stat}: artifacts in artifacts/")
            summary.append(res)
        else:
            print(f"[SKIP] Not enough rows for {stat}")
    if summary:
        pd.DataFrame(summary).to_json(ART_DIR / "training_summary.json", orient="records", indent=2)
        print("Saved training summary → artifacts/training_summary.json")

if __name__ == "__main__":
    main()

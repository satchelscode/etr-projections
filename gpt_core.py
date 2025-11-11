import os, glob, pickle
import pandas as pd
from sklearn.linear_model import Ridge

def _nodate(df: pd.DataFrame) -> pd.DataFrame:
    drops = [c for c in df.columns if c.lower() in ("date","dateidx")]
    if drops:
        df = df.drop(columns=drops, errors="ignore")
    return df

def build_features(df: pd.DataFrame):
    df = _nodate(df)
    for col in ["Player","Team","Opp","Minutes"]:
        if col not in df.columns:
            df[col] = ""
    X = pd.get_dummies(
        df[["Player","Team","Opp","Minutes"]],
        columns=["Player","Team","Opp"],
        dummy_na=False
    )
    return X, X.columns.tolist()

def fit_model(df: pd.DataFrame):
    df = _nodate(df)
    if "Stat" not in df.columns or "Projection" not in df.columns:
        raise ValueError("training needs Stat + Projection")

    # Build full design matrix on TRAINING DATA to lock feature space
    X_all, feature_cols = build_features(df)

    stats = sorted(df["Stat"].unique())
    models = {}
    for stat in stats:
        sub = df[df["Stat"] == stat].copy()
        if sub.empty:
            continue
        Xs, _ = build_features(sub)
        # align submatrix to full training feature space
        Xs = Xs.reindex(columns=feature_cols, fill_value=0)
        y = pd.to_numeric(sub["Projection"], errors="coerce").astype(float).values
        m = Ridge(alpha=5.0)
        m.fit(Xs, y)
        models[stat] = m

    return {"feature_cols": feature_cols, "stats": stats, "models": models}

def save_artifact(bundle, model_id: str):
    os.makedirs("artifacts", exist_ok=True)
    path = f"artifacts/{model_id}.pkl"
    import pickle as pkl
    with open(path, "wb") as f:
        pkl.dump(bundle, f)
    return path

def load_latest_artifact():
    paths = sorted(glob.glob("artifacts/*.pkl"), key=os.path.getmtime, reverse=True)
    if not paths:
        raise FileNotFoundError("no artifacts/*.pkl found")
    import pickle as pkl
    with open(paths[0], "rb") as f:
        return pkl.load(f)

def predict_with_features(bundle, player, team, opp, minutes):
    # Single-row to predict
    df = pd.DataFrame([{
        "Player": player,
        "Team": team,
        "Opp": opp,
        "Minutes": float(minutes),
    }])
    X_pred, _ = build_features(df)
    # Align to training feature space
    feature_cols = bundle["feature_cols"]
    X_pred = X_pred.reindex(columns=feature_cols, fill_value=0)

    out = {}
    for stat, m in bundle["models"].items():
        try:
            out[stat] = float(m.predict(X_pred)[0])
        except Exception:
            out[stat] = None
    return out

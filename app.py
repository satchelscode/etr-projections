from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
from pathlib import Path

ART_DIR = Path("artifacts")

app = Flask(__name__)

# Stats we trained/saved as:
#   artifacts/model_player_rates_{base}.csv
#   artifacts/model_opp_adj_{base}.csv
#   artifacts/model_meta_{base}.json
# where base = stat name lowercased with spaces -> underscores
STATS = [
    "Points",
    "Assists",
    "Rebounds",
    "Three Pointers Made",
    "Turnovers",
    "Steals",
    "Blocks",
    "PRA",
]


def stat_to_base(stat: str) -> str:
    return stat.replace(" ", "_").lower()


class Model:
    """
    Loads:
      - meta[stat]['intercept']
      - player_rate[stat][player] = per-minute rate
      - opp_adj[stat][TEAM] = opponent effect
    Also builds optional players_master & per-team player index if
    artifacts/players_master.csv exists (exported by train_artifacts.py).
    """
    def __init__(self):
        self.meta = {}
        self.player_rate = {}
        self.opp_adj = {}
        self.players = set()
        self.opponents = set()

        self.players_master = None  # DataFrame with columns: Player, Team
        self.team_index = {}        # TEAM -> [players]

        # Load players_master (optional, used for roster-by-team)
        pm_path = ART_DIR / "players_master.csv"
        if pm_path.exists():
            try:
                pm = pd.read_csv(pm_path)
                pm["Player"] = pm["Player"].astype(str)
                pm["Team"] = pm["Team"].astype(str).str.upper()
                self.players_master = pm
                for t, sub in pm.groupby("Team"):
                    self.team_index[t] = sorted(sub["Player"].unique().tolist())
            except Exception:
                # keep going even if players_master is malformed
                pass

        # Load per-stat artifacts
        for stat in STATS:
            base = stat_to_base(stat)
            pr = ART_DIR / f"model_player_rates_{base}.csv"
            oa = ART_DIR / f"model_opp_adj_{base}.csv"
            mj = ART_DIR / f"model_meta_{base}.json"

            if pr.exists() and mj.exists():
                pr_df = pd.read_csv(pr)
                try:
                    oa_df = pd.read_csv(oa)
                except Exception:
                    oa_df = pd.DataFrame({"Opponent": [], "opp_adj": []})

                try:
                    with mj.open("r") as f:
                        meta = json.load(f)
                except Exception:
                    meta = {"intercept": 0.0}

                self.meta[stat] = meta
                # Player per-minute rates
                if "Player" in pr_df.columns and "rate_per_min" in pr_df.columns:
                    self.player_rate[stat] = dict(
                        zip(pr_df["Player"].astype(str), pr_df["rate_per_min"].astype(float))
                    )
                    self.players.update(pr_df["Player"].dropna().astype(str).tolist())
                else:
                    self.player_rate[stat] = {}

                # Opponent adjustments
                if "Opponent" in oa_df.columns and "opp_adj" in oa_df.columns:
                    self.opp_adj[stat] = dict(
                        zip(oa_df["Opponent"].astype(str), oa_df["opp_adj"].astype(float))
                    )
                    self.opponents.update(
                        oa_df["Opponent"].dropna().astype(str).tolist()
                    )
                else:
                    self.opp_adj[stat] = {}

        # Fallback: if we have no opponent list yet, seed with NBA team codes
        if not self.opponents:
            self.opponents = set(
                [
                    "ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU",
                    "IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL",
                    "PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"
                ]
            )


model = Model()


# ------------------- Helpers -------------------
def project_row(player: str, opponent: str, minutes: float) -> dict:
    out = {"player": player, "opponent": opponent, "minutes": minutes}
    if not model.player_rate:
        return out

    for stat in STATS:
        if stat not in model.meta:
            continue
        intercept = float(model.meta[stat].get("intercept", 0.0))
        rate = model.player_rate[stat].get(player)
        if rate is None:
            # Fallback to median rate for robustness
            vals = list(model.player_rate[stat].values())
            rate = float(pd.Series(vals).median()) if vals else 0.0

        opp_effect = float(model.opp_adj[stat].get(opponent, 0.0))
        proj = intercept + minutes * float(rate) + opp_effect
        out[f"Proj_{stat}"] = round(float(proj), 2)
    return out


# ------------------- Routes -------------------
@app.get("/")
def index():
    missing = not bool(model.player_rate)
    return render_template("index.html", missing_artifacts=missing)


@app.get("/api/opponents")
def api_opponents():
    return jsonify(sorted(list(model.opponents)))


@app.get("/api/players")
def api_players():
    """
    Optional query params:
      - team=TEAM (use roster from players_master.csv if available)
      - q=prefix (case-insensitive startswith)
    """
    q = (request.args.get("q") or "").strip().lower()
    team = (request.args.get("team") or "").strip().upper()

    if team and model.team_index.get(team):
        base = model.team_index[team]
    else:
        base = sorted(list(model.players))

    if q:
        base = [p for p in base if p.lower().startswith(q)]
    return jsonify(base)


@app.get("/api/players_master")
def api_players_master():
    if model.players_master is None:
        return jsonify([])
    return jsonify(model.players_master.to_dict(orient="records"))


@app.post("/api/project")
def api_project():
    data = request.get_json(force=True)
    player = str(data.get("player", ""))
    opponent = str(data.get("opponent", ""))
    minutes = float(data.get("minutes", 0) or 0)
    return jsonify(project_row(player, opponent, minutes))


@app.post("/api/project_bulk")
def api_project_bulk():
    """
    Body: { "rows": [ {"player":"...", "opponent":"OKC", "minutes": 32.5}, ... ] }
    """
    data = request.get_json(force=True)
    rows = data.get("rows", []) or []
    out = []
    for r in rows:
        p = str(r.get("player", ""))
        o = str(r.get("opponent", ""))
        m = float(r.get("minutes", 0) or 0)
        out.append(project_row(p, o, m))
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)

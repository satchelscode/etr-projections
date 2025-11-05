from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
from pathlib import Path

ART_DIR = Path("artifacts")

app = Flask(__name__)

STATS = [
    "Points","Assists","Rebounds","Three Pointers Made","Turnovers","Steals","Blocks","PRA"
]

class Model:
    def __init__(self):
        self.meta = {}
        self.player_rate = {}
        self.opp_adj = {}
        self.players = set()
        self.opponents = set()
        self.players_master = None          # DataFrame: Player, Team
        self.team_index = {}                # dict: TEAM -> [players]

        # try to load players master (for roster filtering)
        pm_path = ART_DIR / "players_master.csv"
        if pm_path.exists():
            try:
                pm = pd.read_csv(pm_path)
                pm["Player"] = pm["Player"].astype(str)
                pm["Team"] = pm["Team"].astype(str).str.upper()
                self.players_master = pm
                # build team index
                for t, sub in pm.groupby("Team"):
                    self.team_index[t] = sorted(sub["Player"].unique().tolist())
            except Exception:
                pass

        # load stat artifacts
        for stat in STATS:
            base = stat.replace(" ", "_").lower()
            pr = ART_DIR / f"model_player_rates_{base}.csv"
            oa = ART_DIR / f"model_opp_adj_{base}.csv"
            mj = ART_DIR / f"model_meta_{base}.json"
            if pr.exists() and mj.exists():
                pr_df = pd.read_csv(pr)
                try:
                    oa_df = pd.read_csv(oa)
                except Exception:
                    oa_df = pd.DataFrame({"Opponent":[], "opp_adj":[]})
                with mj.open("r") as f:
                    meta = json.load(f)
                self.meta[stat] = meta
                self.player_rate[stat] = dict(zip(pr_df["Player"], pr_df["rate_per_min"]))
                self.opp_adj[stat] = dict(zip(oa_df.get("Opponent", []), oa_df.get("opp_adj", [])))
                self.players.update(pr_df["Player"].dropna().astype(str).tolist())
                self.opponents.update(oa_df.get("Opponent", pd.Series(dtype=str)).dropna().astype(str).tolist())

model = Model()

# ---------- routes ----------
@app.get("/")
def index():
    missing = not bool(model.player_rate)
    return render_template("index.html", missing_artifacts=missing)

@app.get("/api/players")
def api_players():
    """Optional query params:
       - q=prefix  (case-insensitive startswith)
       - team=TEAM (filter roster if players_master is present)
    """
    q = (request.args.get("q") or "").strip().lower()
    team = (request.args.get("team") or "").strip().upper()

    # base list
    if team and model.team_index.get(team):
        base = model.team_index[team]
    else:
        base = sorted(list(model.players))

    if q:
        base = [p for p in base if p.lower().startswith(q)]

    return jsonify(base)

@app.get("/api/opponents")
def api_opponents():
    opps = sorted(list(set(list(model.opponents) + [
        "ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU","IND","LAC","LAL",
        "MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL","PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"
    ])))
    return jsonify(opps)

@app.get("/api/players_master")
def api_players_master():
    if model.players_master is None:
        return jsonify([])
    return jsonify(model.players_master.to_dict(orient="records"))

@app.post("/api/project")
def api_project():
    data = request.get_json(force=True)
    player = str(data.get("player",""))
    opponent = str(data.get("opponent",""))
    minutes = float(data.get("minutes", 0) or 0)

    out = {"player": player, "opponent": opponent, "minutes": minutes}

    if not model.player_rate:
        return jsonify({"error": "Artifacts not loaded. Train locally and commit artifacts/."}), 400

    for stat in STATS:
        if stat not in model.meta:
            continue
        intercept = float(model.meta[stat]["intercept"])
        rate = model.player_rate[stat].get(player)
        if rate is None:
            rate = pd.Series(model.player_rate[stat].values()).median()
        opp_effect = model.opp_adj[stat].get(opponent, 0.0)
        proj = intercept + minutes * float(rate) + float(opp_effect)
        out[f"Proj_{stat}"] = round(float(proj), 2)

    return jsonify(out)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)

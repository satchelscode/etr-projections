from flask import Flask, render_template, request, jsonify
import json
from pathlib import Path
import pandas as pd

# Blueprints
from minutes_api import minutes_bp
from daily_api import daily_bp

ART_DIR = Path("artifacts")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB uploads

# Register blueprints (once, after app exists)
app.register_blueprint(minutes_bp)
app.register_blueprint(daily_bp)

STATS = [
    "Points", "Assists", "Rebounds", "Three Pointers Made",
    "Turnovers", "Steals", "Blocks", "PRA",
]

def stat_to_base(s: str) -> str:
    return s.replace(" ", "_").lower()

def load_minutes_overrides() -> dict:
    store = ART_DIR / "minutes_overrides.json"
    if store.exists():
      try:
        data = json.loads(store.read_text(encoding="utf-8"))
        return data.get("overrides", {}) or {}
      except Exception:
        return {}
    return {}

class Model:
    def __init__(self):
        self.meta = {}
        self.player_rate = {}
        self.opp_adj = {}
        self.players = set()
        self.opponents = set()
        self.players_master = None
        self.team_index = {}

        pm_path = ART_DIR / "players_master.csv"
        if pm_path.exists():
            pm = pd.read_csv(pm_path)
            pm["Player"] = pm["Player"].astype(str)
            pm["Team"] = pm["Team"].astype(str).str.upper()
            self.players_master = pm
            for t, sub in pm.groupby("Team"):
                self.team_index[t] = sorted(sub["Player"].tolist())

        for stat in STATS:
            base = stat_to_base(stat)
            pr = ART_DIR / f"model_player_rates_{base}.csv"
            oa = ART_DIR / f"model_opp_adj_{base}.csv"
            mj = ART_DIR / f"model_meta_{base}.json"

            if pr.exists():
                pr_df = pd.read_csv(pr)
                d = dict(zip(pr_df["Player"].astype(str), pr_df["rate_per_min"].astype(float)))
                self.player_rate[stat] = d
                self.players.update(d.keys())
            else:
                self.player_rate[stat] = {}

            if oa.exists():
                oa_df = pd.read_csv(oa)
                d2 = dict(zip(oa_df["Opponent"].astype(str), oa_df["opp_adj"].astype(float)))
                self.opp_adj[stat] = d2
                self.opponents.update(d2.keys())
            else:
                self.opp_adj[stat] = {}

            if mj.exists():
                self.meta[stat] = json.loads(mj.read_text(encoding="utf-8"))
            else:
                self.meta[stat] = {"intercept": 0.0}

        if not self.opponents:
            self.opponents = set([
                "ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU",
                "IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL",
                "PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"
            ])

model = Model()

def project_row(player: str, opponent: str, minutes: float) -> dict:
    out = {"player": player, "opponent": opponent, "minutes": minutes}
    for stat in STATS:
        intercept = float(model.meta.get(stat, {}).get("intercept", 0.0))
        rate = model.player_rate.get(stat, {}).get(player)
        if rate is None:
            vals = list(model.player_rate.get(stat, {}).values())
            rate = float(pd.Series(vals).median()) if vals else 0.0
        opp = float(model.opp_adj.get(stat, {}).get(opponent, 0.0))
        out[f"Proj_{stat}"] = round(intercept + minutes * float(rate) + opp, 2)
    return out

@app.get("/")
def index():
    missing = not bool(model.player_rate)
    return render_template("index.html", missing_artifacts=missing)

@app.get("/api/players")
def api_players():
    q = (request.args.get("q") or "").lower().strip()
    team = (request.args.get("team") or "").upper().strip()
    if team and model.team_index.get(team):
        base = model.team_index[team]
    else:
        base = sorted(list(model.players))
    if q:
        base = [p for p in base if p.lower().startswith(q)]
    return jsonify(base)

@app.get("/api/opponents")
def api_opponents():
    return jsonify(sorted(list(model.opponents)))

@app.get("/api/players_master")
def api_players_master():
    if model.players_master is None:
        return jsonify([])
    return jsonify(model.players_master.to_dict(orient="records"))

@app.post("/api/project")
def api_project():
    data = request.get_json(force=True)
    return jsonify(project_row(
        str(data.get("player","")),
        str(data.get("opponent","")),
        float(data.get("minutes",0) or 0)
    ))

@app.post("/api/project_bulk")
def api_project_bulk():
    data = request.get_json(force=True)
    rows = data.get("rows", []) or []
    return jsonify([project_row(str(r.get("player","")), str(r.get("opponent","")), float(r.get("minutes",0) or 0)) for r in rows])

@app.get("/api/teams")
def api_teams():
    if model.players_master is None:
        return jsonify(sorted(list(model.opponents)))
    return jsonify(sorted(model.players_master["Team"].unique().tolist()))

@app.get("/api/team/<team>/roster")
def api_team_roster(team):
    t = team.upper()
    if model.team_index.get(t):
        roster = model.team_index[t]
    elif model.players_master is not None:
        roster = sorted(model.players_master[model.players_master["Team"] == t]["Player"].tolist())
    else:
        roster = []
    overrides = load_minutes_overrides()
    out = []
    for name in roster:
        ov = overrides.get(" ".join(name.lower().split()))
        minutes = ov["minutes"] if ov and isinstance(ov.get("minutes"), (int,float)) else ""
        out.append({"player": name, "opponent": "", "minutes": minutes})
    return jsonify(out)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)


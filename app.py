from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
from pathlib import Path
import os

# Minutes upload blueprint
from minutes_api import minutes_bp

ART_DIR = Path("artifacts")

app = Flask(__name__)
# register AFTER app is created
app.register_blueprint(minutes_bp)

########################################
#            MODEL SECTION
########################################

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

def _norm_name(s: str) -> str:
    return " ".join(str(s or "").strip().lower().replace("_", " ").split())

def load_minutes_overrides() -> dict:
    """Load overrides mapping: normalized player name -> {'minutes': float, 'opponent': str, 'raw': row}"""
    store = ART_DIR / "minutes_overrides.json"
    if store.exists():
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
            return data.get("overrides", {}) or {}
        except Exception:
            return {}
    return {}

class Model:
    """
    Loads per-minute rates + intercepts from artifacts, and optionally
    players_master.csv to map teams → players.
    """

    def __init__(self):
        self.meta = {}
        self.player_rate = {}
        self.opp_adj = {}
        self.players = set()
        self.opponents = set()

        self.players_master = None  # DataFrame with columns: Player, Team
        self.team_index = {}        # TEAM -> [players]

        # Optional: load players_master for team rosters
        pm_path = ART_DIR / "players_master.csv"
        if pm_path.exists():
            try:
                pm = pd.read_csv(pm_path)
                pm["Player"] = pm["Player"].astype(str)
                pm["Team"] = pm["Team"].astype(str).str.upper()
                self.players_master = pm
                for t, sub in pm.groupby("Team"):
                    roster = sorted(sub["Player"].tolist())
                    self.team_index[t] = roster
            except Exception:
                pass

        # load per-stat files
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
                    with mj.open("r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    meta = {"intercept": 0.0}

                self.meta[stat] = meta

                if (
                    "Player" in pr_df.columns
                    and "rate_per_min" in pr_df.columns
                ):
                    d = dict(
                        zip(
                            pr_df["Player"].astype(str),
                            pr_df["rate_per_min"].astype(float),
                        )
                    )
                    self.player_rate[stat] = d
                    self.players.update(list(d.keys()))
                else:
                    self.player_rate[stat] = {}

                if (
                    "Opponent" in oa_df.columns
                    and "opp_adj" in oa_df.columns
                ):
                    d2 = dict(
                        zip(
                            oa_df["Opponent"].astype(str),
                            oa_df["opp_adj"].astype(float),
                        )
                    )
                    self.opp_adj[stat] = d2
                    self.opponents.update(list(d2.keys()))
                else:
                    self.opp_adj[stat] = {}

        if not self.opponents:
            # fallback default
            self.opponents = set(
                [
                    "ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU",
                    "IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL",
                    "PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"
                ]
            )


model = Model()


########################################
#        PROJECTION CALC
########################################

def project_row(player: str, opponent: str, minutes: float) -> dict:
    """Compute all stat projections for a single (player, opp, minutes)."""
    out = {
        "player": player,
        "opponent": opponent,
        "minutes": minutes,
    }
    if not model.player_rate:
        # no artifacts
        return out

    for stat in STATS:
        if stat not in model.meta:
            continue

        intercept = float(model.meta[stat].get("intercept", 0.0))

        rate = model.player_rate[stat].get(player)
        if rate is None:
            vals = list(model.player_rate[stat].values())
            rate = float(pd.Series(vals).median()) if vals else 0.0

        opp_effect = float(model.opp_adj[stat].get(opponent, 0.0))
        proj = intercept + minutes * float(rate) + opp_effect

        out[f"Proj_{stat}"] = round(float(proj), 2)

    return out


########################################
#               ROUTES
########################################

@app.get("/")
def index():
    missing = not bool(model.player_rate)
    return render_template("index.html", missing_artifacts=missing)


@app.get("/api/opponents")
def api_opponents():
    return jsonify(sorted(list(model.opponents)))


@app.get("/api/players")
def api_players():
    # optional search
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
    data = request.get_json(force=True)
    rows = data.get("rows", []) or []
    out = []
    for r in rows:
        p = str(r.get("player", ""))
        o = str(r.get("opponent", ""))
        m = float(r.get("minutes", 0) or 0)
        out.append(project_row(p, o, m))
    return jsonify(out)


########################################
#         TEAM ROSTER HELPERS
########################################

@app.get("/api/teams")
def api_teams():
    if model.players_master is None:
        return jsonify(sorted(list(model.opponents)))
    else:
        arr = sorted(model.players_master["Team"].unique().tolist())
        return jsonify(arr)


@app.get("/api/team/<team>/roster")
def api_team_roster(team):
    """
    Returns rows with minutes pre-filled from overrides (if present),
    otherwise minutes is "" so UI can use the default minutes field.
    """
    t = team.upper()
    roster_names = []
    if model.team_index.get(t):
        roster_names = model.team_index[t]
    elif model.players_master is not None:
        roster_names = sorted(model.players_master[model.players_master["Team"] == t]["Player"].tolist())

    overrides = load_minutes_overrides()  # normalized-name -> dict
    rows = []
    for name in roster_names:
        ov = overrides.get(_norm_name(name))
        minutes = ov["minutes"] if ov and isinstance(ov.get("minutes"), (int, float)) else ""
        rows.append({"player": name, "opponent": "", "minutes": minutes})
    return jsonify(rows)


########################################
#               MAIN
########################################

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)

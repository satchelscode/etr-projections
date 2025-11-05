import os
import json
from flask import Flask, request, jsonify, render_template
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
import joblib

app = Flask(__name__)

ART_DIR = Path("artifacts")
STATS = [
    "Points",
    "Rebounds",
    "Assists",
    "Three Pointers Made",
    "Steals",
    "Blocks",
    "Turnovers",
    "PRA",   # = Points + Rebounds + Assists
]


class ModelArtifacts:
    """Holds:
      - intercept + midpoint
      - per-min player rate
      - opp effects
    """
    def __init__(self):
        self.meta = {}
        self.player_rate = {}
        self.opp_adj = {}

    def load(self, folder):
        meta_path = folder / "meta.json"
        if not meta_path.exists():
            return False
        with open(meta_path, "r") as f:
            self.meta = json.load(f)

        for stat in STATS:
            pfile = folder / f"{stat}_player_rate.json"
            ofile = folder / f"{stat}_opp_adj.json"

            if pfile.exists():
                with open(pfile, "r") as f:
                    self.player_rate[stat] = json.load(f)
            else:
                self.player_rate[stat] = {}

            if ofile.exists():
                with open(ofile, "r") as f:
                    self.opp_adj[stat] = json.load(f)
            else:
                self.opp_adj[stat] = {}

        return True


model = ModelArtifacts()
have_art = model.load(ART_DIR)


def project_one(player, opponent, minutes):
    """
    Return dict for 1 player / opponent / minutes
    """
    out = {
        "player": player,
        "opponent": opponent,
        "minutes": minutes,
    }

    for stat in STATS:
        if stat not in model.meta:
            continue
        intercept = float(model.meta[stat]["intercept"])
        rate = model.player_rate[stat].get(player)
        if rate is None:
            # fallback median
            rate = pd.Series(model.player_rate[stat].values()).median()

        opp_eff = model.opp_adj[stat].get(opponent, 0.0)
        pred = intercept + minutes * float(rate) + float(opp_eff)
        out[f"Proj_{stat}"] = round(float(pred), 2)

    return out


@app.get("/")
def index():
    return render_template("index.html", missing_artifacts=(not have_art))


@app.get("/api/players")
def api_players():
    """
    /api/players?team=OKC&q=sha
    filters by team if provided; then prefix match on "q".
    """
    plist = set()
    team = request.args.get("team", "")
    q = request.args.get("q", "").lower()

    # union over "player_rate" sets so we see all known players
    for statdict in model.player_rate.values():
        for p in statdict.keys():
            plist.add(p)

    players = sorted(plist)

    # first filter by team if provided:
    # heuristic: if we see the team as part of name or from prior usage,
    # but simpler: if player name contains "(OKC)"?  not guaranteed.
    # So we keep it simple: if team provided, we rely purely on q prefix
    # usage in front-end (they pass team so they get roster via prefix queries).
    if q:
        players = [p for p in players if p.lower().startswith(q)]

    return jsonify(players)


@app.get("/api/opponents")
def api_opponents():
    """
    Return list of opponent codes.  We harvest from opp_adj keys.
    """
    opps = set()
    for stat in STATS:
        for t in model.opp_adj.get(stat, {}).keys():
            opps.add(t)
    return jsonify(sorted(opps))


@app.post("/api/project")
def api_project():
    """
    Single player
    POST:
      { "player": "...", "opponent": "...", "minutes": 34 }
    """
    d = request.get_json(force=True)
    player = d.get("player", "")
    opponent = d.get("opponent", "")
    minutes = float(d.get("minutes", 0))
    return jsonify(project_one(player, opponent, minutes))


@app.post("/api/project_bulk")
def api_project_bulk():
    """
    bulk project
    {
      "rows": [
        { "player": "Kawhi Leonard", "opponent": "OKC", "minutes": 34 },
        ...
      ]
    }
    """
    if not model.player_rate:
        return jsonify({"error": "Artifacts not loaded."}), 400

    data = request.get_json(force=True)
    rows = data.get("rows", [])
    out = []
    for r in rows:
        p = r.get("player", "")
        o = r.get("opponent", "")
        m = float(r.get("minutes", 0))
        row = project_one(p, o, m)
        out.append(row)
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

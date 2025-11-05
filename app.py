import os
import json
import csv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, abort

APP_ROOT = os.path.dirname(__file__)
ARTIFACTS_DIR = os.path.join(APP_ROOT, "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

PLAYERS_MASTER = os.path.join(APP_ROOT, "players_master.csv")
MINUTES_STORE = os.path.join(ARTIFACTS_DIR, "minutes_overrides.json")

app = Flask(__name__, static_folder="static", template_folder="templates")

# ---------------------------
# Utilities
# ---------------------------

def norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())

def load_minutes_overrides():
    if os.path.exists(MINUTES_STORE):
        try:
            with open(MINUTES_STORE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"updated_at": None, "overrides": {}}
    return {"updated_at": None, "overrides": {}}

def save_minutes_overrides(payload):
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    with open(MINUTES_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def read_players_master():
    """Return [{'name': 'X', 'team': 'YYY'}, ...] best-effort from players_master.csv"""
    rows = []
    if not os.path.exists(PLAYERS_MASTER):
        return rows
    with open(PLAYERS_MASTER, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r.get("Player") or r.get("player") or r.get("Name") or r.get("name") or ""
            team = r.get("Team") or r.get("team") or ""
            if name:
                rows.append({"name": name, "team": team})
    return rows

# ---------------------------
# Pages
# ---------------------------

@app.route("/")
def index():
    # You already have this page
    missing = not os.path.isdir(ARTIFACTS_DIR)
    return render_template("index.html", missing_artifacts=missing)

# ---------------------------
# Minutes CSV endpoints
# ---------------------------

@app.route("/api/minutes/overrides", methods=["GET"])
def minutes_overrides_get():
    return jsonify(load_minutes_overrides())

@app.route("/api/minutes/upload", methods=["POST"])
def minutes_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file field 'file'"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "No selected file"}), 400

    overrides = {"updated_at": None, "overrides": {}}
    try:
        reader = csv.DictReader((line.decode("utf-8", errors="ignore") for line in f.stream))
        def get(row, key):
            for h in row.keys():
                if h.strip().lower() == key:
                    return row[h]
            return None

        count = 0
        new_map = {}
        for row in reader:
            player = (get(row, "player") or "").strip()
            mins_raw = (get(row, "minutes") or "").strip()
            opp = (get(row, "opp") or get(row, "opponent") or "").strip()
            if not player or mins_raw == "":
                continue
            try:
                minutes = float(mins_raw)
            except Exception:
                continue
            new_map[norm(player)] = {"minutes": minutes, "opponent": opp, "raw": row}
            count += 1

        overrides["overrides"] = new_map
        save_minutes_overrides(overrides)
        return jsonify({"ok": True, "count": count, "updated_at": overrides["updated_at"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/minutes/template.csv", methods=["GET"])
def minutes_template_download():
    path = os.path.join(ARTIFACTS_DIR, "minutes_template.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player", "opp", "minutes"])
        # Example row (commented out)
        # w.writerow(["LeBron James", "NYK", 34])
    return send_file(path, as_attachment=True, download_name="minutes_template.csv")

# ---------------------------
# Meta/data endpoints for dropdowns
# ---------------------------

@app.route("/api/meta", methods=["GET"])
def api_meta():
    players = read_players_master()
    teams = sorted(list({p.get("team") for p in players if p.get("team")}))
    return jsonify({
        "players": players,              # [{name, team}]
        "teams": teams,                  # ["NYK", "BOS", ...]
        "opponents": teams               # mirror teams by default
    })

@app.route("/api/players", methods=["GET"])
def api_players():
    return jsonify(read_players_master())

@app.route("/api/teams", methods=["GET"])
def api_teams():
    players = read_players_master()
    teams = sorted(list({p.get("team") for p in players if p.get("team")}))
    return jsonify(teams)

@app.route("/api/opponents", methods=["GET"])
def api_opponents():
    # identical to /api/teams for now
    players = read_players_master()
    teams = sorted(list({p.get("team") for p in players if p.get("team")}))
    return jsonify(teams)

@app.route("/api/team/<team>/roster", methods=["GET"])
def api_team_roster(team):
    team_norm = norm(team)
    players = read_players_master()
    roster = [{"player": p["name"], "opponent": "", "minutes": ""} for p in players if norm(p.get("team")) == team_norm]
    return jsonify(roster)

# ---------------------------
# Serve players_master.csv at root (for JS CSV fallback)
# ---------------------------

@app.route("/players_master.csv", methods=["GET"])
def players_master_file():
    if not os.path.exists(PLAYERS_MASTER):
        abort(404)
    return send_from_directory(APP_ROOT, "players_master.csv")

# ---------------------------
# NOTE: We DO NOT touch your existing projection endpoints.
# Keep your /api/project and /api/project/bulk handlers as-is in this same file.
# If they are not here, add them below. The front-end expects them.
# ---------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

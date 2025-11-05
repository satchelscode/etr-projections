import os
import json
import csv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, abort

# -----------------------------
# App setup
# -----------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

MINUTES_STORE = os.path.join(ARTIFACTS_DIR, "minutes_overrides.json")

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

def norm_name(s: str) -> str:
    return " ".join(s.strip().lower().split())

# -----------------------------
# PAGES
# -----------------------------
@app.route("/")
def index():
    # Render as-is; existing UI pulls data via JS.
    return render_template("index.html")

# ======================================================
# ===============  MINUTES: API ENDPOINTS  =============
# ======================================================

@app.route("/api/minutes/overrides", methods=["GET"])
def minutes_overrides_get():
    """
    Returns current minutes overrides as:
    {
      "updated_at": "...",
      "overrides": {
        "<player_name_lower>": {
          "minutes": float,
          "opponent": "NYK" (optional, passthrough),
          "raw": {...original row...}
        },
        ...
      }
    }
    """
    return jsonify(load_minutes_overrides())

@app.route("/api/minutes/upload", methods=["POST"])
def minutes_upload():
    """
    Accepts multipart/form-data with file field 'file'.
    CSV expected columns (case-insensitive):
      - player  (required)
      - minutes (required; int/float)
      - opp     (optional; ignored for merge, but stored)
      - ...     (ignored)
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file part 'file'"}), 400

    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "No selected file"}), 400

    try:
        # Parse CSV
        overrides = load_minutes_overrides()
        reader = csv.DictReader((line.decode("utf-8", errors="ignore") for line in f.stream))
        # Normalise headers
        headers = [h.strip().lower() for h in reader.fieldnames or []]
        def get(row, key):
            # case-insensitive accessor
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
                # skip incomplete rows
                continue
            try:
                minutes = float(mins_raw)
            except Exception:
                continue

            key = norm_name(player)
            new_map[key] = {
                "minutes": minutes,
                "opponent": opp,
                "raw": row
            }
            count += 1

        overrides["overrides"] = new_map
        save_minutes_overrides(overrides)

        return jsonify({
            "ok": True,
            "count": count,
            "updated_at": overrides["updated_at"]
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/minutes/template.csv", methods=["GET"])
def minutes_template_download():
    """
    Generate a CSV template with headers only:
      player,opp,minutes
    """
    try:
        path = os.path.join(ARTIFACTS_DIR, "minutes_template.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["player", "opp", "minutes"])
            # Optionally write a single example row
            # w.writerow(["LeBron James", "NYK", 34])
        return send_file(path, as_attachment=True, download_name="minutes_template.csv")
    except Exception as e:
        abort(500, str(e))

# ======================================================
# =======  EXISTING DATA ENDPOINTS (placeholders)  =====
# ======================================================
# Keep your existing endpoints below (projections, teams, etc.)
# Nothing else changes. The front-end will merge minutes overrides on the client.
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

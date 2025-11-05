# minutes_api.py
import os
import json
import csv
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, current_app

minutes_bp = Blueprint("minutes", __name__)

APP_ROOT = os.path.dirname(__file__)
ARTIFACTS_DIR = os.path.join(APP_ROOT, "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

MINUTES_STORE = os.path.join(ARTIFACTS_DIR, "minutes_overrides.json")

def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())

def _load_minutes():
    if os.path.exists(MINUTES_STORE):
        try:
            with open(MINUTES_STORE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"updated_at": None, "overrides": {}}

def _save_minutes(payload):
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    with open(MINUTES_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

@minutes_bp.route("/api/minutes/overrides", methods=["GET"])
def minutes_overrides_get():
    return jsonify(_load_minutes())

@minutes_bp.route("/api/minutes/upload", methods=["POST"])
def minutes_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file field 'file'"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "No selected file"}), 400

    # Read entire file and let csv.Sniffer pick the delimiter.
    content = f.read().decode("utf-8", errors="ignore")
    if not content.strip():
        return jsonify({"ok": False, "error": "Empty file"}), 400

    try:
        sample = content[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        except Exception:
            # default to comma
            dialect = csv.excel
        reader = csv.DictReader(content.splitlines(), dialect=dialect)
        if not reader.fieldnames:
            return jsonify({"ok": False, "error": "No headers found"}), 400

        def get(row, key_variants):
            for want in key_variants:
                for h in row.keys():
                    if h.strip().lower() == want:
                        return row[h]
            return None

        overrides = _load_minutes()
        new_map = {}
        count = 0
        for row in reader:
            player = (get(row, ["player", "name", "player_name"]) or "").strip()
            mins_raw = (get(row, ["minutes", "mins", "min"]) or "").strip()
            opp = (get(row, ["opp", "opponent", "opp_team"]) or "").strip()
            if not player or mins_raw == "":
                continue
            try:
                minutes = float(mins_raw)
            except Exception:
                continue
            new_map[_norm(player)] = {"minutes": minutes, "opponent": opp, "raw": row}
            count += 1

        overrides["overrides"] = new_map
        _save_minutes(overrides)
        return jsonify({"ok": True, "count": count, "updated_at": overrides["updated_at"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@minutes_bp.route("/api/minutes/template.csv", methods=["GET"])
def minutes_template_download():
    template_path = os.path.join(ARTIFACTS_DIR, "minutes_template.csv")
    with open(template_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player", "opp", "minutes"])
        # example (comment out if you prefer blank):
        # w.writerow(["LeBron James", "NYK", 34])
    return send_file(template_path, as_attachment=True, download_name="minutes_template.csv")

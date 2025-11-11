from flask import Flask, jsonify, send_file
from daily_api_gpt import bp as gpt_bp
import os

app = Flask(__name__)
app.register_blueprint(gpt_bp, url_prefix="/api/gpt")

@app.get("/")
def index():
    return "etr-projections API"

@app.get("/api/health")
def api_health():
    return jsonify(ok=True, status="live")

@app.get("/monitor")
def monitor():
    """Serve the monitoring dashboard"""
    return send_file("monitor.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=False)

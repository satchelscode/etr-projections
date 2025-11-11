diff --git a/app.py b/app.py
index bf760d63284c198dd913e0865d48cdddf4a28bdb..08fcbd928a2c62da7d577c88f16f7ab7a8b8b413 100644
--- a/app.py
+++ b/app.py
@@ -1,16 +1,20 @@
-from flask import Flask, jsonify
+"""Application entry point for the ETR projections service."""
+
+from flask import Flask, jsonify, render_template
+
 from daily_api_gpt import bp as gpt_bp
 
-app = Flask(__name__)
+
+app = Flask(__name__, static_folder="static", template_folder="templates")
 app.register_blueprint(gpt_bp, url_prefix="/api/gpt")
 
 @app.get("/")
 def index():
-    return "etr-projections API"
+    return render_template("index.html")
 
 @app.get("/api/health")
 def api_health():
     return jsonify(ok=True, status="live")
 
 if __name__ == "__main__":
     app.run(host="0.0.0.0", port=5005, debug=False)

diff --git a/app.py b/app.py
index bf760d63284c198dd913e0865d48cdddf4a28bdb..aca17ef05891abefa1895baa2fce3b81444fd9ea 100644
--- a/app.py
+++ b/app.py
@@ -1,16 +1,16 @@
-from flask import Flask, jsonify
+from flask import Flask, jsonify, render_template
 from daily_api_gpt import bp as gpt_bp
 
 app = Flask(__name__)
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

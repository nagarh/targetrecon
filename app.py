"""TargetRecon — Hugging Face Spaces entry point.

Runs the Flask web app on port 7860 (HF Spaces default).
"""
from targetrecon.webapp import app, _ensure_ketcher

if __name__ == "__main__":
    _ensure_ketcher()
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)

#!/usr/bin/env python3
"""Serve CostSense AI web dashboard on port 8501."""
import os, sys, threading, webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
PORT = int(os.environ.get("DASHBOARD_PORT", 8501))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)
    def log_message(self, *a): pass

def open_browser():
    import time; time.sleep(0.6)
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    print(f"  CostSense AI Dashboard  →  http://localhost:{PORT}")
    print("  API backend must be running on port 8000 (python run.py)")
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")

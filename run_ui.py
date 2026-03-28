"""
CostSense AI — Streamlit UI Entry Point

Usage:
    python run_ui.py
    python run_ui.py --port 8501 --api-url http://localhost:8000
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="CostSense AI Streamlit UI")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--host", default="localhost")
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_BASE_URL", "http://localhost:8000"),
        help="FastAPI backend URL",
    )
    parser.add_argument("--browser", action="store_true", default=True, help="Open browser automatically")
    parser.add_argument("--no-browser", dest="browser", action="store_false")
    args = parser.parse_args()

    # Set API_BASE_URL so the UI components can reach the backend
    os.environ["API_BASE_URL"] = args.api_url

    app_path = Path(__file__).parent / "ui" / "streamlit_app.py"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(args.port),
        "--server.address",
        args.host,
        "--theme.base",
        "dark",
    ]

    if not args.browser:
        cmd.extend(["--server.headless", "true"])

    print(f"Starting CostSense AI UI on http://{args.host}:{args.port}")
    print(f"API backend: {args.api_url}")
    print("Press Ctrl+C to stop.\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nUI server stopped.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to start Streamlit: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

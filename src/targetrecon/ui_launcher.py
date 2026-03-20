"""Entry point for the targetrecon-ui command."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    app_path = Path(__file__).parent / "app.py"
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(app_path),
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        check=True,
    )

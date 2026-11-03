"""Convenience entry point for the complete capstone pipeline."""
from pathlib import Path
import subprocess, sys
ROOT = Path(__file__).resolve().parent
if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "run_all.py"], cwd=ROOT))

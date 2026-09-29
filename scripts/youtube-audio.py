"""Separate YouTube read, private upload, and old-video management commands."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kenton_workflow.youtube_audio import main

if __name__ == "__main__":
    raise SystemExit(main())

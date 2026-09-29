"""Repair a local service recording without importing document dependencies."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kenton_workflow.audio_repair import main

if __name__ == "__main__":
    raise SystemExit(main())

"""Create an editable video repair plan from a local recording."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kenton_workflow.video_repair import plan_main

if __name__ == "__main__":
    raise SystemExit(plan_main())

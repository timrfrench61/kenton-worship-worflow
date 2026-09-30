import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kenton_workflow.youtube_lookup import resolve_video
from kenton_workflow.youtube_config import configured_channel


class LookupTests(unittest.TestCase):
    def test_selection_duplicates_missing_and_log(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Path(folder) / "inventory.json"
            log = Path(folder) / "lookup.log"
            def entry(hour, basis="actual_start"):
                return {"youtube": {"event_local_date": "2026-09-20", "event_local_time": f"2026-09-20T{hour}:02:35-07:00", "date_basis": basis}}
            data = {"channel": {"id": configured_channel()}, "videos": {"am": entry("11"), "pm": entry("18"), "upload": entry("11", "published_at")}}
            catalog.write_text(json.dumps(data))
            day = date(2026, 9, 20)
            self.assertEqual(resolve_video(day, "morning", catalog, log), "am")
            self.assertEqual(resolve_video(day, "evening", catalog, log), "pm")
            data["videos"]["duplicate"] = entry("11")
            catalog.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                resolve_video(day, "morning", catalog, log)
            with self.assertRaisesRegex(ValueError, "No matching"):
                resolve_video(date(2026, 9, 19), "morning", catalog, log)
            self.assertIn("ATTENTION: Duplicate", log.read_text())
            self.assertIn("ATTENTION: No matching", log.read_text())

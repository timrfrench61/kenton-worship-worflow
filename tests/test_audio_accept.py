import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kenton_workflow.audio_repair import digest
from kenton_workflow.youtube_audio import repair_file


class AcceptanceTests(unittest.TestCase):
    def test_cli_acceptance_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = directory / "source.mp4"
            source.write_bytes(b"fixture source")
            media = directory / "repaired.partial.mp4"
            media.write_bytes(b"fixture rendered media")
            report = directory / "repair.json"
            data = {"state": "incomplete", "source": str(source), "source_sha256": digest(source),
                    "output": str(directory / "repaired.mp4"),
                    "checks": {"loudness": True, "peak": False, "duration": False, "source_unchanged": True}}
            report.write_text(json.dumps(data))
            command = [sys.executable, str(ROOT / "scripts/audio-repair-accept.py"), str(report)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            data["checks"]["duration"] = True
            report.write_text(json.dumps(data))
            before = report.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(report.read_bytes(), before)
            approved, path = repair_file(directory / "accepted.json")
            self.assertFalse(approved["checks"]["peak"])
            self.assertEqual(path.resolve(), media.resolve())
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            media.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                repair_file(directory / "accepted.json")

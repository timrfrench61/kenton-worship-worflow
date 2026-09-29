"""Real FFmpeg CLI checks for picture replacement, slide timing and retained audio."""
import array
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kenton_workflow.audio_repair import digest
from kenton_workflow.video_repair import seconds


class TimestampTests(unittest.TestCase):
    def test_explicit_finite_timestamps(self):
        self.assertAlmostEqual(seconds("01:02:03.5", "test"), 3723.5)
        for invalid in (None, True, "NaN", "inf", -1, "00:60:00", "12:30"):
            with self.assertRaises(ValueError):
                seconds(invalid, "test")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
class VideoCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "work").mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="video-tests-", dir=ROOT / "work")
        cls.folder = Path(cls.temp.name)
        for name, color, tone, duration in (("service.mp4", "red", 440, 6), ("hswtl.mp4", "blue", 880, 3)):
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", f"color=c={color}:size=160x90:rate=10",
                            "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000", "-t", str(duration),
                            "-c:v", "libx264", "-c:a", "aac", str(cls.folder / name)], check=True)
        for name, color in (("band.png", "lime"), ("piano.png", "yellow")):
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", f"color=c={color}:size=160x90", "-frames:v", "1", str(cls.folder / name)], check=True)

    @classmethod
    def tearDownClass(cls):
        # Optional test artifact export for separate visual inspection.
        keep = os.environ.get("KENTON_VIDEO_TEST_ARTIFACTS")
        if keep:
            shutil.copytree(cls.folder, Path(keep))
        cls.temp.cleanup()

    def cli(self, script, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], capture_output=True, text=True)

    def plan(self, name, audio="original", out=2):
        value = {"schema": 1, "source": "service.mp4", "source_audio_track": 0,
                 "output": {"width": 160, "height": 90, "fps": "10"},
                 "edits": [{"type": "replace", "label": "HSWTL", "start": 1, "end": 3, "file": "hswtl.mp4", "in": 0, "out": out, "audio": audio},
                           {"type": "slide", "kind": "praise-band", "start": 3, "end": 4, "file": "band.png"},
                           {"type": "slide", "kind": "piano", "start": 4, "end": 5, "file": "piano.png"}]}
        path = self.folder / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, value

    def pixel(self, path, timestamp):
        result = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(path), "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
        self.assertEqual(len(result.stdout), 3)
        return tuple(result.stdout)

    def frequency(self, path, timestamp):
        result = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(path), "-t", "0.5", "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"], capture_output=True, check=True)
        samples = array.array("h", result.stdout)
        crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
        return crossings / (len(samples) / 48000)

    def test_starter_is_incomplete_and_protected(self):
        path = self.folder / "starter.json"
        result = self.cli("plan-video-repair.py", self.folder / "service.mp4", "--output", path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(path.read_text())
        self.assertEqual(plan["edits"][0]["audio"], "original")
        self.assertIsNone(plan["edits"][0]["start"])
        self.assertEqual(self.cli("repair-video.py", path, "--check").returncode, 1)
        original = path.read_bytes()
        self.assertEqual(self.cli("plan-video-repair.py", self.folder / "service.mp4", "--output", path).returncode, 1)
        self.assertEqual(path.read_bytes(), original)

    def test_original_audio_and_all_three_edits(self):
        plan, _ = self.plan("original-audio.json")
        source_hash = digest(self.folder / "service.mp4")
        job = self.folder / "original-audio-result"
        checked = self.cli("repair-video.py", plan, "--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertFalse(job.exists())
        result = self.cli("repair-video.py", plan, "--output-dir", job)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = job / "repaired.mp4"
        report = json.loads((job / "video-repair.json").read_text())
        self.assertEqual(report["state"], "complete")
        self.assertTrue(all(report["checks"].values()))
        self.assertAlmostEqual(report["output_duration"], 6, delta=0.15)
        for time, expected in ((0.5, (255, 0, 0)), (1.5, (0, 0, 255)), (3.5, (0, 255, 0)), (4.5, (255, 255, 0)), (5.5, (255, 0, 0))):
            pixel = self.pixel(output, time)
            self.assertTrue(all(abs(a - b) < 15 for a, b in zip(pixel, expected)), (time, pixel))
            self.assertAlmostEqual(self.frequency(output, time), 440, delta=5)
        self.assertEqual(source_hash, digest(self.folder / "service.mp4"))
        self.assertFalse(list(job.glob("segment-*.mkv")))
        self.assertEqual(self.cli("repair-video.py", plan, "--output-dir", job).returncode, 1)
        self.assertEqual(digest(output), report["output_sha256"])

    def test_file_audio_and_changed_duration_mapping(self):
        plan, _ = self.plan("file-audio.json", audio="file", out=1)
        job = self.folder / "file-audio-result"
        result = self.cli("repair-video.py", plan, "--output-dir", job)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((job / "video-repair.json").read_text())
        self.assertAlmostEqual(report["output_duration"], 5, delta=0.15)
        self.assertAlmostEqual(self.frequency(job / "repaired.mp4", 1.25), 880, delta=5)
        self.assertAlmostEqual(self.frequency(job / "repaired.mp4", 2.25), 440, delta=5)
        self.assertGreater(self.pixel(job / "repaired.mp4", 2.5)[1], 240)
        self.assertEqual(report["segments"][2]["output_start"], 2)

    def test_bad_edits_fail_before_render(self):
        cases = ["overlap", "unequal-audio", "missing-file", "range", "typo", "no-edits", "bad-fps", "bad-track"]
        for name in cases:
            path, plan = self.plan(name + ".json")
            if name == "overlap": plan["edits"][1]["start"] = 2
            if name == "unequal-audio": plan["edits"][0]["out"] = 1
            if name == "missing-file": plan["edits"][0]["file"] = "missing.mp4"
            if name == "range": plan["edits"][0]["end"] = 100
            if name == "typo": plan["edits"][0]["adudio"] = "original"
            if name == "no-edits": plan["edits"] = []
            if name == "bad-fps": plan["output"]["fps"] = "0/0"
            if name == "bad-track": plan["source_audio_track"] = 5
            path.write_text(json.dumps(plan))
            job = self.folder / (name + "-result")
            result = self.cli("repair-video.py", path, "--output-dir", job)
            self.assertEqual(result.returncode, 1, name + result.stdout + result.stderr)
            self.assertIn("ATTENTION:", result.stdout)
            self.assertFalse(job.exists())


if __name__ == "__main__":
    unittest.main()

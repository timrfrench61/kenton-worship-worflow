"""Real FFmpeg CLI tests and isolated YouTube request tests; no account actions."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kenton_workflow.audio_repair import digest
from kenton_workflow.youtube_audio import mark_original, upload


class AudioCLI(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def cli(self, script, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], capture_output=True, text=True)

    def test_help_and_review_guard_without_google(self):
        for script in ("repair-audio.py", "youtube-audio.py"):
            self.assertEqual(self.cli(script, "--help").returncode, 0)
        result = self.cli("youtube-audio.py", "upload", "missing.json", "--metadata", "missing.json", "--original-id", "old", "--channel-id", "channel")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--reviewed", result.stdout)

    def test_missing_input_and_bad_target(self):
        result = self.cli("repair-audio.py", self.folder / "missing.mp4")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Recording not found", result.stdout)
        self.assertEqual(self.cli("repair-audio.py", "missing", "--lufs", "nan").returncode, 2)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_real_repair_and_silence(self):
        for silent in (False, True):
            source = self.folder / ("silent.mp4" if silent else "quiet.mp4")
            audio = "anullsrc=r=48000:cl=stereo" if silent else "sine=frequency=440:sample_rate=48000,volume=0.1"
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=size=160x90:rate=25", "-f", "lavfi", "-i", audio,
                            "-t", "6", "-c:v", "libx264", "-c:a", "aac", str(source)], check=True)
            original = digest(source)
            destination = self.folder / ("silent-result" if silent else "result")
            result = self.cli("repair-audio.py", source, "--output-dir", destination)
            self.assertEqual(digest(source), original)
            report = json.loads((destination / "repair.json").read_text())
            if silent:
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(report["state"], "incomplete")
                self.assertFalse((destination / "repaired.mp4").exists())
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(report["state"], "complete")
                self.assertLess(abs(float(report["after"]["input_i"]) + 18), 1)
                print(f"Real FFmpeg test: {report['before']['input_i']} -> {report['after']['input_i']} LUFS", flush=True)
                rerun = self.cli("repair-audio.py", source, "--output-dir", destination)
                self.assertEqual(rerun.returncode, 1)
                self.assertEqual(digest(destination / "repaired.mp4"), report["output_sha256"])


class YouTubeActions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.api = Mock()
        self.api.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": "channel"}]}
        self.old = {"id": "old", "snippet": {"title": "Original", "categoryId": "22", "channelId": "channel", "description": "Retain this", "tags": ["service"]},
                    "status": {"privacyStatus": "public", "embeddable": True, "license": "youtube", "selfDeclaredMadeForKids": False}}
        self.new = {"id": "new", "snippet": {"channelId": "channel"}, "status": {"privacyStatus": "public"}, "processingDetails": {"processingStatus": "succeeded"}}
        self.receipt = self.folder / "upload.json"
        self.receipt.write_text(json.dumps({"state": "private-verified", "original_id": "old", "video_id": "new", "channel_id": "channel"}))

    def args(self, action):
        return argparse.Namespace(receipt=self.receipt, channel_id="channel", reviewed=True, action=action)

    def reads(self, *items):
        self.api.videos.return_value.list.return_value.execute.side_effect = [{"items": [item]} for item in items]

    def test_private_replacement_blocks_hiding_old(self):
        self.new["status"]["privacyStatus"] = "private"
        self.reads(self.old, self.new)
        with self.assertRaisesRegex(ValueError, "must be processed"):
            mark_original(self.args("private"), self.api)
        self.api.videos.return_value.update.assert_not_called()

    def test_document_only_and_wrong_channel(self):
        self.reads(self.old, self.new)
        self.assertEqual(mark_original(self.args("document"), self.api)["state"], "documented")
        self.api.videos.return_value.update.assert_not_called()
        self.api.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": "wrong"}]}
        with self.assertRaisesRegex(ValueError, "not the requested channel"):
            mark_original(self.args("unlisted"), self.api)

    def test_notice_preserves_metadata_and_snapshots(self):
        updated = json.loads(json.dumps(self.old))
        updated["snippet"]["description"] = "Audio-corrected recording: https://www.youtube.com/watch?v=new\n\nRetain this"
        self.reads(self.old, self.new, updated)
        result = mark_original(self.args("notice"), self.api)
        self.assertEqual(result["state"], "verified")
        request = self.api.videos.return_value.update.call_args.kwargs
        self.assertEqual(request["part"], "snippet")
        self.assertEqual(request["body"]["snippet"]["tags"], ["service"])
        self.assertEqual(result["before"], self.old)

    def test_privacy_preserves_other_status(self):
        updated = json.loads(json.dumps(self.old))
        updated["status"]["privacyStatus"] = "private"
        self.reads(self.old, self.new, updated)
        mark_original(self.args("private"), self.api)
        request = self.api.videos.return_value.update.call_args.kwargs
        self.assertEqual(request["part"], "status")
        self.assertEqual(request["body"]["status"], updated["status"])

    def test_upload_private_changed_file_and_duplicate_guard(self):
        self.receipt.unlink()
        media = self.folder / "repaired.mp4"
        media.write_bytes(b"fixture - no real upload")
        report = self.folder / "repair.json"
        report.write_text(json.dumps({"state": "complete", "checks": {"loudness": True}, "output": str(media), "output_sha256": digest(media)}))
        metadata = self.folder / "metadata.json"
        metadata.write_text(json.dumps({"title": "Repaired", "description": "Description", "categoryId": "22", "madeForKids": False}))
        args = argparse.Namespace(report=report, metadata=metadata, original_id="old", channel_id="channel", reviewed=True)
        self.new["status"]["privacyStatus"] = "private"
        self.reads(self.old, self.new)
        self.api.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "new"})
        result = upload(args, self.api, Mock())
        self.assertEqual(result["state"], "private-verified")
        self.assertEqual(self.api.videos.return_value.insert.call_args.kwargs["body"]["status"]["privacyStatus"], "private")
        with self.assertRaisesRegex(ValueError, "already attempted"):
            upload(args, self.api, Mock())
        media.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            upload(args, self.api, Mock())

    def test_youtube_cli_with_fake_service(self):
        # Execute the actual script as __main__ in a separate process. Only the
        # external service is substituted; argument parsing and receipts are real.
        harness = self.folder / "cli_fixture.py"
        harness.write_text('''import json, runpy, sys
from pathlib import Path
from unittest.mock import Mock
root, receipt = map(Path, sys.argv[1:3])
sys.path.insert(0, str(root / 'src'))
from kenton_workflow import youtube_audio
api = Mock()
api.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'channel'}]}
api.videos.return_value.list.return_value.execute.return_value = {'items': [{'snippet': {'channelId': 'channel'}, 'status': {'privacyStatus': 'private'}}]}
youtube_audio.service = lambda *a, **kw: api
sys.argv = [str(root / 'scripts/youtube-audio.py'), 'mark-original', str(receipt), '--channel-id', 'channel', '--action', 'document', '--reviewed']
runpy.run_path(sys.argv[0], run_name='__main__')
''', encoding="utf-8")
        result = subprocess.run([sys.executable, str(harness), str(ROOT), str(self.receipt)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((self.folder / "original-document.json").read_text())["state"], "documented")

    def test_interrupted_upload_keeps_receipt(self):
        self.receipt.unlink()
        media = self.folder / "repaired.mp4"
        media.write_bytes(b"fixture")
        report = self.folder / "repair.json"
        report.write_text(json.dumps({"state": "complete", "checks": {"loudness": True}, "output": str(media), "output_sha256": digest(media)}))
        metadata = self.folder / "metadata.json"
        metadata.write_text(json.dumps({"title": "Repaired", "description": "Description", "categoryId": "22", "madeForKids": False}))
        args = argparse.Namespace(report=report, metadata=metadata, original_id="old", channel_id="channel", reviewed=True)
        self.reads(self.old)
        self.api.videos.return_value.insert.return_value.next_chunk.side_effect = RuntimeError("network interrupted")
        with self.assertRaises(RuntimeError):
            upload(args, self.api, Mock())
        self.assertEqual(json.loads(self.receipt.read_text())["state"], "started")
        with self.assertRaisesRegex(ValueError, "already attempted"):
            upload(args, self.api, Mock())


if __name__ == "__main__":
    unittest.main()

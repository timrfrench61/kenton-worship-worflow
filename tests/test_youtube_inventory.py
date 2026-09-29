import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kenton_workflow.youtube_inventory import collect


class InventoryTests(unittest.TestCase):
    def fixture(self):
        api = Mock()
        api.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": "channel", "snippet": {"title": "Kenton"}, "contentDetails": {"relatedPlaylists": {"uploads": "playlist"}}}]}
        api.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "public"}}], "nextPageToken": "second"},
            {"items": [{"contentDetails": {"videoId": "private"}}]}]
        def video(key, privacy):
            return {"id": key, "snippet": {"title": "Service", "channelId": "channel", "publishedAt": "2026-09-28T01:00:00Z"},
                    "status": {"privacyStatus": privacy}, "contentDetails": {"duration": "PT1H"},
                    "liveStreamingDetails": {"actualStartTime": "2026-09-28T01:00:00Z"}}
        api.videos.return_value.list.return_value.execute.return_value = {"items": [video("public", "public"), video("private", "private")]}
        old = {"schema": 1, "timezone": "UTC", "channel": None, "videos": {"public": {"local": {"service": "evening", "proposed_title": "Evening (AUDIO FIXED)"}}, "old": {"local": {"repair_status": "reviewed"}}}}
        return api, old

    def test_pagination_public_filter_preserve_labels_and_missing(self):
        api, old = self.fixture()
        result, count = collect(api, old)
        self.assertEqual(count, 1)
        self.assertNotIn("private", result["videos"])
        self.assertEqual(result["videos"]["public"]["local"], old["videos"]["public"]["local"])
        self.assertFalse(result["videos"]["old"]["seen_in_public_inventory"])
        self.assertEqual(api.playlistItems.return_value.list.call_count, 2)
        self.assertNotIn("youtube", old["videos"]["public"])

    def test_network_failure_does_not_mutate_catalog(self):
        api, old = self.fixture()
        before = json.dumps(old)
        api.videos.return_value.list.return_value.execute.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            collect(api, old)
        self.assertEqual(json.dumps(old), before)

    def test_wrong_channel_rejected(self):
        api, old = self.fixture()
        with self.assertRaisesRegex(ValueError, "Select an authorized"):
            collect(api, old, "other")

    def test_real_cli_label_and_date_list(self):
        api, old = self.fixture()
        catalog, _ = collect(api, old)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            path.write_text(json.dumps(catalog))
            harness = Path(folder) / "run_local.py"
            harness.write_text('''import runpy,sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / 'src'))
from kenton_workflow import youtube_inventory
youtube_inventory.ROOT = Path(__file__).parent
sys.argv = [str(root / 'scripts/inventory-youtube.py'), *sys.argv[2:]]
runpy.run_path(sys.argv[0], run_name='__main__')
''')
            command = [sys.executable, str(harness), str(ROOT), "--catalog", str(path)]
            result = subprocess.run(command + ["label", "public", "--date", "2026-09-27", "--service", "evening", "--title", "Evening (AUDIO FIXED)"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            listing = subprocess.run(command + ["list", "--date", "2026-09-27"], capture_output=True, text=True)
            self.assertEqual(listing.returncode, 0)
            self.assertIn("Evening (AUDIO FIXED)", listing.stdout)

    def test_sync_entrypoint_with_fake_api(self):
        _, old = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            path.write_text(json.dumps(old))
            harness = Path(folder) / "run_sync.py"
            harness.write_text('''import runpy,sys
from pathlib import Path
root, catalog = map(Path, sys.argv[1:3])
sys.path[:0] = [str(root / 'src'), str(root / 'tests')]
from test_youtube_inventory import InventoryTests
from kenton_workflow import youtube_inventory
api, _ = InventoryTests().fixture()
youtube_inventory.ROOT = catalog.parent
youtube_inventory.service = lambda *a, **kw: api
sys.argv = [str(root / 'scripts/inventory-youtube.py'), '--catalog', str(catalog), 'sync']
runpy.run_path(sys.argv[0], run_name='__main__')
''')
            result = subprocess.run([sys.executable, str(harness), str(ROOT), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["channel"]["id"], "channel")
            self.assertNotIn("private", saved["videos"])


if __name__ == "__main__":
    unittest.main()

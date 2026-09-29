import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from kenton_workflow import youtube_audio, youtube_config

TARGET = 'UCQv5lUpAVNhfV7RS1Hzbf-Q'
OTHERS = ['UCf_VN9JkxVt21UJheXtRdzw', 'UCRgaPdRqB4C94lUiHwMSNvA']


class ChannelConfigTests(unittest.TestCase):
    def test_configured_identity(self):
        self.assertEqual(youtube_config.configured_channel(), TARGET)
        for other in OTHERS:
            with self.assertRaisesRegex(ValueError, 'differs from youtube.json'):
                youtube_config.configured_channel(other)

    def test_cli_rejects_other_channels_before_google_access(self):
        for other in OTHERS:
            for script, arguments in (
                ('inventory-youtube.py', ['sync', '--channel-id', other]),
                ('youtube-audio.py', ['read', 'unused', '--output', 'unused.json', '--channel-id', other])):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *arguments], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('differs from youtube.json', result.stdout)

    def test_auth_wrong_channel_does_not_save_token(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'credentials-read.json').write_text('{}')
            credentials = Mock(granted_scopes=youtube_audio.SCOPES['read'])
            flow = Mock()
            flow.from_client_secrets_file.return_value.run_local_server.return_value = credentials
            api = Mock()
            api.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': OTHERS[1]}]}
            with patch.object(youtube_audio, 'dependencies', return_value=(Mock(), Mock(), flow, Mock(return_value=api), Mock())):
                with self.assertRaisesRegex(ValueError, 'does not provide configured channel'):
                    youtube_audio.service('read', directory, authorize=True)
            self.assertFalse((directory / 'token-read.json').exists())

    def test_missing_or_invalid_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'youtube.json'
            with patch.object(youtube_config, 'CONFIG', path):
                with self.assertRaises(FileNotFoundError):
                    youtube_config.configured_channel()
                path.write_text(json.dumps({'channel_id': 'Kenton Session'}))
                with self.assertRaises(ValueError):
                    youtube_config.configured_channel()


if __name__ == '__main__':
    unittest.main()

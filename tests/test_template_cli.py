import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TemplateCliTests(unittest.TestCase):
    def test_template_flags_through_update_entry_point(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            (fixture / 'sitecustomize.py').write_text('''
import json, os
from pathlib import Path
from kenton_workflow import automation as a
a.ROOT = Path(os.environ['FIXTURE_ROOT'])
def probe(root, day, check, offline, chords, bulletin_templates):
    print('SELECTION=' + json.dumps(str(bulletin_templates) if bulletin_templates else 'standard'))
    return 0
a.update_automation = probe
''')
            env = dict(os.environ, FIXTURE_ROOT=str(fixture),
                       PYTHONPATH=os.pathsep.join([str(fixture), str(repo / 'src')]))
            command = [sys.executable, str(repo / 'scripts/update-automation.py'), '--date', '2026-10-04']
            for flags, expected in [([], 'standard'), (['--communion'], str(fixture / 'work/templates/communion')),
                                    (['--bulletin-templates', 'custom'], 'custom'), ([], 'standard')]:
                result = subprocess.run(command + flags, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('SELECTION=' + json.dumps(expected), result.stdout)
            result = subprocess.run(command + ['--communion', '--bulletin-templates', 'custom'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            result = subprocess.run(command + ['--communion', '--website-only'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('cannot be used with --website-only', result.stdout)

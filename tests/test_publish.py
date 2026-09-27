"""Exercise the publish entry point using temporary output and destination folders."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublishTests(unittest.TestCase):
    def test_publish_destination_and_guards(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / 'project'
            output = project / 'work/output'
            output.mkdir(parents=True)
            destination = base / 'drive-week-sets'
            destination.mkdir()
            files = {'study.docx': b'synthetic Word fixture', 'study.pdf': b'synthetic PDF fixture'}
            for name, payload in files.items():
                (output / name).write_bytes(payload)
            build = {'date': '2026-09-27', 'complete': True,
                     'files': {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}}
            (project / 'work/build.json').write_text(json.dumps(build))
            (project / 'work/input-state.json').write_text(json.dumps({'date': build['date']}))
            (base / 'sitecustomize.py').write_text(
                'from pathlib import Path\nfrom kenton_workflow import automation as a\n'
                f'a.ROOT = Path({str(project)!r})\n'
                f'a.PUBLISH_ROOT = Path({str(destination)!r})\n'
                'import os\n'
                'if os.environ.get("FAIL_PUBLISH_PROMOTION"):\n'
                '    original_rename = Path.rename\n'
                '    def fail_promotion(self, target):\n'
                '        if self.name.startswith(".publish-"):\n'
                '            raise OSError("Simulated final rename failure")\n'
                '        return original_rename(self, target)\n'
                '    Path.rename = fail_promotion\n')
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(base), str(ROOT / 'src')]))
            command = [sys.executable, str(ROOT / 'scripts/publish-automation.py')]
            def run(*args):
                return subprocess.run([*command, *args], env=env, capture_output=True, text=True)
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Review the output first', result.stdout)
            destination.rmdir()
            result = run('--reviewed')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((project / 'work/week-sets').exists())
            destination.mkdir()
            (output / 'study.pdf').write_bytes(b'changed after review')
            result = run('--reviewed')
            self.assertIn('Review output changed', result.stdout)
            self.assertFalse(list(destination.iterdir()))
            (output / 'study.pdf').write_bytes(files['study.pdf'])
            result = run('--reviewed')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            target = destination / '20260927'
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, files)
            self.assertFalse((project / 'work/week-sets').exists())
            result = run('--reviewed')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Nothing was overwritten', result.stdout)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, files)
            (target / 'obsolete.pdf').write_bytes(b'previous-only file')
            previous = {p.name: p.read_bytes() for p in target.iterdir()}
            result = run('--force')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, previous)
            (output / 'study.pdf').write_bytes(b'unreviewed edit')
            result = run('--reviewed', '--force')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, previous)
            (output / 'study.pdf').write_bytes(files['study.pdf'])
            result = run('--reviewed', '--force')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, files)
            backups = list((destination / '_archive').glob('*/20260927'))
            self.assertEqual(len(backups), 1)
            self.assertEqual({p.name: p.read_bytes() for p in backups[0].iterdir()}, previous)
            (target / 'keep-on-failure.pdf').write_bytes(b'preserve on rollback')
            before_failure = {p.name: p.read_bytes() for p in target.iterdir()}
            env['FAIL_PUBLISH_PROMOTION'] = '1'
            result = run('--reviewed', '--force')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Previous week-set restored', result.stdout)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, before_failure)
            del env['FAIL_PUBLISH_PROMOTION']
            build['complete'] = False
            (project / 'work/build.json').write_text(json.dumps(build))
            result = run('--reviewed', '--force')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Update has not completed', result.stdout)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()}, before_failure)


if __name__ == '__main__':
    unittest.main()

"""Exercise input's real CLI without touching Drive or active work."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import openpyxl


class InputRefreshTests(unittest.TestCase):
    def test_switch_rerun_and_failed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / 'scripts'
            scripts.mkdir()
            for name in ('input-automation.py', '_python_environment.py'):
                shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts' / name, scripts / name)
            source = root / 'drive'
            source.mkdir()
            for name in ('recent-logs.xlsx', 'Song-Lists.xlsx'):
                book = openpyxl.Workbook()
                book.save(source / name)
                book.close()
            for week in ('20260920', '20260927'):
                folder = source / 'week-sets' / week
                folder.mkdir(parents=True)
                (folder / f'{week}-morning-bulletin.docx').write_bytes(week.encode())
            previous = root / 'work/desktop/previous'

            def run(day):
                return subprocess.run([sys.executable, str(scripts / 'input-automation.py'),
                                       '--date', day, '--source', str(source)],
                                      capture_output=True, text=True)

            result = run('2026-09-27')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            (previous / 'user-notes.txt').write_text('keep me')
            book = openpyxl.load_workbook(source / 'Song-Lists.xlsx')
            book.active['A1'] = 'Updated Drive song list'
            book.save(source / 'Song-Lists.xlsx')
            book.close()
            result = run('2026-10-04')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / 'work/planning/Song-Lists.xlsx').read_bytes(),
                             (source / 'Song-Lists.xlsx').read_bytes())
            self.assertEqual([p.name for p in previous.iterdir()], ['20260927-morning-bulletin.docx'])
            archives = root / 'work/_archive/input-refresh'
            self.assertEqual(len(list(archives.glob('*/previous/user-notes.txt'))), 1)
            self.assertEqual(len(list(archives.glob('*/previous/20260920-morning-bulletin.docx'))), 1)
            result = run('2026-10-04')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(list(previous.iterdir())), 1)
            (source / 'recent-logs.xlsx').unlink()
            result = run('2026-09-27')
            self.assertEqual(result.returncode, 1)
            self.assertEqual((previous / '20260927-morning-bulletin.docx').read_bytes(), b'20260927')
            state = json.loads((root / 'work/input-state.json').read_text())
            self.assertFalse(state['complete'])


if __name__ == '__main__':
    unittest.main()

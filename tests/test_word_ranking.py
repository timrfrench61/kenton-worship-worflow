import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class RankingTests(unittest.TestCase):
    def test_cli_ranking_and_rejection(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copyfile(repo / 'scripts/_research_output.py', root / 'scripts/_research_output.py')
            (root / 'work').mkdir()
            shutil.copyfile(repo / 'scripts/rank-word-study.py', root / 'scripts/rank-word-study.py')
            shutil.copyfile(repo / 'application.json', root / 'application.json')
            source = {'complete': True, 'passage': 'Matthew 5:8', 'main_passage': {'data': {}},
                      'bible': {'data': {}}, 'words': [{'word': 'pure'}]}
            for testament, book in [('old_testament', 'GEN'), ('new_testament', 'MAT')]:
                source['words'][0][testament] = {'verses': [
                    {'id': f'{book}.1.{i}', 'reference': f'{book} 1:{i}', 'text': f'Exact source text {i}'}
                    for i in range(1, 7)]}
            (root / 'source.json').write_text(json.dumps(source))
            (root / 'sitecustomize.py').write_text('''
import io, json, os
import urllib.request
def fake(request, timeout):
    body = json.loads(request.data)
    payload = json.loads(body['contents'][0]['parts'][0]['text'].split('\\n', 1)[1])
    groups = [{'group': g['group'], 'ordered_ids': [v['id'] for v in reversed(g['verses'])]} for g in payload['groups']]
    if os.environ.get('BAD'):
        groups[0]['ordered_ids'][0] = 'INVENTED'
    return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps({'groups': groups})}]}}]}).encode())
urllib.request.urlopen = fake
''')
            env = dict(os.environ, PYTHONPATH=str(root), GEMINI_API_KEY='synthetic-key')
            command = [sys.executable, str(root / 'scripts/rank-word-study.py'),
                       '--input', 'source.json', '--output', 'work/ranked.json']
            run = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            output = json.loads((root / 'work/ranked.json').read_text())
            self.assertEqual(output['words'][0]['old_testament']['verses'][0]['text'], 'Exact source text 6')
            md = (root / 'work/ranked.md').read_text(encoding='utf-8')
            self.assertIn('See also... GEN 1:3; GEN 1:2; GEN 1:1.', md)
            self.assertNotIn('Exact source text 1', md)
            self.assertNotIn('synthetic-key', (root / 'work/ranked.json').read_text())
            again = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(again.returncode, 1)
            forced = subprocess.run(command + ['--force'], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
            self.assertEqual(len(list((root / 'work/_archive/research').glob('*/ranked.json'))), 1)
            before = (root / 'work/ranked.json').read_bytes()
            failed_force = subprocess.run(command + ['--force'], cwd=root, env=dict(env, BAD='1'), capture_output=True, text=True)
            self.assertEqual(failed_force.returncode, 1)
            self.assertEqual((root / 'work/ranked.json').read_bytes(), before)
            command[-1] = 'work/bad.json'
            bad = subprocess.run(command, cwd=root, env=dict(env, BAD='1'), capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertFalse((root / 'work/bad.json').exists())
            env['GEMINI_API_KEY'] = ''
            missing = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            self.assertIn('Set GEMINI_API_KEY', missing.stdout)

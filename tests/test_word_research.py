import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class WordResearchTests(unittest.TestCase):
    def test_cli_balanced_sources_shortfall_and_wrong_translation(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copyfile(repo / 'scripts/_research_output.py', root / 'scripts/_research_output.py')
            shutil.copyfile(repo / 'scripts/research-word-study.py', root / 'scripts/research-word-study.py')
            shutil.copyfile(repo / 'application.json', root / 'application.json')
            (root / 'sitecustomize.py').write_text('''
import io, json, os
from urllib.parse import urlparse, parse_qs
import urllib.request
ID = '78a9f6124f344018-01'
def fake(request, timeout):
    url = urlparse(request.full_url)
    query = parse_qs(url.query)
    if url.path.endswith(ID):
        data = dict(id=ID, abbreviation='KJV' if os.environ.get('WRONG') else 'NIV11',
                    name='New International Version 2011', language={'id':'eng'})
    elif url.path.endswith('/search'):
        if 'range' not in query:
            data = {'passages':[{'id':'MAT.5.8','bibleId':ID,'reference':'Matthew 5:8'}]}
        else:
            book = 'GEN' if query['range'][0].startswith('GEN') else 'MAT'
            size = 3 if os.environ.get('SHORT') else 8
            verses = [dict(id=f'{book}.1.{i}',bookId=book,bibleId=ID,
                           reference=f'{book} 1:{i}',text='pure heart synthetic text') for i in range(1,size+1)]
            data = {'verses':verses + [verses[0]],'total':size}
    else:
        identity = url.path.rsplit('/',1)[1]
        book, chapter, verse = identity.split('.')
        data = dict(id=identity,bookId=book,bibleId=ID,reference=f'{book} {chapter}:{verse}',
                    content='Full synthetic verse from verse endpoint.')
    return io.BytesIO(json.dumps({'data':data}).encode())
urllib.request.urlopen = fake
''')
            env = dict(os.environ, PYTHONPATH=str(root), API_BIBLE_KEY='synthetic-key')
            command = [sys.executable, str(root / 'scripts/research-word-study.py'), '--passage', 'Matthew 5:8',
                       '--words', 'pure', '--output', str(root / 'work/result.json')]
            run = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result = json.loads((root / 'work/result.json').read_text())
            for testament in ('old_testament', 'new_testament'):
                verses = result['words'][0][testament]['verses']
                self.assertEqual(len(verses), 6)
                self.assertEqual(len({v['id'] for v in verses}), 6)
                self.assertTrue(all(v['text'].startswith('Full synthetic') for v in verses))
            self.assertNotIn('synthetic-key', (root / 'work/result.json').read_text())
            self.assertTrue((root / 'work/result.md').exists())
            rerun = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(rerun.returncode, 1)
            forced = subprocess.run(command + ['--force'], env=env, capture_output=True, text=True)
            self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
            self.assertEqual(len(list((root / 'work/_archive/research').glob('*/result.json'))), 1)
            config = json.loads((root / 'application.json').read_text())
            config['word_study']['cache_directory'] = 'work/short-cache'
            (root / 'application.json').write_text(json.dumps(config))
            command[-1] = str(root / 'work/short.json')
            run = subprocess.run(command, env=dict(env, SHORT='1'), capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
            self.assertFalse(json.loads((root / 'work/short.json').read_text())['complete'])
            command[-1] = str(root / 'work/wrong.json')
            run = subprocess.run(command, env=dict(env, WRONG='1'), capture_output=True, text=True)
            self.assertEqual(run.returncode, 1)
            self.assertFalse((root / 'work/wrong.json').exists())

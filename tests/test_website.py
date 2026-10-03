"""Website publication uses fixtures, never the actual website project."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kenton_workflow import website

ROOT = Path(__file__).resolve().parents[1]


class WebsiteTests(unittest.TestCase):
    def test_appearance_settings_validate_and_preserve_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / 'site/wwwroot/images/card-background/test.jpg'
            image.parent.mkdir(parents=True)
            image.write_bytes(b'fixture')
            config = {'project': str(root/'site'), 'cards': {'next-sunday-morning': {
                'backgroundImage': 'test.jpg', 'appearance': {'overlayColor': '#12345680', 'imageOpacity': '0.6'}}}}
            website.write(root/'website.json', config)
            cards = [{'slot': 'next-sunday-morning', 'summary': 'Keep teaching'}]
            website.apply_appearance(root, cards)
            self.assertEqual(cards[0]['summary'], 'Keep teaching')
            self.assertEqual(cards[0]['appearance']['overlayColor'], '#12345680')
            config['cards']['next-sunday-morning']['appearance']['overlayColor'] = 'red; background:url(https://example.org)'
            website.write(root/'website.json', config)
            with self.assertRaisesRegex(ValueError, '#RRGGBB'):
                website.apply_appearance(root, cards)

    def test_rollover_review_edit_guard_and_idempotent_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = root / 'site'
            target = site / 'data.json'
            cards = []
            for period, day in [('last', '2026-09-13'), ('next', '2026-09-20')]:
                for service in ('morning', 'evening'):
                    cards.append(dict(slot=f'{period}-sunday-{service}', serviceDate=day,
                        backgroundImage='photo.jpg', summary='Old service', heading='Old heading',
                        timeframe='Today', speaker='Old speaker', linkUrl='/old.pdf', linkLabel='Old study'))
            website.write(target, {'cards': cards})
            website.write(root/'website.json', {'project': str(site), 'data_file': 'data.json'})
            plan = {'date': '2026-09-27'}
            for service in ('morning', 'evening'):
                plan[service] = dict(sermon='Matthew 5:7', topic='Current topic',
                    kind='word-study', call_to_worship='Psalm 34:1-3', praise_songs=['Song'], hymns=[])
            draft = website.prepare(root, plan['date'], plan)
            data = website.read(draft)
            self.assertEqual([c['serviceDate'] for c in data['cards']], ['2026-09-20']*2+['2026-09-27']*2)
            self.assertEqual(data['cards'][0]['linkUrl'], '/old.pdf')
            self.assertIsNone(data['cards'][2]['linkUrl'])
            self.assertIsNone(data['cards'][2]['speaker'])
            self.assertEqual(data['cards'][2]['backgroundImage'], 'photo.jpg')
            (root/'sitecustomize.py').write_text('from pathlib import Path\nfrom kenton_workflow import automation as a\n'+f'a.ROOT=Path({str(root)!r})\n')
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root), str(ROOT/'src')]))
            def run(*args):
                return subprocess.run([sys.executable, str(ROOT/'scripts/publish-automation.py'),
                    '--date', plan['date'], '--website-only', *args], env=env, capture_output=True, text=True)
            self.assertNotEqual(run().returncode, 0)
            before = target.read_bytes()
            target.write_bytes(before+b' ')
            self.assertIn('edited after preparation', run('--reviewed').stdout)
            self.assertEqual(target.read_bytes(), before+b' ')
            target.write_bytes(before)
            result = run('--reviewed')
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual(target.read_bytes(), draft.read_bytes())
            self.assertEqual(run('--reviewed').returncode, 0)
            self.assertEqual(len(list((root/'work/_archive/website').glob('*.json'))), 1)
            website.prepare(root, plan['date'], plan)  # Same-week rerun retains last Sunday.
            with self.assertRaisesRegex(ValueError, 'verified'):
                website.prepare(root, '2026-10-11', dict(plan, date='2026-10-11'))


if __name__ == '__main__':
    unittest.main()

"""Source parsing and cleanup tests with synthetic Scripture HTML, not live services."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kenton_workflow import automation as a


def source(ref='Matthew 1:1-2', version='New International Version', second=True):
    return (f'<html><meta charset="utf-8"><h1 class="passage-display">{ref} {version}</h1>'
            '<div class="passage-content"><h3>Not Scripture</h3>'
            '<span class="text Matt-1-1"><sup>1</sup>Exact first, '
            '<span class="text Matt-1-1">with punctuation.</span><sup>Footnote</sup></span>'
            + ('<span class="text Matt-1-2">Exact second!</span>' if second else '') + '</div></html>').encode()


class NIVAndCleanupTests(unittest.TestCase):
    def test_exact_source_cache_and_no_offline_summary_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with self.assertRaisesRegex(ValueError, 'not cached'):
                a.exact_niv_reading('Matt 1:1-2', cache, offline=True)
            with patch.object(a, 'urlopen', return_value=io.BytesIO(source())):
                actual = a.exact_niv_reading('Matt 1:1-2', cache)
            self.assertEqual(actual, 'Exact first, with punctuation. Exact second!')
            self.assertEqual(a.exact_niv_reading('Matt 1:1-2', cache, offline=True), actual)
            path = next(cache.glob('*.json'))
            record = json.loads(path.read_text())
            record['html'] = record['html'].replace('Exact first', 'Paraphrased first')
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'cache changed'):
                a.exact_niv_reading('Matt 1:1-2', cache, offline=True)

    def test_wrong_version_reference_and_missing_verse_rejected(self):
        for payload in (source(version='Different Version'), source(ref='Matthew 1:3-4'), source(second=False)):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                with patch.object(a, 'urlopen', return_value=io.BytesIO(payload)):
                    with self.assertRaises(ValueError):
                        a.exact_niv_reading('Matthew 1:1-2', Path(directory))
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_small_caps_and_nonconsecutive_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = source(ref='Matthew 1:1', second=False).replace(
                b'Exact first, ', b'<span class="small-caps">Lord</span>, ')
            with patch.object(a, 'urlopen', return_value=io.BytesIO(payload)):
                self.assertEqual(a.exact_niv_reading('Matt 1:1', Path(directory)), 'LORD, with punctuation.')
            third = source(ref='Matthew 1:3', second=False).replace(b'Matt-1-1', b'Matt-1-3')
            with patch.object(a, 'urlopen', return_value=io.BytesIO(third)):
                self.assertEqual(a.exact_niv_reading('Matt 1:1, 3', Path(directory)),
                                 'LORD, with punctuation.\nExact first, with punctuation.')

    def test_cleanup_checks_scope_and_verified_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root / 'work/.update-fixture'
            stage.mkdir(parents=True)
            (stage / 'draft').write_bytes(b'draft')
            manifest = {'study.docx': a.hashlib.sha256(b'output').hexdigest()}
            for folder in ('desktop', 'output'):
                target = root / 'work' / folder
                target.mkdir()
                (target / 'study.docx').write_bytes(b'output')
            with self.assertRaisesRegex(ValueError, 'Refusing cleanup'):
                a.finish_update_stage(root, root / 'work/output', True, manifest)
            (root / 'work/output/study.docx').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'no longer matches'):
                a.finish_update_stage(root, stage, True, manifest)
            self.assertTrue(stage.exists())
            (root / 'work/output/study.docx').write_bytes(b'output')
            self.assertIsNone(a.finish_update_stage(root, stage, True, manifest))
            self.assertFalse(stage.exists())
            self.assertTrue((root / 'work/output/study.docx').exists())


if __name__ == '__main__':
    unittest.main()

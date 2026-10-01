from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO

from kenton_workflow.automation import bible_reading


class BulletinReadingTests(unittest.TestCase):
    def test_multiple_sections_and_translation_rejection(self):
        def section(verse, version='New International Version'):
            return (f'<div class="passage-display">Psalm 150:{verse} {version}</div>'
                    f'<div class="passage-content"><span class="text Ps-150-{verse}">'
                    f'Synthetic verse {verse}—text.</span></div>')
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            payload = ('<html>' + section(1) + section(2) + section(6) + '</html>').encode()
            with patch('kenton_workflow.automation.urlopen', return_value=BytesIO(payload)):
                self.assertEqual(bible_reading('Psalm 150:1-2, 6', cache),
                                 ['Synthetic verse 1—text.', 'Synthetic verse 2—text.', 'Synthetic verse 6—text.'])
            self.assertEqual(len(bible_reading('Psalm 150:1-2, 6', cache, offline=True)), 3)
            payload = ('<html>' + section(1) + section(6, 'Other version') + '</html>').encode()
            with patch('kenton_workflow.automation.urlopen', return_value=BytesIO(payload)):
                with self.assertRaisesRegex(ValueError, 'not labeled'):
                    bible_reading('Psalm 150:1, 6', cache)

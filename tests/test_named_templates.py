from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from docx import Document
from kenton_workflow import handouts
from test_handouts import template, plan, authored


class NamedTemplateTests(unittest.TestCase):
    def test_discussion_uses_named_layout_and_current_authored_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layouts, sources = root / 'templates', root / 'authored'
            layouts.mkdir()
            sources.mkdir()
            layout = layouts / 'discussion_template.docx'
            template(layout, 'discussion')
            service = plan('discussion')
            service['topic'] = 'Example Series (2) New Topic'
            current = sources / 'episode2.docx'
            data = authored('discussion')
            handouts.generate(service, {'_handout_source': layout, 'handout_content': data}, current)
            before = layout.read_bytes()
            content = {}
            selected = handouts.prepare_named(service, content, layouts, [sources])
            self.assertEqual(selected, layout)
            self.assertEqual(content['handout_content']['episode'], '2')
            self.assertEqual(content['handout_content']['scripture'], data['scripture'])
            output = root / 'output.docx'
            handouts.generate(service, dict(content, _handout_source=selected), output)
            text = '\n'.join(p.text for p in Document(output).paragraphs)
            self.assertIn('EPISODE 2', text)
            self.assertNotIn('EPISODE 1', text)
            self.assertEqual(layout.read_bytes(), before)

    def test_word_layout_is_separate_from_authored_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layouts, sources = root / 'templates', root / 'authored'
            layouts.mkdir()
            sources.mkdir()
            template(layouts / 'word_study_template.docx', 'word-study')
            source = sources / 'study.docx'
            template(source, 'word-study')
            content = {}
            self.assertEqual(handouts.prepare_named(plan('word-study'), content, layouts, [sources]),
                             layouts / 'word_study_template.docx')
            self.assertEqual(content['_word_content_source'], source)
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'Template found:.*Missing current authored teaching content'):
                handouts.prepare_named(plan('word-study'), {}, layouts, [sources])

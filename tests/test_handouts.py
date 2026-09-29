"""Synthetic teaching text only. Word export is simulated in CLI isolation tests."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from kenton_workflow import handouts


def template(path, kind):
    doc = Document()
    if kind == 'discussion':
        for value in ('Example Series', 'EPISODE 1  /  Example Topic', 'Example presenter',
                      'Purpose: Example purpose', 'Five Points to Watch For'):
            doc.add_paragraph(value)
        for i in range(5):
            doc.add_paragraph(f'Point {i}. Explanation {i}.')
            doc.add_paragraph('')
        doc.add_page_break()
        doc.add_paragraph('Five Questions for Reflection')
        for i in range(5):
            doc.add_paragraph(f'Question {i}? Follow-up {i}?')
            doc.add_paragraph('___________')
        doc.add_paragraph('Scripture to Keep in Mind')
        doc.add_paragraph('Example scripture\nExample 1:1')
        doc.add_paragraph('AS YOU WATCH OR READ\nExample focus')
        p = doc.sections[0].footer.paragraphs[0]
        p.add_run('Example Series | EPISODE 1')
    else:
        for value in ('Example Title', 'A Word Study on Matthew 1:1', 'Example passage',
                      'Example introduction', '1. Example', 'Greek: example — meaning'):
            doc.add_paragraph(value)
        table = doc.add_table(rows=2, cols=2)
        for cell, value in zip([c for r in table.rows for c in r.cells],
                               ['OLD TESTAMENT', 'NEW TESTAMENT', 'Example 1:1 — explanation', 'Example 2:1 — explanation']):
            cell.text = value
        for value in ('In Matthew 1:1: Example context', 'Putting It Together', 'Example synthesis', 'For further reading: Example'):
            doc.add_paragraph(value)
        doc.sections[0].footer.paragraphs[0].text = 'Standing attribution'
    doc.save(path)


def plan(kind):
    return dict(kind=kind, sermon='Matt 1:1', topic='Example Series (1) Example Topic', study_words=['Example'])


def authored(kind):
    if kind == 'discussion':
        return dict(series='Example Series', episode='2', episode_title='New Topic', presenter='New presenter',
                    purpose='New purpose', focus='New focus',
                    points=[dict(lead=f'New point {i}.', text=f'New explanation {i}.') for i in range(5)],
                    questions=[dict(lead=f'New question {i}?', text=f'New follow-up {i}?') for i in range(5)],
                    scripture=[dict(reference=f'New {i}:1', text=f'New scripture {i}') for i in range(3)])
    word = dict(word='First', language='Greek', term='term', meaning='New meaning', context='New context',
                old_testament=[dict(reference='Old 1:1', text='Old explanation')],
                new_testament=[dict(reference='New 1:1', text='New explanation')])
    return dict(title='New title', passage_reference='Matthew 1:2', passage_text='New passage', translation='NIV',
                introduction='New introduction', summary='New summary', further_reading='New reading',
                words=[word, dict(deepcopy(word), word='Second')])


class HandoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_matching_source_is_byte_identical_and_wrong_subject_rejected(self):
        for kind in ('word-study', 'discussion'):
            source = self.root / (kind + '.docx')
            template(source, kind)
            service = plan(kind)
            selected = handouts.prepare(service, {}, [self.root])
            out = self.root / (kind + '-out.docx')
            content = {'_handout_source': selected}
            if kind == 'word-study':
                content['_verified_word_content'] = handouts.verified_word_content(service, content, lambda ref: 'Verified fixture text for ' + ref)
            handouts.generate(service, content, out)
            if kind == 'discussion':
                self.assertEqual(source.read_bytes(), out.read_bytes())
            else:
                self.assertNotIn('Greek:', '\n'.join(p.text for p in Document(out).paragraphs))
                self.assertIn('Verified fixture text', Document(out).tables[0].cell(1, 0).text)
            service['sermon'] = 'Matt 1:2'
            service['topic'] = 'Example Series (2) Example Topic'
            with self.assertRaisesRegex(ValueError, 'No matching authored'):
                handouts.prepare(service, {}, [self.root])

    def test_authored_mapping_preserves_package_and_replaces_old_teaching(self):
        for kind in ('word-study', 'discussion'):
            source = self.root / (kind + '.docx')
            template(source, kind)
            data, service = authored(kind), plan(kind)
            service.update(sermon='Matt 1:2', topic='Example Series (2) New Topic', study_words=['First', 'Second'])
            selected = handouts.prepare(service, dict(handout_template=str(source), handout_content=data), [])
            out = self.root / (kind + '-out.docx')
            content = {'_handout_source': selected, 'handout_content': data}
            if kind == 'word-study':
                content['_verified_word_content'] = handouts.verified_word_content(service, content, lambda ref: 'Verified fixture text for ' + ref)
            handouts.generate(service, content, out)
            with ZipFile(source) as before, ZipFile(out) as after:
                for name in before.namelist():
                    if name == 'word/document.xml' or (kind == 'discussion' and name.startswith('word/footer')):
                        continue
                    self.assertEqual(before.read(name), after.read(name), name)
                rendered_text = handouts.text(handouts.etree.fromstring(after.read('word/document.xml')))
                self.assertNotIn('Example context', rendered_text)
                self.assertNotIn('Example focus', rendered_text)
                self.assertNotIn('New context', rendered_text)
                if kind == 'discussion':
                    self.assertIn('New focus', rendered_text)
                if kind == 'word-study':
                    self.assertEqual(len(Document(out).tables), 2)
                    study = Document(out)
                    self.assertEqual(study.paragraphs[0].runs[0].font.size.pt, 16)
                    for table in study.tables:
                        for cell in table.rows[1].cells:
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    self.assertEqual(run.font.size.pt, 14)
                    self.assertIn('Second', rendered_text)
                    self.assertNotIn('Greek:', rendered_text)
                    self.assertNotIn('New meaning', rendered_text)
                    self.assertNotIn('Old explanation', rendered_text)
                    self.assertNotIn('New passage', rendered_text)
                    self.assertIn('Verified fixture text for Matthew 1:2', rendered_text)
                else:
                    self.assertIn('EPISODE 2', Document(out).sections[0].footer.paragraphs[0].text)
                    self.assertIn('New scripture 2', rendered_text)

    def test_missing_material_words_and_ambiguous_sources(self):
        self.assertNotEqual(handouts.reference('Matt 1:12'), handouts.reference('Matthew 1:1-2'))
        self.assertNotEqual(handouts.reference('Matt 11:2'), handouts.reference('Matthew 1:12'))
        self.assertEqual(handouts.reference('Matt. 1:1–2'), handouts.reference('Matthew 1:1-2'))
        source = self.root / 'study.docx'
        template(source, 'word-study')
        service = plan('word-study')
        service['study_words'] = ['Different']
        with self.assertRaisesRegex(ValueError, 'No matching authored'):
            handouts.prepare(service, {}, [self.root])
        data = authored('word-study')
        del data['words'][0]['word']
        service.update(sermon='Matt 1:2', study_words=['First', 'Second'])
        with self.assertRaisesRegex(ValueError, 'word'):
            handouts.validate(data, service)
        other = self.root / 'other.docx'
        doc = Document(source)
        doc.paragraphs[0].text = 'Another title'
        doc.save(other)
        with self.assertRaisesRegex(ValueError, 'Multiple handout sources'):
            handouts.prepare(plan('word-study'), {}, [self.root])

    def test_word_study_cannot_bypass_niv_verification_and_preserves_run_roles(self):
        source = self.root / 'study.docx'
        template(source, 'word-study')
        service = plan('word-study')
        with self.assertRaisesRegex(ValueError, 'NIV verification'):
            handouts.generate(service, {'_handout_source': source}, self.root / 'unverified.docx')
        doc = Document(source)
        p = doc.tables[0].cell(1, 0).paragraphs[0]
        p.clear()
        p.add_run('')
        p.add_run('Reference — ').bold = True
        p.add_run('Quotation').bold = False
        handouts.fill(p._p, ['New reference — ', 'Exact text'])
        self.assertTrue(p.runs[0].bold)
        self.assertFalse(p.runs[1].bold)

    def test_excerpts_must_match_exact_source_and_complete_words(self):
        service = plan('word-study')
        service.update(sermon='Matt 1:2', study_words=['First', 'Second'])
        data = authored('word-study')
        entry = data['words'][0]['old_testament'][0]
        entry['reference'] = 'Old 1:1-2'
        entry['excerpt'] = 'Exact fixture quotation'
        content = {'handout_content': data}
        lookup = lambda ref: 'Opening words. Exact fixture quotation. Closing words.'
        verified = handouts.verified_word_content(service, content, lookup)
        self.assertEqual(verified['words'][0]['old_testament'][0]['text'], entry['excerpt'])
        for bad in ('Interpreted fixture quotation', 'exact fixture quotation', 'fixture quot', 'Exact ... quotation', ''):
            entry['excerpt'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                handouts.verified_word_content(service, content, lookup)

    def test_single_verse_is_complete_and_generated_study_has_no_commentary(self):
        source = self.root / 'study.docx'
        template(source, 'word-study')
        service = plan('word-study')
        service.update(sermon='Matt 1:2', study_words=['First', 'Second'])
        data = authored('word-study')
        data['words'][0]['old_testament'][0]['excerpt'] = 'short selection'
        content = {'_handout_source': source, 'handout_content': data}
        full = 'The complete fixture verse with its closing words.'
        content['_verified_word_content'] = handouts.verified_word_content(service, content, lambda ref: full)
        entry = content['_verified_word_content']['words'][0]['old_testament'][0]
        self.assertEqual(entry['text'], full)
        self.assertNotIn('excerpt', entry)
        output = self.root / 'generated.docx'
        handouts.generate(service, content, output)
        with ZipFile(output) as package:
            text = handouts.text(handouts.etree.fromstring(package.read('word/document.xml')))
        for forbidden in ('Commentary', 'New introduction', 'New context', 'New summary', 'Putting It Together', 'Greek:'):
            self.assertNotIn(forbidden, text)
        regenerated = handouts.verified_word_content(service, {'_handout_source': output}, lambda ref: full)
        self.assertEqual(len(regenerated['words']), 2)

    def test_cli_independent_outputs_multipage_export_and_stale_archive(self):
        """Run the real entry point against synthetic inputs; only Word is simulated."""
        fixture = self.root / 'fixture'
        previous = fixture / 'work/desktop/previous'
        previous.mkdir(parents=True)
        for kind in ('word-study', 'discussion'):
            template(previous / (kind + '.docx'), kind)
        (fixture / 'work/input-state.json').write_text(json.dumps({'date': '2026-09-27'}))
        # Bootstrap replaces gather (workbook/network I/O) and native Word export only.
        bootstrap = self.root / 'sitecustomize.py'
        bootstrap.write_text('''
import os
from pathlib import Path
from kenton_workflow import automation as a, handouts
from pypdf import PdfWriter
a.ROOT = Path(os.environ['FIXTURE_ROOT'])
if os.environ.get('LOCK_STUDY'):
    original_rename = Path.rename
    def locked_rename(self, target):
        if self.name == '2026-09-27-morning-word-study.pdf':
            raise PermissionError('Synthetic open PDF')
        return original_rename(self, target)
    Path.rename = locked_rename
def gather(root, day, offline, chords):
    p = a.paths(root, day)
    plans = {}
    prepared = {}
    for name, kind in [('morning', 'word-study'), ('evening', 'discussion')]:
        s = dict(kind=kind, sermon='Matt 1:1', topic='Example Series (1) Example Topic', study_words=['Example'], praise_songs=[])
        e = dict(service=name, chord_source_error='Synthetic unavailable source')
        if not (name == 'morning' and os.environ.get('MISSING_STUDY')):
            e['_handout_source'] = handouts.prepare(s, {}, [p['desktop'] / 'previous'])
            if kind == 'word-study':
                e['_verified_word_content'] = handouts.verified_word_content(s, e, lambda ref: 'Verified fixture text for ' + ref)
        if os.environ.get('ALL_SUCCESS'):
            from docx import Document
            s.update(praise_songs=['Fixture song'], call_to_worship='Example 1:1')
            chord = root / 'work/fixture-chord.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with chord.open('wb') as f: writer.write(f)
            e.update(chord_source_error=None, chords=[chord], template='fixture', prayer='Fixture prayer',
                     call_lines=['Fixture reading'], translation='NIV', call_reference='Example 1:1')
            def bulletin(template, service, content, day, target):
                Document().save(target)
            a.bulletin = bulletin
        plans[name], prepared[name] = s, e
    return p, {}, plans, prepared, []
def export(path):
    writer = PdfWriter()
    pages = 1 if 'word-study' in path.name and not os.environ.get('OVERSIZE_STUDY') else 2
    for _ in range(pages): writer.add_blank_page(width=612, height=792)
    pdf = path.with_suffix('.pdf')
    with pdf.open('wb') as f: writer.write(f)
    return pdf
a.gather, a.export_word = gather, export
''')
        env = dict(os.environ, FIXTURE_ROOT=str(fixture), PYTHONPATH=os.pathsep.join([str(self.root), str(ROOT / 'src')]))
        command = [sys.executable, str(ROOT / 'scripts/update-automation.py'), '--offline']
        run = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        build = json.loads((fixture / 'work/build.json').read_text())
        self.assertIn('2026-09-27-morning-word-study.pdf', build['files'])
        self.assertFalse(any('one page' in note for note in build['attention']))
        self.assertFalse(build['complete'])  # Independent bulletin failures remain visible.
        self.assertIn('_archive', build['working_files'])
        self.assertFalse(list((fixture / 'work').glob('.update-*')))
        env['LOCK_STUDY'] = '1'
        run = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        build = json.loads((fixture / 'work/build.json').read_text())
        self.assertIn('morning handout', build['failed_outputs'])
        self.assertIn('2026-09-27-evening-discussion.pdf', build['files'])
        self.assertTrue(any('Close the open review file' in item for item in build['attention']))
        del env['LOCK_STUDY']
        env['MISSING_STUDY'] = '1'
        run = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertFalse((fixture / 'work/output/2026-09-27-morning-word-study.pdf').exists())
        self.assertTrue((fixture / 'work/output/2026-09-27-evening-discussion.pdf').exists())
        self.assertTrue(list((fixture / 'work/_archive').rglob('2026-09-27-morning-word-study.pdf')))
        del env['MISSING_STUDY']
        env['ALL_SUCCESS'] = '1'
        run = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        build = json.loads((fixture / 'work/build.json').read_text())
        self.assertTrue(build['complete'], build['attention'])
        self.assertIsNone(build['working_files'])
        self.assertFalse(list((fixture / 'work').glob('.update-*')))
        self.assertTrue((fixture / 'work/output/2026-09-27-morning-word-study.pdf').exists())
        env['OVERSIZE_STUDY'] = '1'
        run = subprocess.run(command, env=env, capture_output=True, text=True)
        build = json.loads((fixture / 'work/build.json').read_text())
        self.assertFalse(build['complete'])
        self.assertIn('morning handout', build['failed_outputs'])
        self.assertTrue(any('must fit on one page' in note for note in build['attention']))
        self.assertIn('2026-09-27-evening-discussion.pdf', build['files'])


if __name__ == '__main__':
    unittest.main()

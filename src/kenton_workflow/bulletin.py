"""Narrow adapter for the retained Kenton morning bulletin layout."""
from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import openpyxl

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def build_morning(snapshot, template, catalog, output, liturgy=None, sermon_title=None):
    """Produce an unapproved review copy; retain all untouched ZIP parts exactly."""
    plan = json.loads(Path(snapshot).read_text(encoding='utf-8'))
    if plan.get('issues'):
        raise ValueError('Resolve planner issues before bulletin generation.')
    day = date.fromisoformat(plan['date'])
    morning = plan['morning']
    def field(name):
        result = morning[name]['value']
        if not isinstance(result, str) or not result.strip():
            raise ValueError(f'Missing morning {name}')
        return result.strip()
    def selection(name):
        values = [v['value'] for v in morning[name] if v['value']]
        if len(values) != 3:
            raise ValueError('This template adapter requires exactly three praise songs and three hymns.')
        return values
    praise, hymns = selection('praise_songs'), selection('hymns')
    if liturgy is None:
        raise ValueError('Responsive call-to-worship text is required; a reading instruction is not a substitute.')
    responsive = json.loads(Path(liturgy).read_text(encoding='utf-8'))
    if responsive.get('reference', '').strip() != field('call_to_worship'):
        raise ValueError('Responsive reading reference must match the weekly plan.')
    lines = responsive.get('lines', [])
    if not lines or any(not isinstance(line, dict) or line.get('speaker') not in ('Leader', 'People', 'All')
                        or not isinstance(line.get('text'), str) or not line['text'].strip() for line in lines):
        raise ValueError('Responsive reading requires speaker/text entries for Leader, People, or All.')
    if not responsive.get('translation'):
        raise ValueError('Identify the Bible translation for the responsive reading.')
    reference = field('prayer_of_confession')
    book = openpyxl.load_workbook(catalog, read_only=True, data_only=False)
    try:
        matches = [row[3] for row in book['PrayerOfConfession'].iter_rows(min_row=2, values_only=True)
                   if len(row) > 3 and isinstance(row[1], str) and row[1].strip() == reference]
    finally:
        book.close()
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0].strip() or matches[0].startswith('='):
        raise ValueError('Expected one supplied confession prayer matching the planner reference.')
    with ZipFile(template) as source:
        raw = source.read('word/document.xml')
        # lxml preserves original namespace declarations and untouched structures.
        from lxml import etree
        document = etree.fromstring(raw)
        body = document.find(W+'body')
        paragraphs = body.findall(W+'p')
        def text(node): return ''.join(node.xpath('.//w:t/text()', namespaces={'w': W[1:-1]}))
        anchors = {4: 'Kenton Church', 9: 'CALL TO WORSHIP', 11: 'PRAISE MUSIC',
                   18: '* HYMN', 19: 'SCRIPTURE', 20: 'PRAYER OF CONFESSION',
                   31: '* HYMN', 37: 'SERMON', 40: '* HYMN'}
        if len(paragraphs) != 71 or any(not text(paragraphs[i]).startswith(prefix) for i,prefix in anchors.items()):
            raise ValueError('Template layout differs from the verified adapter; review mapping first.')
        def replace(paragraph, value):
            runs = paragraph.findall(W+'r')
            base = deepcopy(runs[0]) if runs else etree.Element(W+'r')
            for child in list(base):
                if child.tag != W+'rPr': base.remove(child)
            node = etree.SubElement(base, W+'t'); node.text = value
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            for child in list(paragraph):
                if child.tag != W+'pPr': paragraph.remove(child)
            paragraph.append(base)
        replacements = {
            5: f'{day.strftime("%B")} {day.day}, {day.year} - Morning',
            9: f'CALL TO WORSHIP ({field("call_to_worship")} - {responsive["translation"]})',
            12: praise[0], 13: praise[1], 14: praise[2],
            18: '* HYMN - '+hymns[0], 19: '',
            21: matches[0].strip(), 23: '', 25: '', 26: 'From '+reference,
            31: '* HYMN - '+hymns[1],
            37: 'SERMON - '+str(morning['sermon']['source_text']['value'] or ''),
            38: sermon_title or str(morning['sermon']['topic']['value'] or ''),
            40: '* HYMN - '+hymns[2],
        }
        if not morning['sermon']['source_text']['value'] or not morning['sermon']['topic']['value']:
            raise ValueError('Morning sermon reference and topic are required.')
        if any(v['value'] for v in plan.get('unassigned_readings', [])):
            raise ValueError('Assign additional readings before generating this bulletin.')
        for i,value in replacements.items(): replace(paragraphs[i], value)
        tables = body.findall(W+'tbl')
        if len(tables) != 1 or len(tables[0].findall(W+'tr')) != 5:
            raise ValueError('Expected the five-row call-to-worship table.')
        rows = tables[0].findall(W+'tr')
        for row in rows: tables[0].remove(row)
        for line in lines:
            # Preserve the reference table's widths and cell/paragraph formatting.
            row = deepcopy(rows[1] if line['speaker'] == 'People' else rows[0])
            cells = row.findall(W+'tc')
            replace(cells[0].find(W+'p'), line['speaker'])
            replace(cells[1].find(W+'p'), line['text'].strip())
            tables[0].append(row)
        # The old file started with blank paragraphs and a page break before its title.
        # Remove only that leading blank-page scaffolding; keep later service breaks.
        for paragraph in paragraphs[:4]:
            if text(paragraph).strip():
                raise ValueError('Unexpected content before the title; review template.')
            body.remove(paragraph)
        for br in paragraphs[4].xpath('.//w:br | .//w:lastRenderedPageBreak', namespaces={'w': W[1:-1]}):
            br.getparent().remove(br)
        # Remove obsolete empty spacing paragraphs in the shortened prayer block.
        for i in (22, 23, 24, 25): body.remove(paragraphs[i])
        payload = BytesIO()
        with ZipFile(payload, 'w') as target:
            for info in source.infolist():
                target.writestr(info, etree.tostring(document, xml_declaration=True, encoding='UTF-8', standalone=True)
                                if info.filename == 'word/document.xml' else source.read(info.filename))
    destination = Path(output)
    if destination.suffix.lower() != '.docx': raise ValueError('Output must be a DOCX file.')
    from kenton_workflow.sync import checked_path
    destination = checked_path(destination)
    work = checked_path(Path.cwd() / 'work')
    if work not in destination.parents: raise ValueError('Output must be under this repository work/ folder.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream: stream.write(payload.getvalue())
    return {'output': str(destination), 'status': 'unapproved; visual review required',
            'review': ['Call to worship uses supplied responsive lines and translation.',
                       'Confirm the published sermon title.',
                       'Preacher was removed because the plan does not specify one.',
                       'Other standing service text is retained from the template; confirm it still applies.']}

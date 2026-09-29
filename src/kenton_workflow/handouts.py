"""Read authored studies and fill their retained Word components; never invent teaching."""
from copy import deepcopy
from pathlib import Path
import re
import shutil
from zipfile import BadZipFile, ZipFile

from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = {'w': W[1:-1]}


def text(element):
    return ''.join(element.itertext()) if element.tag == W + 't' else ''.join(element.xpath('.//w:t/text()', namespaces=NS))


def key(value):
    return re.sub(r'[^a-z0-9]', '', str(value).casefold())


def reference(value):
    value = str(value).casefold().replace('–', '-').replace('—', '-')
    value = re.sub(r'\bmatt?\.?\s*(?=\d)', 'matthew ', value)
    # Keep chapter/verse separators and ranges: 1:12 is not 1:1-2 or 11:2.
    return re.sub(r'[\s.]', '', value)


def read_template(path, kind):
    """Recognize the two supplied patterns by their actual section structure."""
    with ZipFile(path) as package:
        tree = etree.fromstring(package.read('word/document.xml'))
    body = tree.find(W + 'body')
    blocks = list(body)
    strings = [text(b) for b in blocks]
    if kind == 'discussion':
        points = strings.index('Five Points to Watch For')
        questions = strings.index('Five Questions for Reflection')
        scripture = strings.index('Scripture to Keep in Mind')
        focus = next(i for i, s in enumerate(strings) if s.startswith('AS YOU WATCH OR READ'))
        point_slots = [i for i in range(points + 1, questions) if strings[i].strip()]
        question_slots = [i for i in range(questions + 1, scripture)
                          if strings[i].strip() and not strings[i].startswith('_')]
        scripture_slots = [i for i in range(scripture + 1, focus) if strings[i].strip()]
        if len(point_slots) != 5 or len(question_slots) != 5 or not scripture_slots:
            raise ValueError('Expected five teaching points, five questions, and Scripture.')
        episode = re.fullmatch(r'EPISODE\s+(\d+)\s*/\s*(.+)', strings[1], re.I)
        if not episode or not strings[3].startswith('Purpose:'):
            raise ValueError('Missing episode identity or purpose.')
        slots = dict(points=point_slots, questions=question_slots, scripture=scripture_slots, focus=focus)
        identity = dict(series=strings[0], episode=episode[1], episode_title=episode[2])
    else:
        if not strings[1].startswith('A Word Study on '):
            raise ValueError('Missing Word study passage heading.')
        further = next((i for i, s in enumerate(strings) if s.startswith('For further reading:')), None)
        summary = strings.index('Putting It Together') if 'Putting It Together' in strings else (further or len(blocks) - 1)
        starts = [i for i in range(3, summary) if re.match(r'^\d+\.\s+', strings[i])]
        if not starts:
            raise ValueError('Expected numbered word sections.')
        tables = []
        for i in starts:
            # Retained sources may contain a legacy Greek paragraph. Recognize
            # it for reading, but never carry it into a newly generated study.
            table = i + 1 if blocks[i + 1].tag == W + 'tbl' else i + 2
            if table >= summary or blocks[table].tag != W + 'tbl':
                raise ValueError('Expected a two-Testament table.')
            tables.append(table)
            cells = blocks[table].xpath('./w:tr/w:tc', namespaces=NS)
            if len(cells) != 4 or 'OLD TESTAMENT' not in text(cells[0]) or 'NEW TESTAMENT' not in text(cells[1]):
                raise ValueError('Expected paired Old/New Testament columns.')
            if any(not text(c).strip() for c in cells[2:]):
                raise ValueError('Missing cross-reference material.')
        slots = dict(words=starts, tables=tables, summary=summary, further=further)
        identity = dict(passage=strings[1].removeprefix('A Word Study on '),
                        words=[re.sub(r'^\d+\.\s+', '', strings[i]) for i in starts])
    return tree, body, slots, identity


def matches(identity, service):
    if service['kind'] == 'word-study':
        return (reference(identity['passage']) == reference(service['sermon']) and
                [key(w) for w in identity['words']] == [key(w) for w in service['study_words']])
    topic = service['topic']
    episode = re.search(r'\((\d+)\)|\bepisode\s+(\d+)\b', topic, re.I)
    if not episode:
        return False
    series = topic[:episode.start()].strip(' -:/')
    title = topic[episode.end():].strip(' -:/')
    return (key(series) == key(identity['series']) and
            str(int(episode[1] or episode[2])) == str(int(identity['episode'])) and
            key(title) == key(identity['episode_title']))


def prepare(service, content, folders):
    """Choose a unique matching authored DOCX, or an explicit template plus authored fields."""
    authored = content.get('handout_content')
    if authored and not content.get('handout_template'):
        raise ValueError('Authored handout_content needs an explicit handout_template DOCX path.')
    explicit = content.get('handout_template') if authored else content.get('handout_source')
    candidates = [Path(explicit)] if explicit else sorted({p for folder in folders if folder.is_dir()
                   for p in folder.rglob('*.docx') if not p.name.startswith('~$')})
    selected = []
    for path in candidates:
        try:
            _, _, _, identity = read_template(path, service['kind'])
        except (ValueError, StopIteration, IndexError, KeyError, BadZipFile, etree.XMLSyntaxError) as error:
            if explicit:
                raise ValueError(f'Unsupported handout template "{path}": {error}') from error
            continue
        if authored or matches(identity, service):
            selected.append(path)
    if not selected:
        raise ValueError('No matching authored Word handout. AI/Codex must prepare the current '
                         'teaching material in a retained DOCX, or supply handout_template and '
                         'handout_content in work/desktop/content.json. Generic worksheets are not substituted.')
    # Identical retained copies are equivalent; differing versions require explicit selection.
    import hashlib
    unique = {}
    for p in selected:
        unique.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
    if len(unique) != 1:
        raise ValueError('Multiple handout sources match; select handout_source (or handout_template '
                         'with authored content): ' + ', '.join(str(p) for p in selected))
    chosen = next(iter(unique.values()))
    if authored:
        validate(authored, service)
    return chosen


def validate(data, service):
    """Validate the explicit author-to-assembler handoff before creating any file."""
    def required(obj, names):
        if not isinstance(obj, dict):
            raise ValueError('Handout content must contain named fields.')
        for name in names:
            if not isinstance(obj.get(name), str) or not obj[name].strip():
                raise ValueError(f'Authored handout content needs {name}.')
    def records(name, fields, count=None, owner=None):
        owner = data if owner is None else owner
        values = owner.get(name)
        if not isinstance(values, list) or not values or (count is not None and len(values) != count):
            raise ValueError(f'Authored handout needs {count or "one or more"} {name}.')
        for value in values:
            required(value, fields)
        return values
    if service['kind'] == 'discussion':
        required(data, ('series', 'episode', 'episode_title', 'presenter', 'purpose', 'focus'))
        if not matches(data, service):
            raise ValueError('Authored episode/series/title does not match the planner.')
        records('points', ('lead', 'text'), 5)
        records('questions', ('lead', 'text'), 5)
        records('scripture', ('reference', 'text'))
    else:
        required(data, ('title', 'passage_reference', 'translation'))
        if data.get('body_font_size', 14) not in (13, 14):
            raise ValueError('Word-study body_font_size must be 14, or 13 when needed to fit one page.')
        if data['translation'] != 'NIV' or reference(data['passage_reference']) != reference(service['sermon']):
            raise ValueError('Authored NIV passage must match the planner.')
        words = records('words', ('word',))
        if [key(w['word']) for w in words] != [key(w) for w in service['study_words']]:
            raise ValueError('Authored words must match planner Study-words in order.')
        for word in words:
            records('old_testament', ('reference',), owner=word)
            records('new_testament', ('reference',), owner=word)


def verified_word_content(service, content, lookup):
    """Use authored reference choices, but fetch ALL Scripture verbatim.

    lookup is the NIV source reader, not an AI author. Neither legacy DOCX
    summaries nor supplied JSON verse text is trusted as the Scripture source.
    """
    data = deepcopy(content.get('handout_content'))
    if not data:
        _, body, slots, identity = read_template(content['_handout_source'], 'word-study')
        if not matches(identity, service):
            raise ValueError('Handout source no longer matches the planner.')
        blocks = list(body)
        data = dict(title=text(blocks[0]), passage_reference=identity['passage'], translation='NIV',
                    further_reading=text(blocks[slots['further']]).removeprefix('For further reading: ') if slots['further'] is not None else '', words=[])
        for word, table in zip(identity['words'], slots['tables']):
            item = dict(word=word)
            cells = blocks[table].xpath('./w:tr/w:tc', namespaces=NS)[2:]
            for cell, field in zip(cells, ('old_testament', 'new_testament')):
                item[field] = []
                for paragraph in cell.findall(W + 'p'):
                    line = text(paragraph).strip()
                    if not line:
                        continue
                    parts = re.split(r'\s+[—–]\s+', line, maxsplit=1)
                    if len(parts) != 2:
                        raise ValueError(f'Cannot identify a Scripture reference in the retained table: {line}')
                    entry = {'reference': re.sub(r' \(NIV(?: excerpt)?\)$', '', parts[0])}
                    if parts[0].endswith(' (NIV excerpt)'):
                        entry['excerpt'] = parts[1]
                    item[field].append(entry)
            data['words'].append(item)
    validate(data, service)
    data['passage_text'] = lookup(data['passage_reference'])
    for word in data['words']:
        for field in ('old_testament', 'new_testament'):
            for item in word[field]:
                item['text'] = lookup(item['reference'])
                if not isinstance(item['text'], str) or not item['text'].strip():
                    raise ValueError(f'Exact NIV text is missing for {item["reference"]}.')
                if re.search(r':\s*\d+\s*$', item['reference']):
                    # A single-verse citation always prints the entire verse,
                    # even when older authored content contains an excerpt.
                    item.pop('excerpt', None)
                if 'excerpt' in item:
                    excerpt = item['excerpt']
                    if not isinstance(excerpt, str) or not excerpt.strip():
                        raise ValueError(f'Empty NIV excerpt for {item["reference"]}.')
                    excerpt = ' '.join(excerpt.split())
                    full = ' '.join(item['text'].split())
                    if not re.search(r'(?<!\w)' + re.escape(excerpt) + r'(?!\w)', full):
                        raise ValueError(f'Excerpt for {item["reference"]} is not an exact, contiguous NIV quotation. '
                                         'AI/user must correct the quotation; no paraphrase was used.')
                    item['text'] = excerpt
    if not isinstance(data['passage_text'], str) or not data['passage_text'].strip():
        raise ValueError('Exact NIV passage text is missing.')
    return data


def fill(paragraph, pieces):
    """Replace text using the existing run formats (e.g. bold lead, regular explanation)."""
    # Empty leading runs in retained table cells must not shift the bold
    # reference style onto the quotation or lose its regular body style.
    runs = [r for r in paragraph.findall(W + 'r') if any(t.text for t in r.iter(W + 't'))]
    formats = [deepcopy(r.find(W + 'rPr')) for r in runs]
    for child in list(paragraph):
        if child.tag != W + 'pPr':
            paragraph.remove(child)
    for i, value in enumerate(pieces):
        run = etree.SubElement(paragraph, W + 'r')
        if formats:
            fmt = formats[min(i, len(formats) - 1)]
            if fmt is not None:
                run.append(deepcopy(fmt))
        for j, line in enumerate(value.split('\n')):
            if j:
                etree.SubElement(run, W + 'br')
            node = etree.SubElement(run, W + 't')
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            node.text = line


def font_size(element, points):
    """Explicit reader-approved sizing overrides small retained template runs."""
    for run in element.iter(W + 'r'):
        properties = run.find(W + 'rPr')
        if properties is None:
            properties = etree.Element(W + 'rPr')
            run.insert(0, properties)
        for tag in ('sz', 'szCs'):
            size = properties.find(W + tag)
            if size is None:
                size = etree.SubElement(properties, W + tag)
            size.set(W + 'val', str(points * 2))


def generate(service, content, destination):
    source = Path(content['_handout_source'])
    data = content.get('handout_content')
    if service['kind'] == 'word-study':
        data = content.get('_verified_word_content')
        if not data:
            raise ValueError('Exact NIV verification is required before generating a word study.')
    tree, body, slots, identity = read_template(source, service['kind'])
    if not data:
        if not matches(identity, service):
            raise ValueError('Handout source no longer matches the planner.')
        shutil.copyfile(source, destination)
        return
    validate(data, service)
    blocks = list(body)
    changed = {}
    if service['kind'] == 'discussion':
        fill(blocks[0], [data['series']])
        fill(blocks[1], [f'EPISODE {data["episode"]}  /  {data["episode_title"]}'])
        fill(blocks[2], [data['presenter'] + '  •  Study & Discussion Handout'])
        fill(blocks[3], ['Purpose: ', data['purpose']])
        for section in ('points', 'questions'):
            for i, item in zip(slots[section], data[section]):
                fill(blocks[i], [item['lead'].rstrip() + ' ', item['text']])
        for item in data['scripture']:
            paragraph = deepcopy(blocks[slots['scripture'][0]])
            fill(paragraph, [item['text'] + '\n', '— ' + item['reference']])
            body.insert(body.index(blocks[slots['scripture'][0]]), paragraph)
        for i in slots['scripture']:
            body.remove(blocks[i])
        fill(blocks[slots['focus']], ['AS YOU WATCH OR READ\n', data['focus']])
        with ZipFile(source) as package:
            for name in package.namelist():
                if re.fullmatch(r'word/footer\d+\.xml', name):
                    footer = etree.fromstring(package.read(name))
                    for node in footer.xpath('.//w:t', namespaces=NS):
                        if node.text:
                            node.text = node.text.replace(identity['series'], data['series'])
                            node.text = re.sub(r'EPISODE\s+\d+', 'EPISODE ' + data['episode'], node.text)
                    changed[name] = etree.tostring(footer, xml_declaration=True, encoding='UTF-8', standalone=True)
    else:
        fill(blocks[0], [data['title']])
        fill(blocks[1], ['A Word Study on ' + data['passage_reference']])
        fill(blocks[2], [data['passage_text'] + '\n', data['passage_reference'] + ', NIV'])
        body_size = data.get('body_font_size', 14)
        font_size(blocks[0], 16)
        font_size(blocks[1], 11)
        font_size(blocks[2], body_size)
        first = slots['words'][0]
        for number, word in enumerate(data['words'], 1):
            heading = deepcopy(blocks[first])
            table = deepcopy(blocks[slots['tables'][0]])
            header = table.find(W + 'tr')
            properties = header.find(W + 'trPr')
            if properties is None:
                properties = etree.SubElement(header, W + 'trPr')
            if properties.find(W + 'tblHeader') is None:
                etree.SubElement(properties, W + 'tblHeader')
            fill(heading, [f'{number}. {word["word"]}'])
            font_size(heading, 16)
            font_size(header, 11)
            cells = table.xpath('./w:tr/w:tc', namespaces=NS)[2:]
            for cell, field in zip(cells, ('old_testament', 'new_testament')):
                sample = cell.find(W + 'p')
                for p in list(cell.findall(W + 'p')):
                    cell.remove(p)
                for item in word[field]:
                    p = deepcopy(sample)
                    label = ' (NIV excerpt) — ' if 'excerpt' in item else ' (NIV) — '
                    fill(p, [item['reference'] + label, item['text']])
                    font_size(p, body_size)
                    cell.append(p)
            for b in (heading, table):
                body.insert(body.index(blocks[first]), b)
        for i, b in enumerate(blocks[3:], 3):
            if b.tag == W + 'sectPr':
                continue
            if i == slots['further'] and data.get('further_reading'):
                fill(b, ['For further reading: ' + data['further_reading']])
                font_size(b, 11)
            else:
                body.remove(b)
    changed['word/document.xml'] = etree.tostring(tree, xml_declaration=True, encoding='UTF-8', standalone=True)
    # Preserve all opaque package parts and relationships byte-for-byte.
    with ZipFile(source) as original, ZipFile(destination, 'w') as output:
        for entry in original.infolist():
            output.writestr(entry, changed.get(entry.filename, original.read(entry.filename)))

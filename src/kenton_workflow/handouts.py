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


def word_table_cells(table):
    cells = table.xpath('./w:tr/w:tc', namespaces=NS)
    headers = [next((i for i, c in enumerate(cells) if text(c).strip() == label), None)
               for label in ('OLD TESTAMENT', 'NEW TESTAMENT')]
    if None in headers:
        raise ValueError('Expected Old/New Testament table headings.')
    if headers == [0, 1] and len(cells) in (4, 6):
        return [(cells[i+2], cells[i+4] if len(cells) == 6 else cells[i+2]) for i in range(2)]
    mapped = []
    for index in headers:
        if index + 1 >= len(cells):
            raise ValueError('Missing Testament Scripture cell.')
        body = cells[index+1]
        following = cells[index+2] if index+2 < len(cells) else None
        see = following if following is not None and text(following).strip().startswith('See also') else body
        mapped.append((body, see))
    return mapped


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
        passage_heading = next((i for i, s in enumerate(strings[:3]) if s.startswith('A Word Study on ')), None)
        if passage_heading is None:
            raise ValueError('Missing Word study passage heading.')
        further = next((i for i, s in enumerate(strings) if s.startswith('For further reading:')), None)
        summary = strings.index('Putting It Together') if 'Putting It Together' in strings else (further or len(blocks) - 1)
        starts = [i for i in range(passage_heading + 2, summary) if re.match(r'^\d+\.\s+', strings[i])]
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
            if any(not text(c).strip() for c, _ in word_table_cells(blocks[table])):
                raise ValueError('Missing cross-reference material.')
        slots = dict(words=starts, tables=tables, summary=summary, further=further,
                     title=0 if passage_heading == 1 else None, passage_heading=passage_heading, passage_text=passage_heading+1,
                     passage_attribution='[Passage reference]' in strings[passage_heading+1] or bool(re.search(r',\s*NIV\s*$', strings[passage_heading+1])))
        identity = dict(passage=strings[passage_heading].removeprefix('A Word Study on '),
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


def prepare_named(service, content, template_folder, authored_folders):
    """Use the user's named layout; authored documents supply content only."""
    filename = 'word_study_template.docx' if service['kind'] == 'word-study' else 'discussion_template.docx'
    template = Path(template_folder) / filename
    if not template.is_file():
        raise ValueError(f'Missing editable template: "{template}". A PDF is a visual reference, not a Word template.')
    read_template(template, service['kind'])
    content['_preserve_template_format'] = True
    if content.get('handout_content'):
        validate(content['handout_content'], service)
    else:
        # Never interpret the old example text in the layout as this week's teaching.
        try:
            authored = prepare(service, {}, authored_folders)
        except ValueError as error:
            if not str(error).startswith('No matching authored Word handout.'):
                raise
            subject = service['sermon'] if service['kind'] == 'word-study' else service['topic']
            words = ', '.join(service.get('study_words', []))
            detail = f' Study words: {words}.' if words else ''
            raise ValueError(f'Template found: "{template}". Missing current authored teaching content for '
                             f'{subject}.{detail} AI/Codex or the user must supply that content; '
                             'the template itself does not need replacing.') from error
        if service['kind'] == 'word-study':
            content['_word_content_source'] = authored
        else:
            content['handout_content'] = discussion_content(authored)
            validate(content['handout_content'], service)
    return template


def discussion_content(source):
    """Extract existing authored teaching verbatim for mapping into a named layout."""
    _, body, slots, identity = read_template(source, 'discussion')
    blocks = list(body)
    def lines(block):
        return ''.join('\n' if node.tag == W+'br' else (node.text or '')
                       for node in block.iter() if node.tag in (W+'t', W+'br'))
    data = dict(identity, presenter=lines(blocks[2]).split('  ')[0],
                purpose=lines(blocks[3]).removeprefix('Purpose:').strip(),
                focus=lines(blocks[slots['focus']]).removeprefix('AS YOU WATCH OR READ').strip())
    for section in ('points', 'questions'):
        data[section] = []
        for i in slots[section]:
            value = lines(blocks[i])
            lead = ''
            for run in blocks[i].findall(W+'r'):
                if run.find(W+'rPr/'+W+'b') is None:
                    break
                lead += lines(run)
            if not lead.strip() or not value.startswith(lead):
                split = re.match(r'(.+?[.!?])(?:\s+|$)(.*)', value, re.S)
                lead = split[1] if split else value
            data[section].append({'lead': lead.rstrip(), 'text': value[len(lead):].lstrip()})
    data['scripture'] = []
    pending = ''
    for i in slots['scripture']:
        value = lines(blocks[i]).strip()
        quote, separator, ref = value.rpartition('—')
        if separator:
            data['scripture'].append({'reference': ref.strip(), 'text': (pending + quote).strip()})
            pending = ''
        else:
            pending += value + '\n'
    if pending or not data['scripture']:
        raise ValueError(f'Cannot separate the authored Scripture quotations and references in "{source}".')
    return data


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
        for section in ('points', 'questions'):
            for item in records(section, ('lead',), 5):
                if not isinstance(item.get('text'), str):
                    raise ValueError(f'Authored {section} needs text (which may be empty).')
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
        _, body, slots, identity = read_template(content.get('_word_content_source', content['_handout_source']), 'word-study')
        if not matches(identity, service):
            raise ValueError('Handout source no longer matches the planner.')
        blocks = list(body)
        data = dict(title=text(blocks[0]), passage_reference=identity['passage'], translation='NIV',
                    further_reading=text(blocks[slots['further']]).removeprefix('For further reading: ') if slots['further'] is not None else '', words=[])
        for word, table in zip(identity['words'], slots['tables']):
            item = dict(word=word)
            all_cells = blocks[table].xpath('./w:tr/w:tc', namespaces=NS)
            cells = all_cells[2:4]
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
            if len(all_cells) == 6:
                for cell, field in zip(all_cells[4:], ('old_testament', 'new_testament')):
                    value = re.sub(r'^See also[.\s:]*', '', text(cell)).strip().rstrip('.')
                    value = re.sub(r'\s*\(NIV\)\s*$', '', value)
                    if value:
                        item[field + '_see_also'] = [v.strip() for v in value.split(';') if v.strip()]
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
        if slots['title'] is not None:
            fill(blocks[slots['title']], [data['title']])
        fill(blocks[slots['passage_heading']], ['A Word Study on ' + data['passage_reference']])
        passage_parts = [data['passage_text']]
        if slots['passage_attribution']:
            passage_parts = [data['passage_text'] + '\n', data['passage_reference'] + ', NIV']
        fill(blocks[slots['passage_text']], passage_parts)
        body_size = data.get('body_font_size', 14)
        apply_size = (lambda element, points: None) if content.get('_preserve_template_format') else font_size
        apply_size(blocks[0], 16)
        apply_size(blocks[1], 11)
        apply_size(blocks[2], body_size)
        first = slots['words'][0]
        for number, word in enumerate(data['words'], 1):
            slot = min(number - 1, len(slots['words']) - 1)
            heading = deepcopy(blocks[slots['words'][slot]])
            table = deepcopy(blocks[slots['tables'][slot]])
            header = table.find(W + 'tr')
            properties = header.find(W + 'trPr')
            if properties is None:
                properties = etree.SubElement(header, W + 'trPr')
            if properties.find(W + 'tblHeader') is None:
                etree.SubElement(properties, W + 'tblHeader')
            fill(heading, [f'{number}. {word["word"]}'])
            apply_size(heading, 16)
            apply_size(header, 11)
            for (cell, see_cell), field in zip(word_table_cells(table), ('old_testament', 'new_testament')):
                sample = cell.find(W + 'p')
                samples = [p for p in cell.findall(W + 'p') if text(p).strip() and not text(p).startswith('See also')]
                see_sample = next((p for p in see_cell.findall(W+'p') if text(p).startswith('See also')), sample)
                see_sample = deepcopy(see_sample)
                for p in list(cell.findall(W + 'p')):
                    cell.remove(p)
                for index, item in enumerate(word[field]):
                    p = deepcopy(samples[min(index, len(samples) - 1)])
                    label = ' (NIV excerpt) — ' if 'excerpt' in item else ' (NIV) — '
                    fill(p, [item['reference'] + label, item['text']])
                    apply_size(p, body_size)
                    cell.append(p)
                if word.get(field + '_see_also'):
                    p = deepcopy(see_sample)
                    if see_cell is not cell:
                        for old in list(see_cell.findall(W + 'p')):
                            see_cell.remove(old)
                    pattern = data.get('see_also_format', 'See also {references} (NIV)')
                    if pattern.count('{references}') != 1:
                        raise ValueError('see_also_format must contain one {references} placeholder.')
                    fill(p, [pattern.replace('{references}', '; '.join(word[field + '_see_also']))])
                    apply_size(p, body_size)
                    see_cell.append(p)
                elif see_cell is not cell:
                    for old in see_cell.findall(W + 'p'):
                        fill(old, [''])
            for b in (heading, table):
                body.insert(body.index(blocks[first]), b)
        for i, b in enumerate(blocks[slots['passage_text']+1:], slots['passage_text']+1):
            if b.tag == W + 'sectPr':
                continue
            if i == slots['further'] and data.get('further_reading'):
                fill(b, ['For further reading: ' + data['further_reading']])
                apply_size(b, 11)
            else:
                body.remove(b)
    changed['word/document.xml'] = etree.tostring(tree, xml_declaration=True, encoding='UTF-8', standalone=True)
    # Preserve all opaque package parts and relationships byte-for-byte.
    with ZipFile(source) as original, ZipFile(destination, 'w') as output:
        for entry in original.infolist():
            output.writestr(entry, changed.get(entry.filename, original.read(entry.filename)))

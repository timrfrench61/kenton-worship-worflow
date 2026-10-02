"""The three stages in docs/01-kenton-workflow-001.md.

File preparation, document production, and local publication are separate steps.
No old layout profiles, paragraph-spacing engine, or AI API is used.
"""
import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

import openpyxl

from kenton_workflow.planner import extract_week, praise_title
from kenton_workflow import handouts, website
from kenton_workflow.sync import checked_path, GOOGLE_NATIVE_EXTENSIONS

ROOT = Path(__file__).resolve().parents[2]
PLANNING_ROOT = Path(r'G:\My Drive\kenton\_worship')
PUBLISH_ROOT = Path(r'G:\My Drive\kenton\_worship\week-sets')
SERVICES = ('morning', 'evening')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = {'w': W[1:-1]}
NIV_NOTICE = ('Scripture quotations taken from The Holy Bible, New International Version®, NIV®. '
              'Copyright © 1973, 1978, 1984, 2011 by Biblica, Inc.® Used by permission. All rights reserved worldwide.')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    """Replace a generated working file atomically, never a source file."""
    path = checked_path(Path(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(payload)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def copy_file(source, target):
    """Copy bytes only: Drive timestamps are not necessarily valid Windows dates."""
    target = checked_path(Path(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    before = digest(source)
    with Path(source).open('rb') as src, target.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    if digest(source) != before or digest(target) != before:
        raise ValueError(f'File changed while copying: {source}. Retry the input stage.')


def files_under(folder):
    """Do not traverse junctions; ignore OS metadata and Google document pointers."""
    def fail(error):
        raise error
    for directory, dirs, names in os.walk(folder, onerror=fail, followlinks=False):
        for name in dirs:
            checked_path(Path(directory) / name)
        for name in sorted(names):
            path = Path(directory) / name
            if name.lower() in ('desktop.ini', 'thumbs.db') or name.startswith('~$'):
                continue
            if path.suffix.lower() in GOOGLE_NATIVE_EXTENSIONS:
                continue
            yield checked_path(path)


def copy_tree(source, destination):
    for original in files_under(source):
        target = Path(destination) / original.relative_to(source)
        if target.exists():
            if digest(original) != digest(target):
                raise ValueError(f'Existing copy differs: {target}. Keep it or rename it before retrying.')
        else:
            copy_file(original, target)


def paths(root, day):
    root = Path(root)
    return {'desktop': checked_path(root / 'work/desktop'),
            'working': checked_path(root / 'work/desktop'),
            'output': checked_path(root / 'work/output'),
            'weeks': checked_path(root / 'work/week-sets')}


def log(root, message, clear=False):
    location = checked_path(Path(root) / 'work/desktop/automation.log')
    location.parent.mkdir(parents=True, exist_ok=True)
    with location.open('w' if clear else 'a', encoding='utf-8') as f:
        f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n')
    print(message)


def workbook_file(folder, expected):
    normalized = lambda s: re.sub(r'[^a-z0-9]', '', s.casefold())
    found = [p for p in Path(folder).glob('*.xlsx') if normalized(p.stem) == normalized(expected)]
    if len(found) != 1:
        raise ValueError(f'Expected one {expected}.xlsx in {folder}; found {len(found)}.')
    return found[0]


def readable_workbook(source, destination):
    book = openpyxl.load_workbook(source, read_only=True, data_only=False)
    lines = [f'# {source.name}', '', 'Cell addresses identify the original workbook cells.', '']
    try:
        for sheet in book:
            lines += [f'## {sheet.title}', '']
            for row in sheet:
                populated = []
                for cell in row:
                    if cell.value is not None:
                        value = cell.value.isoformat() if isinstance(cell.value, (date, datetime)) else str(cell.value)
                        populated.append(f'{cell.coordinate}: {value.replace(chr(10), " / ")}')
                if populated:
                    lines.append(' | '.join(populated))
            lines.append('')
    finally:
        book.close()
    save(destination, '\n'.join(lines))


def previous_week(weeks, day):
    previous = date.fromisoformat(day) - timedelta(days=7)
    options = [weeks / previous.strftime('%Y%m%d'), weeks / previous.isoformat(),
               weeks / str(previous.year) / previous.isoformat()]
    existing = [p for p in options if p.is_dir()]
    if len(existing) != 1:
        raise ValueError(f'Expected one week-set for {previous}; found {len(existing)}. Use --previous-week with its folder.')
    return existing[0]


def input_automation(root, day, previous=None, planning_root=None):
    p = paths(root, day)
    log(root, f'INPUT — {day}', clear=True)
    save(p['working'] / 'build.json', {'date': day, 'complete': False})
    planning = Path(planning_root) if planning_root is not None else PLANNING_ROOT
    log(root, f'Planning source folder: "{planning}" (read-only; no local fallback)')
    if not planning.is_dir():
        raise ValueError(f'Planning source is unavailable: "{planning}". Connect Google Drive and rerun input.')
    sources = [workbook_file(planning, 'recent logs'), workbook_file(planning, 'Song Lists')]
    source_week = Path(previous).resolve() if previous else previous_week(p['weeks'], day)
    if not source_week.is_dir():
        raise ValueError(f'Last week folder is unavailable: {source_week}')
    template_folder = p['output'] / 'templates'
    if source_week == template_folder or source_week in template_folder.parents or template_folder in source_week.parents:
        raise ValueError('The previous week and template copy must be separate folders.')
    previous_record = p['working'] / 'input.json'
    if previous_record.exists() and not read_json(previous_record).get('planning_root'):
        # Remove the rejected local-source copies from the active desktop, without deleting them.
        old_folder = p['working'] / 'planning'
        archive = checked_path(Path(root) / 'work/_archive/planning-copies' /
                               datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        for old in list(old_folder.glob('*.xlsx')):
            archive.mkdir(parents=True, exist_ok=True)
            checked_path(old).rename(checked_path(archive / old.name))
            export = p['working'] / (old.stem + '.md')
            if export.exists():
                checked_path(export).rename(checked_path(archive / export.name))
            log(root, f'Preserved rejected local-source copy in "{archive / old.name}"')
    planning_files = []
    for source in sources:
        # Refresh machine copies; never write the planning originals.
        target = p['working'] / 'planning' / source.name
        if target.exists() and digest(target) != digest(source):
            archive = checked_path(Path(root) / 'work/_archive/planning-copies' /
                                   datetime.now().strftime('%Y%m%d-%H%M%S-%f') / target.name)
            archive.parent.mkdir(parents=True, exist_ok=True)
            checked_path(target).rename(archive)
            log(root, f'Preserved superseded planning copy: "{archive}"')
        if not target.exists():
            copy_file(source, target)
        readable_workbook(source, p['working'] / f'{source.stem}.md')
        planning_files.append({'source': str(source.resolve()), 'copy': str(target.resolve()),
                               'sha256': digest(source)})
        log(root, f'Planning source: "{source.resolve()}"')
        log(root, f'Planning copy: "{target.resolve()}" (same contents; original filename preserved)')
        log(root, f'Agent reading export: "{p["working"] / (source.stem + ".md")}"')
    inventory = [f'# Week sets available for {day}', '', f'Folder: {p["weeks"]}', '']
    inventory.extend(str(f.relative_to(p['weeks'])) for f in files_under(p['weeks']))
    save(p['working'] / 'week-sets.md', '\n'.join(inventory) + '\n')
    log(root, 'Updated the local week-set inventory for agent reading.')
    copy_tree(source_week, template_folder)
    log(root, f'Copied last week into {template_folder}')
    record = {'date': day, 'planner': str(sources[0]), 'catalog': str(sources[1]),
              'planning_root': str(planning.resolve()),
              'previous_week': str(source_week), 'templates': str(template_folder),
              'planning_files': planning_files}
    save(p['working'] / 'input.json', record)
    save(p['desktop'] / 'current-week.json', {'date': day})
    log(root, f'INPUT complete. Next: python scripts/update-automation.py --date {day}')


def norm(value):
    return re.sub(r'\s+', ' ', str(value).replace('–', '-').replace('—', '-')).strip().casefold()


def confession(catalog, reference):
    book = openpyxl.load_workbook(catalog, read_only=True, data_only=False)
    try:
        matches = [r[3] for r in book['PrayerOfConfession'].iter_rows(min_row=2, values_only=True)
                   if len(r) > 3 and norm(r[1]) == norm(reference)]
    finally:
        book.close()
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0].strip() or matches[0].startswith('='):
        raise ValueError(f'PrayerOfConfession needs one full prayer in column D for {reference}.')
    return matches[0].strip()


def parse_biblegateway(payload):
    """Extract Scripture verse spans, excluding notes, headings and cross references."""
    from lxml import html
    doc = html.fromstring(payload, parser=html.HTMLParser(encoding='utf-8'))
    containers = doc.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " passage-content ")]')
    if len(containers) != 1:
        raise ValueError('Bible Gateway did not return one Scripture passage. Supply the reading in content.json.')
    container = containers[0]
    for node in container.xpath('.//sup|.//h1|.//h2|.//h3|.//h4|.//h5|.//span[@class="chapternum"]'):
        node.drop_tree()
    spans = container.xpath('.//span[contains(concat(" ", normalize-space(@class), " "), " text ")]')
    lines, verse_ids = [], set()
    for span in spans:
        if span.xpath('ancestor::span[contains(concat(" ", normalize-space(@class), " "), " text ")]'):
            continue
        identity = next((c for c in span.get('class', '').split() if re.fullmatch(r'[1-3]?[A-Za-z]+-\d+-\d+', c)), None)
        if not identity:
            continue
        verse_ids.add(identity)
        for br in span.xpath('.//br'):
            br.tail = '\n' + (br.tail or '')
        for line in span.text_content().splitlines():
            clean = re.sub(r'\s+', ' ', line).strip()
            if clean:
                lines.append(clean)
    if not lines:
        raise ValueError('No Scripture verses found on Bible Gateway. Supply the reading in content.json.')
    return lines, sorted(verse_ids)


def bible_reading(reference, cache, offline=False):
    key = hashlib.sha256(reference.encode()).hexdigest()[:16]
    target = cache / f'{key}-NIV.json'
    if target.exists():
        result = read_json(target)
        if result.get('reference') != reference or result.get('translation') != 'NIV' or not result.get('lines'):
            raise ValueError(f'Invalid Scripture cache: {target}')
        return result['lines']
    if offline:
        raise ValueError(f'NIV text for {reference} is not cached. Run without --offline or supply it in content.json.')
    from lxml import html
    url = 'https://www.biblegateway.com/passage/?' + urlencode({'search': reference, 'version': 'NIV'})
    try:
        with urlopen(Request(url, headers={'User-Agent': 'KentonWorshipWorkflow/1.0'}), timeout=25) as response:
            payload = response.read(2_000_000)
        page = html.fromstring(payload, parser=html.HTMLParser(encoding='utf-8'))
        headings = page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " passage-display ")]')
        if not headings or any('New International Version' not in heading.text_content() for heading in headings):
            raise ValueError('The returned page is not labeled New International Version.')
        containers = page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " passage-content ")]')
        if len(containers) != len(headings):
            raise ValueError('Bible Gateway passage sections do not match the translation headings.')
        lines, verses = [], []
        for container in containers:
            section_lines, section_verses = parse_biblegateway(html.tostring(container, encoding='utf-8'))
            lines.extend(section_lines)
            verses.extend(section_verses)
    except Exception as error:
        raise ValueError(f'Could not read NIV {reference} from Bible Gateway: {error}') from error
    save(target, {'reference': reference, 'translation': 'NIV', 'url': url,
                  'verse_ids': verses, 'lines': lines})
    return lines


def exact_niv_reading(reference, cache, offline=False):
    """Read full requested verses from saved/fresh NIV source HTML, never authored text.

    Separate from the bulletin cache: old handout summaries and manually supplied
    lines cannot be accepted as verified quotations. Re-parse source HTML on reruns.
    """
    normalized = reference.replace('–', '-').replace('—', '-')
    match = re.fullmatch(r'([1-3]?\s*[A-Za-z][A-Za-z ]*)\s+(\d+):([\d,\s-]+)', normalized)
    if not match:
        raise ValueError(f'Exact NIV lookup needs an explicit book, chapter, and verses: {reference}')
    book, chapter, selection = match.groups()
    passages = []
    from lxml import html
    for part in selection.split(','):
        part = part.strip()
        limits = re.fullmatch(r'(\d+)(?:-(\d+))?', part)
        if not limits:
            raise ValueError(f'Invalid NIV verse selection: {reference}')
        first, last = int(limits[1]), int(limits[2] or limits[1])
        if first < 1 or last < first or last - first > 175:
            raise ValueError(f'Invalid NIV verse range: {reference}')
        requested = f'{book.strip()} {chapter}:{part}'
        url = 'https://www.biblegateway.com/passage/?' + urlencode({'search': requested, 'version': 'NIV'})
        cache_file = cache / (hashlib.sha256(requested.encode()).hexdigest()[:16] + '-NIV-source.json')
        cached = cache_file.exists()
        if cached:
            record = read_json(cache_file)
            if record.get('reference') != requested or record.get('url') != url or record.get('translation') != 'NIV':
                raise ValueError(f'Invalid NIV source record: {cache_file}')
            payload = record.get('html', '').encode('utf-8')
            if hashlib.sha256(payload).hexdigest() != record.get('sha256'):
                raise ValueError(f'NIV source cache changed: {cache_file}. Remove it and retry online.')
        else:
            if offline:
                raise ValueError(f'Exact NIV source for {requested} is not cached. Rerun update without --offline; no paraphrase will be used.')
            try:
                with urlopen(Request(url, headers={'User-Agent': 'KentonWorshipWorkflow/1.0'}), timeout=25) as response:
                    payload = response.read(2_000_000)
            except Exception as error:
                raise ValueError(f'Cannot retrieve exact NIV {requested}: {error}') from error
        page = html.fromstring(payload)
        headings = page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " passage-display ")]')
        if len(headings) != 1 or 'New International Version' not in headings[0].text_content():
            raise ValueError(f'Source is not labeled NIV for {requested}.')
        heading_reference = headings[0].text_content().split('New International Version')[0].strip()
        if handouts.reference(heading_reference) != handouts.reference(requested):
            raise ValueError(f'NIV source reference does not match {requested}: {heading_reference}')
        # Preserve rendered small capitals (notably LORD) when moving HTML
        # into plain-text Word slots. Do not change any Scripture wording.
        for small_caps in page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " small-caps ")]'):
            for node in small_caps.iter():
                if node.text:
                    node.text = node.text.upper()
                if node is not small_caps and node.tail:
                    node.tail = node.tail.upper()
        lines, verse_ids = parse_biblegateway(html.tostring(page, encoding='utf-8'))
        numbers = {(int(v.rsplit('-', 2)[1]), int(v.rsplit('-', 2)[2])) for v in verse_ids}
        expected = {(int(chapter), v) for v in range(first, last + 1)}
        if numbers != expected:
            raise ValueError(f'NIV source is missing or adds verses for {requested}; no partial quotation was used.')
        if not cached:
            save(cache_file, {'reference': requested, 'translation': 'NIV', 'url': url,
                              'html': payload.decode('utf-8'), 'sha256': hashlib.sha256(payload).hexdigest()})
        passages.append(' '.join(lines))
    return '\n'.join(passages)


def plain_plan(raw):
    result = {'date': raw['date']}
    for service in SERVICES:
        s = raw[service]
        result[service] = {
            'sermon': s['sermon']['source_text']['value'], 'topic': s['sermon']['topic']['value'],
            'kind': 'discussion' if s['program_kind'] == 'video' else 'word-study',
            'call_to_worship': s['call_to_worship']['value'],
            'prayer_of_confession': s['prayer_of_confession']['value'],
            'prayer_of_confession_text': s.get('prayer_of_confession_text', {}).get('value'),
            'has_prayer_text_row': 'prayer_of_confession_text' in s,
            'praise_songs': [v['value'] for v in s['praise_songs'] if v['value']],
            'hymns': [v['value'] for v in s['hymns'] if v['value']],
            'study_words': [v.strip() for v in re.split(r'[,;\n]+', str(s.get('study_words', {}).get('value') or '')) if v.strip()],
            'additional_reading': raw['unassigned_readings'][0 if service == 'morning' else 1]['value'] or ''}
    return result


def content_file(path, plan):
    """Planner metadata plus optional authored material; no fabricated teaching defaults."""
    result = {'date': plan['date']}
    for name in SERVICES:
        service = plan[name]
        result[name] = {'display_title': service['topic'] or '',
            'call_reference': service['call_to_worship'], 'translation': 'NIV', 'call_lines': [],
            'passage_reference': service['sermon'], 'passage_text': '', 'chord_files': {},
            'target_words': [{'word': word} for word in service['study_words']]}
    if path.exists():
        overrides = read_json(path)
        if overrides.get('date') == plan['date']:
            for name in SERVICES:
                supplied = overrides.get(name, {})
                for key, value in supplied.items():
                    # Reading metadata belongs to supplied text. Blank scaffold text
                    # must not override the current planner's fetched NIV reading.
                    if key == 'passage_reference' and not supplied.get('passage_text'):
                        continue
                    if key == 'call_reference' and not supplied.get('call_lines'):
                        continue
                    if key == 'translation' and not (supplied.get('passage_text') or supplied.get('call_lines')):
                        continue
                    if value:  # Empty fields from an earlier generated scaffold are not requirements.
                        result[name][key] = value
    return result


def discover_chord_folders(root):
    """Locate praise/chord directories by their actual names, not a guessed path."""
    if not root.is_dir():
        raise ValueError(f'Cannot read worship source: {root}')
    found, pending = [], [(root, 0)]
    while pending:
        folder, depth = pending.pop(0)
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            relative = str(child.relative_to(root)).casefold()
            if 'praise' in relative and 'chord' in relative:
                found.append(child)
                continue
            if depth < 4 and child.name.casefold() not in ('week-sets', 'weeksets', '_archive', 'archive', '.git'):
                pending.append((child, depth + 1))
    if not found:
        raise ValueError(f'No praise-chord folder found under {root}. Use --chords with the actual folder.')
    return found


def chord_file(song, folder, override=None):
    folders = list(folder) if isinstance(folder, (list, tuple)) else [folder]
    folder = folders[0]
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = folder / candidate
        if candidate.suffix.lower() not in ('.pdf', '.docx') or not candidate.is_file():
            raise ValueError(f'Chord file is missing or not PDF/DOCX: {candidate}')
        return candidate
    try:
        available = folder.is_dir()
    except PermissionError:
        raise ValueError(f'Cannot read the chord folder: {folder}. Check Drive access or set --chords to a readable copy.') from None
    if not available:
        raise ValueError(f'Chord source is unavailable: {folder}. Set --chords to the praise-chords folder.')
    title = praise_title(song)
    key = lambda s: re.sub(r'[^a-z0-9]', '', s.casefold())
    # Require a complete filename match; arrangements and keys need an explicit choice.
    candidates = [p for location in folders for p in location.rglob('*') if p.is_file() and p.suffix.lower() in ('.pdf', '.docx')
                  and key(praise_title(p.stem)) == key(title)]
    if len(candidates) != 1:
        raise ValueError(f'{song}: found {len(candidates)} exact chord matches. Check its filename or select an arrangement in the optional chord_files override.')
    return candidates[0]


def find_template(folder, service):
    found = [p for p in files_under(folder) if p.suffix.lower() == '.docx'
             and 'bulletin' in p.name.casefold() and service in p.name.casefold()]
    if len(found) != 1:
        raise ValueError(f'Expected one {service} bulletin DOCX in {folder}; found {len(found)}.')
    return found[0]


def paragraph_text(node):
    return ''.join(node.xpath('.//w:t/text()', namespaces=NS))


def set_text(node, value):
    """Fill a whole mapped paragraph without changing its paragraph/run styles."""
    ts = node.xpath('.//w:t', namespaces=NS)
    if not ts:
        raise ValueError('Mapped template paragraph has no text run.')
    ts[0].text = value
    ts[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    for t in ts[1:]:
        t.text = ''
    # Only obsolete in-text line breaks; preserve deliberate page/column breaks.
    for br in node.xpath('.//w:br[not(@w:type) or @w:type="textWrapping"]|.//w:tab', namespaces=NS):
        br.getparent().remove(br)


def bulletin(template, service, content, day, destination):
    """Map labeled sections in the retained bulletin; do not adjust its layout."""
    from lxml import etree
    with ZipFile(template) as source:
        try:
            document = etree.fromstring(source.read('word/document.xml'))
        except etree.XMLSyntaxError as error:
            raise ValueError(f'Template contains invalid Word XML: {template}: {error}') from error
        body = document.find(W+'body')
        ps = body.findall(W+'p')
        def matching(prefix):
            return [p for p in ps if paragraph_text(p).strip().lstrip('* \ufffd').upper().startswith(prefix)]
        def one(prefix):
            found = matching(prefix)
            if len(found) != 1:
                raise ValueError(f'{template.name}: expected one {prefix} heading; found {len(found)}.')
            return found[0]
        def between(first, last):
            nodes = list(body)
            return [n for n in nodes[nodes.index(first)+1:nodes.index(last)] if n.tag == W+'p' and paragraph_text(n).strip()]
        day_value = date.fromisoformat(day)
        dates = [p for p in ps if re.match(r'^[A-Z][a-z]+ \d{1,2}, \d{4}', paragraph_text(p))]
        if len(dates) != 1:
            raise ValueError(f'{template.name}: expected one printed date.')
        original_date = paragraph_text(dates[0])
        set_text(dates[0], re.sub(r'^[A-Z][a-z]+ \d{1,2}, \d{4}',
                 f'{day_value:%B} {day_value.day}, {day_value.year}', original_date))
        call = one('CALL TO WORSHIP')
        set_text(call, f'CALL TO WORSHIP ({service["call_to_worship"]} — NIV)')
        table = call.getnext()
        while table is not None and table.tag == W+'p' and not paragraph_text(table).strip():
            table = table.getnext()
        if table is None or table.tag != W+'tbl':
            raise ValueError('Call to worship must be followed by its responsive-reading table.')
        rows = table.findall(W+'tr')
        patterns = {}
        for row in rows:
            cells = row.findall(W+'tc')
            if len(cells) == 2:
                patterns.setdefault(paragraph_text(cells[0]).strip(), row)
        new_rows = []
        for i, line in enumerate(content['call_lines']):
            speaker = 'Leader' if i % 2 == 0 else 'People'
            if speaker not in patterns:
                raise ValueError(f'Template lacks a {speaker} responsive row.')
            row = deepcopy(patterns[speaker])
            for cell, value in zip(row.findall(W+'tc'), (speaker, line)):
                paragraphs = cell.findall(W+'p')
                if len(paragraphs) != 1:
                    raise ValueError('Responsive table cell needs one paragraph.')
                set_text(paragraphs[0], value)
            new_rows.append(row)
        for row in rows:
            table.remove(row)
        table.extend(new_rows)
        praise = between(one('PRAISE MUSIC'), one('INVOCATION'))
        hymns = matching('HYMN')
        for mapped, values, label in ((praise, service['praise_songs'], 'praise songs'), (hymns, service['hymns'], 'hymns')):
            if len(mapped) != len(values):
                raise ValueError(f'{template.name}: {len(mapped)} {label} slots but {len(values)} selections. Edit the copied template to match.')
            for p, value in zip(mapped, values):
                if label == 'hymns':
                    old = paragraph_text(p)
                    prefix = re.match(r'^\s*\*?\s*HYMN\s*[^\w\s]?\s*', old, re.I).group()
                    value = prefix + value
                set_text(p, value)
        prayer_heading, silent = one('PRAYER OF CONFESSION'), one('SILENT PRAYER')
        # A stray leading glyph may have a black run before the blue heading.
        # Use the actual heading run, not that glyph's formatting.
        heading_run = next((r for r in prayer_heading.findall(W+'r')
                            if 'PRAYER' in paragraph_text(r).upper()), None)
        first_run = prayer_heading.find(W+'r')
        if heading_run is not None and first_run is not None and heading_run is not first_run:
            old = first_run.find(W+'rPr')
            if old is not None:
                first_run.remove(old)
            properties = heading_run.find(W+'rPr')
            if properties is not None:
                first_run.insert(0, deepcopy(properties))
        set_text(prayer_heading, 'PRAYER OF CONFESSION (UNISON)')
        prayer_nodes = between(prayer_heading, silent)
        if not prayer_nodes:
            raise ValueError('Template has no prayer paragraphs.')
        # Keep the prayer and its source adjacent; inherited blank paragraphs
        # and paragraph spacing must not separate the reference from the prayer.
        if len(prayer_nodes) < 2:
            raise ValueError('Template needs a separate prayer and source paragraph.')
        prayer, reference = prayer_nodes[0], prayer_nodes[-1]
        set_text(prayer, ' '.join(content['prayer'].split()))
        set_text(reference, service['prayer_of_confession'].strip())
        for unused in prayer_nodes[1:-1]:
            unused.getparent().remove(unused)
        # between() excludes empty paragraphs, so remove those as well.
        node = prayer.getnext()
        while node is not None and node is not reference:
            following = node.getnext()
            if node.tag == W+'p' and not paragraph_text(node).strip():
                node.getparent().remove(node)
            node = following
        for paragraph in (prayer, reference):
            props = paragraph.find(W+'pPr')
            if props is None:
                props = etree.Element(W+'pPr')
                paragraph.insert(0, props)
            spacing = props.find(W+'spacing')
            if spacing is None:
                spacing = etree.SubElement(props, W+'spacing')
            for key in ('before', 'after', 'beforeLines', 'afterLines'):
                spacing.set(W+key, '0')
            for key in ('beforeAutospacing', 'afterAutospacing'):
                spacing.set(W+key, '0')
            if paragraph is prayer:
                keep = props.find(W+'keepNext')
                if keep is None:
                    keep = etree.SubElement(props, W+'keepNext')
                keep.set(W+'val', '1')
        for run in reference.findall(W+'r'):
            props = run.find(W+'rPr')
            if props is None:
                props = etree.Element(W+'rPr')
                run.insert(0, props)
            for tag, value in (('i', '1'), ('iCs', '1'), ('b', '0'), ('bCs', '0')):
                setting = props.find(W+tag)
                if setting is None:
                    setting = etree.SubElement(props, W+tag)
                setting.set(W+'val', value)
        scripture = [p for p in ps if p in matching('SCRIPTURE') or
                     p.xpath('.//w:bookmarkStart[@w:name="KentonScripture"]', namespaces=NS)]
        if len(scripture) > 1 or (service['additional_reading'] and not scripture):
            raise ValueError('Scripture reference cannot be placed: template needs exactly one SCRIPTURE paragraph. Restore it from an approved bulletin; this bulletin was not generated.')
        elif scripture:
            # Keep the mapping when a week has no reading; a blank printed line
            # must not erase the slot needed when this document is reused.
            if not scripture[0].xpath('.//w:bookmarkStart[@w:name="KentonScripture"]', namespaces=NS):
                ids = document.xpath('//w:bookmarkStart/@w:id', namespaces=NS)
                identity = str(max([int(v) for v in ids if v.isdigit()] + [0]) + 1)
                start = etree.Element(W+'bookmarkStart', {W+'id': identity, W+'name': 'KentonScripture'})
                end = etree.Element(W+'bookmarkEnd', {W+'id': identity})
                scripture[0].append(start)
                scripture[0].append(end)
            set_text(scripture[0], 'SCRIPTURE — ' + service['additional_reading'] if service['additional_reading'] else '')
        sermon_options = matching('SERMON') + matching('VIDEO PRESENTATION')
        if len(sermon_options) != 1:
            raise ValueError('Template needs one SERMON or VIDEO PRESENTATION heading.')
        sermon = sermon_options[0]
        set_text(sermon, 'VIDEO PRESENTATION' if service['kind'] == 'discussion' else 'SERMON — ' + service['sermon'])
        title = sermon.getnext()
        while title is not None and title.tag == W+'p' and not paragraph_text(title).strip():
            title = title.getnext()
        if title is None or title.tag != W+'p':
            raise ValueError('Sermon title paragraph is missing.')
        # Preserve any preacher line following an explicit line break.
        first_line = []
        for node in title.iter():
            if node.tag == W+'br':
                break
            if node.tag == W+'t':
                first_line.append(node)
        if not first_line:
            raise ValueError('Sermon title text is missing.')
        first_line[0].text = content['display_title']
        for node in first_line[1:]:
            node.text = ''
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, 'w') as output:
            for info in source.infolist():
                payload = etree.tostring(document, xml_declaration=True, encoding='UTF-8', standalone=True) if info.filename == 'word/document.xml' else source.read(info.filename)
                output.writestr(deepcopy(info), payload)


def handout(service, content, day, destination):
    """Assemble authored teaching using the retained Word source."""
    handouts.generate(service, content, destination)


def chord_cover(service, day, songs, destination):
    from docx import Document
    doc = Document()
    doc.add_heading('Praise Chords', 0)
    doc.add_paragraph(day)
    doc.add_paragraph(service.title() + ' Worship')
    doc.add_heading('Songs in service order', 1)
    for song in songs:
        doc.add_paragraph(song, style='List Number')
    doc.save(destination)


def export_word(docx):
    """One native Word export, bounded timeout, no GUI or separate PDF compositor."""
    pdf = docx.with_suffix('.pdf')
    script = r'''
$ErrorActionPreference = 'Stop'
$word = $null; $document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($env:KENTON_DOCX, $false, $true)
    $document.Repaginate()
    $document.ExportAsFixedFormat($env:KENTON_PDF, 17)
} finally {
    if ($null -ne $document) { $document.Close(0) }
    if ($null -ne $word) { $word.Quit() }
}
'''
    before = digest(docx)
    import base64
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    env = dict(os.environ, KENTON_DOCX=str(docx.resolve()), KENTON_PDF=str(pdf.resolve()))
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                env=env, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f'Word export could not run: {error}. Run update from your normal Windows terminal.') from error
    if result.returncode or not pdf.is_file():
        raise ValueError('Microsoft Word could not export the PDF. Open Word once in your Windows session, then retry update. '
                         'Technical detail: ' + result.stderr.decode(errors='replace')[-1200:])
    if digest(docx) != before:
        raise ValueError('The Word file changed during PDF export. Retry update.')
    from pypdf import PdfReader
    if not len(PdfReader(pdf).pages):
        raise ValueError(f'Empty exported PDF: {pdf}')
    return pdf


def gather(root, day, offline, chords):
    p = paths(root, day)
    state = Path(root) / 'work/input-state.json'
    imported = read_json(state) if state.exists() else {}
    input_note = None
    if not imported.get('complete') or imported.get('date') != day:
        input_note = 'Input was not marked complete for this date; using the available work/planning files.'
    planning = Path(root) / 'work/planning'
    record = {'planner': str(workbook_file(planning, 'recent logs')),
              'catalog': str(workbook_file(planning, 'song lists')),
              'templates': str(Path(root) / 'work/templates')}
    for key in ('planner', 'catalog'):
        log(root, f'Reading planning copy: "{record[key]}"')
    log(root, f'Reading named templates: "{record["templates"]}"')
    raw = extract_week(record['planner'], record['catalog'], day)
    plan = plain_plan(raw)
    save(p['desktop'] / 'temporary.json', plan)
    extra_path = p['working'] / 'content.json'
    extra = content_file(extra_path, plan)
    issues = [s for s in raw['issues'] if 'additional reading service assignment' not in s]
    if input_note:
        issues.append(input_note)
    if extra.get('date') != day:
        issues.append(f'content.json date must be {day}.')
    chord_source_error = None
    try:
        if chords is None:
            sources = imported.get('planning_sources', [])
            worship = Path(sources[0]).parent if sources else Path(r'G:\My Drive\kenton\_worship')
            chord_folders = discover_chord_folders(worship)
        else:
            chord_folders = [Path(chords)]
            if not chord_folders[0].is_dir():
                raise ValueError(f'Cannot read chord folder: {chord_folders[0]}')
        log(root, 'Praise chord folders: ' + ', '.join(str(v) for v in chord_folders))
    except (OSError, ValueError) as error:
        chord_folders = []
        chord_source_error = f'Praise chords: {error}'
        issues.append(chord_source_error)
    prepared = {}
    for name in SERVICES:
        s = plan[name]
        e = extra.get(name, {})
        e = deepcopy(e)
        e['service'] = name
        e['chord_source_error'] = chord_source_error
        prepared[name] = e
        for field in ('sermon', 'topic', 'call_to_worship', 'prayer_of_confession', 'praise_songs', 'hymns'):
            if not s[field]:
                issues.append(f'{name}: planner is missing {field}.')
        if not e.get('display_title'):
            issues.append(f'{name}: content.json needs display_title.')
        def attempt(label, fn):
            try:
                return fn()
            except (OSError, ValueError, KeyError) as error:
                issues.append(f'{name} {label}: {error}')
                return None
        bulletin_folder = Path(record['templates']) / 'standard'
        e['template'] = attempt('template', lambda: find_template(bulletin_folder, name))
        e['prayer'] = (s.get('prayer_of_confession_text') if s.get('has_prayer_text_row')
                       else attempt('prayer', lambda: confession(record['catalog'], s['prayer_of_confession'])))
        if e.get('call_lines'):
            if e.get('translation') != 'NIV' or norm(e.get('call_reference')) != norm(s['call_to_worship']):
                issues.append(f'{name}: supplied call_lines need NIV and the matching call_reference.')
            if not isinstance(e['call_lines'], list) or any(not isinstance(v, str) or not v.strip() for v in e['call_lines']):
                issues.append(f'{name}: call_lines must contain nonempty text lines.')
        elif s['call_to_worship']:
            e['call_lines'] = attempt('call to worship', lambda: bible_reading(s['call_to_worship'], p['desktop'] / 'scripture-cache', offline))
        sources = imported.get('planning_sources', [])
        worship = Path(sources[0]).parent if sources else PLANNING_ROOT
        if s['kind'] == 'word-study' and not e.get('handout_content'):
            from .study_research import load_ranked
            research = attempt('ranked study research', lambda: load_ranked(root, day, s))
            if research:
                research_path, e['handout_content'], e['_research_niv'] = research
                log(root, f'Reading ranked study research: "{research_path}"')
        e['_handout_source'] = attempt('handout', lambda: handouts.prepare_named(
            s, e, Path(record['templates']), [worship / '_Handouts']))
        if e['_handout_source']:
            log(root, f'Reading authored handout/template: "{e["_handout_source"]}"')
            if s['kind'] == 'word-study':
                def lookup_niv(ref):
                    cached = e.get('_research_niv', {}).get(handouts.reference(ref))
                    if cached:
                        log(root, f'Exact NIV word-study reference: {ref} (verified API.Bible research source)')
                        return cached
                    log(root, f'Exact NIV word-study reference: {ref} (Bible Gateway source HTML)')
                    return exact_niv_reading(ref, p['desktop'] / 'scripture-cache/word-study-niv', offline)
                e['_verified_word_content'] = attempt('exact NIV word study', lambda:
                    handouts.verified_word_content(s, e, lookup_niv))
        e['chords'] = []
        for song in s['praise_songs'] if chord_folders else []:
            file = attempt(f'chords for {song}', lambda song=song: chord_file(song, chord_folders, e.get('chord_files', {}).get(song)))
            if file:
                e['chords'].append(file)
    return p, record, plan, prepared, issues


def replace_working_file(source, target):
    """Refresh generated working files atomically; never write an input source."""
    target = checked_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        if digest(source) != digest(temporary):
            raise ValueError(f'Copy verification failed: {source}')
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def finish_update_stage(root, stage, complete, manifest):
    """Retire only a verified immediate .update-* child of this workspace's work folder."""
    work = checked_path(Path(root) / 'work')
    stage = checked_path(stage)
    if stage.parent != work or not re.fullmatch(r'\.update-[A-Za-z0-9_-]+', stage.name):
        raise ValueError(f'Refusing cleanup outside an update staging folder: {stage}')
    # Reject nested junctions/links before any recursive filesystem operation.
    list(files_under(stage))
    if complete:
        if not manifest:
            raise ValueError('Refusing cleanup without verified generated output.')
        for name, expected in manifest.items():
            if Path(name).name != name:
                raise ValueError(f'Invalid generated filename for cleanup: {name}')
            for folder in ('output', 'desktop'):
                if digest(checked_path(work / folder / name)) != expected:
                    raise ValueError(f'Cannot clean staging: {folder}/{name} no longer matches generated output.')
        shutil.rmtree(stage)
        log(root, f'Removed successful update staging folder: {stage}')
        return None
    destination = checked_path(work / '_archive/failed-updates' / stage.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage.rename(destination)
    log(root, f'Failed update working files retained at: {destination}')
    return str(destination)


def archive_older_generated(root, day):
    """Keep only this service date's generated documents in the active folders."""
    root = Path(root)
    issues = []
    archive = root / 'work/_archive/previous-generated' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for name in ('desktop', 'output'):
        folder = checked_path(root / 'work' / name)
        if not folder.exists():
            continue
        for path in folder.iterdir():
            match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})-(morning|evening)-(bulletin|word-study|discussion|chords-index|praise-chords)\.(docx|pdf)', path.name)
            if match and match[1] != day and path.is_file():
                target = checked_path(archive / name / path.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    checked_path(path).rename(target)
                    log(root, f'Archived previous generated document: "{target}"')
                except PermissionError:
                    issues.append(f'Close "{path}" and rerun update so the previous document can be archived.')
    return issues


def update_automation(root, day, check=False, offline=False, chords=None, bulletin_templates=None):
    log(root, f'UPDATE — {day}')
    chords = Path(chords) if chords else None
    p = paths(root, day)
    status = Path(root) / 'work/build.json'
    save(status, {'date': day, 'complete': False})
    p, record, plan, prepared, issues = gather(root, day, offline, chords)
    if bulletin_templates is not None:
        for name in SERVICES:
            issues = [issue for issue in issues if not issue.startswith(f'{name} template:')]
            try:
                prepared[name]['template'] = find_template(Path(bulletin_templates), name)
                log(root, f'{name.capitalize()} bulletin template: "{prepared[name]["template"]}"')
            except (OSError, ValueError) as error:
                prepared[name]['template'] = None
                issues.append(f'{name} template: {error}')
    report = p['desktop'] / 'needs-attention.txt'
    def report_attention():
        save(report, 'Update attention items\n\n' + ('\n'.join('- ' + s for s in issues) if issues else 'None.') + '\n')
    for issue in issues:
        log(root, 'ATTENTION: ' + issue)
    report_attention()
    log(root, f'Extracted current planner column into {p["desktop"] / "temporary.json"}')
    if check:
        log(root, 'Input check finished. Attention items are advisory; update will attempt each output independently.')
        return 0
    for issue in archive_older_generated(root, day):
        issues.append(issue)
        log(root, 'ATTENTION: ' + issue)
    if (Path(root) / 'website.json').exists():
        try:
            draft = website.prepare(root, day, plan)
            log(root, f'Website panels ready for review: {draft}')
        except (OSError, ValueError, KeyError, TypeError) as error:
            save(Path(root) / 'work/website-build.json', {'date': day, 'complete': False})
            issues.append(f'Website panels: {error}')
            log(root, 'ATTENTION: ' + issues[-1])
    from pypdf import PdfReader, PdfWriter
    stage = Path(tempfile.mkdtemp(prefix='.update-', dir=Path(root) / 'work'))
    output = p['output']
    output.mkdir(parents=True, exist_ok=True)
    manifest, failures = {}, []

    def attempt(label, stem, build):
        """One failed output does not prevent the other services/documents."""
        job = stage / stem
        job.mkdir()
        try:
            if stem.endswith('-handout'):
                # A failed handout must not leave the previous generic or wrong-kind
                # document in active review output. Preserve it before attempting a rerun.
                service_name = stem.removesuffix('-handout')
                archive = Path(root) / 'work/_archive/handouts' / stage.name
                for parent in (output, p['desktop']):
                    for kind in ('word-study', 'discussion'):
                        for suffix in ('.docx', '.pdf'):
                            old = parent / f'{day}-{service_name}-{kind}{suffix}'
                            if old.exists():
                                retained = archive / parent.name / old.name
                                retained.parent.mkdir(parents=True, exist_ok=True)
                                old.rename(retained)
            build(job)
            log(root, f'Generated {label}.')
        except Exception as error:
            message = f'{label}: {error}'
            if isinstance(error, PermissionError):
                message += ' Close the open review file and rerun update.'
            failures.append(label)
            issues.append(message)
            log(root, 'ATTENTION: ' + message + ' Continuing other outputs.')
        # A generated Word file is useful even if native PDF export is unavailable.
        for source in sorted(job.glob('*')):
            if not source.is_file() or source.suffix.lower() not in ('.docx', '.pdf'):
                continue
            # Both index files are intermediates used only inside praise-chords.pdf.
            if source.name.endswith(('-chords-index.docx', '-chords-index.pdf')):
                for parent in (output, p['desktop']):
                    old_index = parent / source.name
                    if old_index.exists():
                        try:
                            retained = Path(root) / 'work/_archive/chord-index' / stage.name / parent.name / source.name
                            retained.parent.mkdir(parents=True, exist_ok=True)
                            old_index.rename(retained)
                        except OSError as error:
                            failures.append(label)
                            issues.append(f'{label}: could not archive standalone index {old_index}: {error}')
                continue
            if source.suffix.lower() == '.pdf':
                try:
                    if not len(PdfReader(source).pages):
                        continue
                except Exception:
                    continue
            try:
                if source.suffix.lower() == '.docx' and not source.with_suffix('.pdf').exists():
                    # An older PDF must not masquerade as the export of this new DOCX.
                    for parent in (output, p['desktop']):
                        old_pdf = checked_path(parent / source.with_suffix('.pdf').name)
                        if old_pdf.exists():
                            retained = checked_path(Path(root) / 'work/_archive/stale-pdfs' / stage.name / parent.name / old_pdf.name)
                            retained.parent.mkdir(parents=True, exist_ok=True)
                            old_pdf.rename(retained)
                replace_working_file(source, output / source.name)
                replace_working_file(source, p['desktop'] / source.name)
                manifest[source.name] = digest(source)
            except OSError as error:
                if label not in failures:
                    failures.append(label)
                message = (f'{label}: Windows could not replace the review file: {error}. '
                           'A PDF/Word viewer (including a background tab), file permissions, or a read-only file may prevent replacement. '
                           f'New files are retained at {job}; see the final archive location below.')
                issues.append(message)
                log(root, 'ATTENTION: ' + message + ' Continuing other outputs.')


    for name in SERVICES:
        s, e = plan[name], prepared[name]
        def make_bulletin(folder):
            if not e.get('template') or not e.get('prayer') or not e.get('call_lines'):
                raise ValueError('Needs its template, confession prayer, and responsive reading; this bulletin was not generated.')
            if not isinstance(e['call_lines'], list) or any(not isinstance(line, str) or not line.strip() for line in e['call_lines']):
                raise ValueError('Responsive reading lines are missing or invalid.')
            if e.get('translation') != 'NIV' or norm(e.get('call_reference')) != norm(s['call_to_worship']):
                raise ValueError('Responsive reading reference/translation does not match the plan.')
            target = folder / f'{day}-{name}-bulletin.docx'
            bulletin(e['template'], s, e, day, target)
            for note in e.get('_layout_attention', []):
                issues.append(f'{name}: {note}')
                log(root, 'ATTENTION: ' + name + ': ' + note)
            export_word(target)
        attempt(f'{name} bulletin', f'{name}-bulletin', make_bulletin)

        def make_handout(folder):
            if not e.get('_handout_source'):
                raise ValueError('Handout was not generated; see the specific template/content attention above.')
            target = folder / f'{day}-{name}-{s["kind"]}.docx'
            handout(s, e, day, target)
            pdf = export_word(target)
            if s['kind'] == 'word-study' and len(PdfReader(pdf).pages) != 1:
                raise ValueError(f'Word study exported to {len(PdfReader(pdf).pages)} pages; the current requirement is one. '
                                 'Draft retained with the template formatting and selected verses unchanged. '
                                 'Review work/templates/GENERATION-PLAN.md and adjust the template or explicitly revise the page requirement.')
        attempt(f'{name} handout', f'{name}-handout', make_handout)

        def make_chords(folder):
            if not s['praise_songs'] or len(e.get('chords', [])) != len(s['praise_songs']):
                raise ValueError('Some chord files are missing; no incomplete chord packet was generated.')
            cover = folder / f'{day}-{name}-chords-index.docx'
            chord_cover(name, day, s['praise_songs'], cover)
            cover_pdf = export_word(cover)
            writer = PdfWriter()
            try:
                writer.append(str(cover_pdf))
                for number, source in enumerate(e['chords'], 1):
                    copied = stage / 'chord-sources' / name / f'{number:02d}-{source.name}'
                    copy_file(source, copied)
                    pdf = export_word(copied) if copied.suffix.lower() == '.docx' else copied
                    writer.append(str(pdf))
                with (folder / f'{day}-{name}-praise-chords.pdf').open('wb') as stream:
                    writer.write(stream)
            finally:
                writer.close()
        if e.get('chord_source_error'):
            failures.append(f'{name} praise chords')
            log(root, f'{name} praise chords not generated; see the single chord-source message above.')
        else:
            attempt(f'{name} praise chords', f'{name}-chords', make_chords)
    working_files = str(stage)
    try:
        working_files = finish_update_stage(root, stage, not failures, manifest)
    except (OSError, ValueError) as error:
        issues.append(f'Temporary-file cleanup: {error}. Working files retained at {stage}.')
        log(root, 'ATTENTION: ' + issues[-1])
    report_attention()
    save(status, {'date': day, 'complete': not failures, 'output': str(output),
                  'files': manifest, 'attention': issues, 'failed_outputs': failures,
                  'visual_review_required': True, 'working_files': working_files})
    log(root, f'UPDATE finished: {len(manifest)} files refreshed; {len(failures)} outputs could not be completed. See {report}.')
    return 0


def publish_automation(root, day, reviewed=False, force=False):
    p = paths(root, day)
    log(root, f'PUBLISH — {day}')
    if not reviewed:
        raise ValueError('Review the output first, then run publish-automation.py --reviewed. This confirms your review.')
    status = Path(root) / 'work/build.json'
    if not status.exists() or not read_json(status).get('complete'):
        raise ValueError('Update has not completed successfully. Nothing was published.')
    build = read_json(status)
    output = p['output']
    actual = {str(f.relative_to(output)): digest(f) for f in files_under(output)}
    if build.get('date') != day or actual != build['files']:
        raise ValueError('Review output changed after generation. Rerun update so Word and PDF stay in agreement.')
    weeks = checked_path(PUBLISH_ROOT)
    if not weeks.is_dir():
        raise ValueError(f'Publish folder is unavailable: "{weeks}". Connect Google Drive and retry; no local fallback is used.')
    target = checked_path(weeks / date.fromisoformat(day).strftime('%Y%m%d'))
    log(root, f'Publish destination: "{target}"')
    if target.exists() and not force:
        raise ValueError(f'Week-set already exists: {target}. Nothing was overwritten. Use --reviewed --force to replace it.')
    if target.exists() and not target.is_dir():
        raise ValueError(f'Week-set destination is not a folder: {target}. Nothing was overwritten.')
    staged = Path(tempfile.mkdtemp(prefix='.publish-', dir=weeks))
    backup = None
    try:
        copy_tree(output, staged)
        if {str(f.relative_to(staged)): digest(f) for f in files_under(staged)} != actual:
            raise ValueError('Published copy did not match review output.')
        if {str(f.relative_to(output)): digest(f) for f in files_under(output)} != actual:
            raise ValueError('Review output changed during publication. Retry.')
        if force and target.exists():
            # Both resolved paths stay beneath the selected publication root.
            # Move the entire old set, including files absent from the new output.
            checked_path(target)
            archive = checked_path(weeks / '_archive')
            archive.mkdir(exist_ok=True)
            container = Path(tempfile.mkdtemp(prefix=target.name + '-', dir=archive))
            backup = checked_path(container / target.name)
            if weeks not in target.parents or weeks not in backup.parents:
                raise ValueError('Publication replacement paths must remain inside WEEK-SETS.')
            target.rename(backup)
            log(root, f'Previous week-set preserved at "{backup}"')
        # Windows rename fails if another process creates the destination.
        staged.rename(target)
    except Exception:
        if backup is not None and backup.exists():
            if not target.exists():
                try:
                    backup.rename(target)
                    log(root, f'Previous week-set restored at "{target}"')
                except OSError as error:
                    log(root, f'Could not restore previous week-set: {error}. Recover it from "{backup}".')
            else:
                log(root, f'Destination now exists; previous week-set remains safe at "{backup}".')
        log(root, f'Incomplete publication retained for inspection at {staged}')
        raise
    log(root, f'PUBLISH complete: {target}. Templates and prior review runs were excluded.')
    return 0


def main(stage, argv=None):
    parser = argparse.ArgumentParser(description={
        'input': "Read planning workbooks and copy last week's templates.",
        'update': 'Generate this week’s bulletins, handouts and praise chord sets.',
        'publish': 'Copy reviewed documents to a new Google Drive week-set.'}[stage])
    parser.add_argument('--date', help='Sunday as YYYY-MM-DD; defaults to the current input week (or next Sunday for input).')
    if stage == 'input':
        parser.add_argument('--previous-week', type=Path, help='Last week’s folder if automatic selection is ambiguous.')
    elif stage == 'update':
        parser.add_argument('--website-only', action='store_true', help='Prepare only the four website panels from the planning copies.')
        parser.add_argument('--check', action='store_true', help='List missing inputs without generating documents.')
        parser.add_argument('--force', action='store_true', help='Explicitly regenerate working documents; update already rebuilds them on every run.')
        parser.add_argument('--offline', action='store_true', help='Use supplied/cached Scripture without contacting Bible Gateway.')
        parser.add_argument('--chords', type=Path, help='Read-only praise-chords source folder.')
        template_options = parser.add_mutually_exclusive_group()
        template_options.add_argument('--communion', action='store_true', help='Use work/templates/communion for both bulletins; otherwise use work/templates/standard.')
        template_options.add_argument('--bulletin-templates', type=Path, help='Use an explicitly selected folder containing one morning and one evening bulletin DOCX.')
    else:
        parser.add_argument('--website', action='store_true', help='Also apply reviewed panels to the configured local website project after Drive publication.')
        parser.add_argument('--website-only', action='store_true', help='Apply only reviewed panels to the local website project; no Drive publication.')
        parser.add_argument('--reviewed', action='store_true', help='Confirm you reviewed this output before copying it.')
        parser.add_argument('--force', action='store_true', help='Replace an existing Drive week-set, preserving it under week-sets/_archive. Requires --reviewed.')
    args = parser.parse_args(argv)
    try:
        if args.date:
            day = date.fromisoformat(args.date)
        elif stage == 'input':
            today = date.today()
            day = today + timedelta(days=(6-today.weekday()) % 7)
        else:
            current = ROOT / 'work/input-state.json'
            if not current.exists():
                raise ValueError('Run input-automation.py first or provide --date YYYY-MM-DD.')
            day = date.fromisoformat(read_json(current)['date'])
        if day.weekday() != 6:
            raise ValueError('The selected date must be a Sunday.')
        if stage == 'input':
            return input_automation(ROOT, day.isoformat(), args.previous_week) or 0
        if stage == 'update':
            if args.website_only and (args.communion or args.bulletin_templates):
                raise ValueError('Bulletin template options cannot be used with --website-only.')
            if args.website_only:
                if args.check:
                    raise ValueError('Use --website-only without --check to prepare the review draft.')
                planning = ROOT / 'work/planning'
                planner = workbook_file(planning, 'recent logs')
                catalog = workbook_file(planning, 'song lists')
                log(ROOT, f'Website planning inputs: "{planner}"; "{catalog}"')
                save(ROOT / 'work/website-build.json', {'date': day.isoformat(), 'complete': False})
                plan = plain_plan(extract_week(planner, catalog, day.isoformat()))
                log(ROOT, f'Website panels ready for review: {website.prepare(ROOT, day.isoformat(), plan)}')
                return 0
            template_folder = ROOT / 'work/templates/communion' if args.communion else args.bulletin_templates
            return update_automation(ROOT, day.isoformat(), args.check, args.offline, args.chords, template_folder)
        if args.website_only:
            if args.force:
                raise ValueError('--force applies only to Drive week-sets; website edits are protected from overwrite.')
            log(ROOT, f'LOCAL WEBSITE updated: {website.publish(ROOT, day.isoformat(), args.reviewed)}. Live site deployment is separate.')
            return 0
        result = publish_automation(ROOT, day.isoformat(), args.reviewed, args.force)
        if args.website:
            log(ROOT, f'LOCAL WEBSITE updated: {website.publish(ROOT, day.isoformat(), args.reviewed)}. Live site deployment is separate.')
        return result
    except ImportError as error:
        log(ROOT, f'Missing Python dependency: {error}. Install once with: python -m pip install -e .')
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        log(ROOT, f'{stage.upper()} stopped: {error}')
        return 1

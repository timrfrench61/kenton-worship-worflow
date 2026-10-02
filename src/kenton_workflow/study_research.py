"""Map ranked, sourced research into the existing Word-study template contract."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .handouts import key, reference

OT = set('GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL'.split())
NT = set('MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV'.split())


def load_ranked(root, day, service):
    root = Path(root)
    matches = []
    for path in (root / 'work/research').glob(day + '*.json'):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if (data.get('status') == 'gemini_ranked_draft_not_approved'
                and reference(data.get('passage', '')) == reference(service['sermon'])
                and [key(w['word']) for w in data.get('words', [])] == [key(w) for w in service['study_words']]):
            matches.append((data['ranking']['created_utc'], path, data))
    if not matches:
        return None
    _, path, data = max(matches, key=lambda item: (item[0], str(item[1])))
    if not data.get('complete'):
        raise ValueError(f'Ranked study research is incomplete: {path}')
    config = json.loads((root / 'application.json').read_text(encoding='utf-8-sig'))
    bible_id = config['bible']['bible_id']
    bible = data['bible']['data']
    if (bible.get('id') != bible_id or bible.get('abbreviation') not in ('NIV', 'NIV11')
            or bible.get('language', {}).get('id') != 'eng'):
        raise ValueError('Ranked research does not identify English NIV.')
    cache = (root / config['word_study']['cache_directory']).resolve()
    if (root / 'work').resolve() not in cache.parents:
        raise ValueError('Research source cache must be under work/.')
    main_ids = {p['id'] for p in data['main_passage']['data']['passages']}
    content = {'title': service['topic'] or service['sermon'], 'translation': 'NIV',
               'passage_reference': service['sermon'],
               'body_font_size': config['word_study'].get('body_font_size', 14),
               'see_also_format': config['word_study'].get('see_also_format', 'See also {references} (NIV)'), 'words': []}
    texts = {}
    count = config['word_study'].get('handout_full_verses_per_testament_per_word', 3)
    count = config['word_study'].get('handout_full_verses_by_word_count', {}).get(str(len(data['words'])), count)
    if type(count) is not int or not 1 <= count <= 3:
        raise ValueError('Handout full-verse count must be between one and three per Testament per word.')
    for word in data['words']:
        item = {'word': word['word'].title()}
        for testament in ('old_testament', 'new_testament'):
            verses = word[testament]['verses']
            if len(verses) != 6 or len({v['id'] for v in verses}) != 6:
                raise ValueError('Ranked research requires six distinct verses per Testament per word.')
            for verse in verses:
                if verse['id'].split('.')[0] not in (OT if testament == 'old_testament' else NT):
                    raise ValueError('Ranked reference is in the wrong Testament.')
                if verse['id'] in main_ids:
                    raise ValueError('Ranked research includes the study verse; regenerate research and ranking.')
                source = verse['source']
                url = source['url']
                parsed = urlparse(url)
                if (parsed.scheme != 'https' or parsed.netloc != 'rest.api.bible'
                        or parsed.path != f'/v1/bibles/{bible_id}/verses/{verse["id"]}'):
                    raise ValueError('Unexpected NIV research source URL.')
                saved = cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
                if not saved.exists() or json.loads(saved.read_text(encoding='utf-8')) != source:
                    raise ValueError(f'Research source cache does not match {verse["reference"]}; recollect research.')
                entry = source['data']
                if (entry.get('bibleId') != bible_id or entry.get('id') != verse['id']
                        or entry.get('bookId') != verse['id'].split('.')[0]
                        or entry.get('reference') != verse['reference']
                        or entry.get('content', '').strip() != verse['text'] or not verse['text'].strip()):
                    raise ValueError('Ranked Scripture text differs from its full-verse source.')
                text = verse['text']
                # API.Bible may prepend the Psalm chapter label even when
                # include-titles=false. It is metadata, not part of the verse.
                if verse['id'].startswith('PSA.'):
                    chapter = verse['id'].split('.')[1]
                    text = re.sub(r'^Psalm ' + re.escape(chapter) + r'\s*\n', '', text)
                texts[reference(verse['reference'])] = ' '.join(text.split())
            item[testament] = [{'reference': v['reference']} for v in verses[:count]]
            item[testament + '_see_also'] = [v['reference'] for v in verses[count:]]
        content['words'].append(item)
    return path, content, texts

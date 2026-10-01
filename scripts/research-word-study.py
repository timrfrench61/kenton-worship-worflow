"""Collect balanced NIV research using Python's standard library. No LLM calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OT = set('GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL'.split())
NT = set('MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV'.split())


def tokens(value):
    return set(re.findall(r"[a-z]+", value.casefold()))


class Client:
    def __init__(self, config):
        self.config = config
        bible = config['bible']
        self.key = os.environ.get(bible['api_key_env'], '').strip()
        if not self.key:
            secrets = ROOT / config['credentials_file']
            if secrets.exists():
                self.key = json.loads(secrets.read_text(encoding='utf-8-sig')).get('api_bible', '').strip()
        if not self.key:
            raise ValueError(f"Set {bible['api_key_env']} or api_bible in {config['credentials_file']}.")
        self.cache = ROOT / config['word_study']['cache_directory']
        if ROOT / 'work' not in self.cache.resolve().parents:
            raise ValueError('Cache directory must be under work/.')

    def get(self, path, params=None):
        url = self.config['bible']['base_url'].rstrip('/') + path
        if params:
            url += '?' + urlencode(params)
        cache = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        # Always verify live access/edition metadata; cache Scripture responses.
        if params and cache.exists():
            record = json.loads(cache.read_text(encoding='utf-8'))
            if record['url'] != url:
                raise ValueError('Cache URL mismatch.')
            return record
        try:
            with urlopen(Request(url, headers={'api-key': self.key}),
                         timeout=self.config['word_study']['timeout_seconds']) as response:
                data = json.load(response)['data']
        except HTTPError as error:
            raise ValueError(f'API.Bible HTTP {error.code} for {path}; no translation substituted.') from None
        except (URLError, KeyError, json.JSONDecodeError) as error:
            raise ValueError(f'API.Bible request failed for {path}: {type(error).__name__}') from None
        record = {'url': url, 'retrieved_utc': datetime.now(timezone.utc).isoformat(), 'data': data}
        if params:
            self.cache.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return record


def validate_entry(entry, bible_id, allowed=None):
    if entry.get('bibleId') != bible_id:
        raise ValueError('Returned Scripture has the wrong Bible ID.')
    if allowed is not None and entry.get('bookId') not in allowed:
        raise ValueError('Search returned a verse outside the requested Testament.')


def collect(get, config, passage, words, count, page_size):
    bible_id = config['bible']['bible_id']
    path = '/bibles/' + bible_id
    metadata = get(path)
    bible = metadata['data']
    if (bible.get('id') != bible_id or bible.get('name') != config['bible']['name']
            or bible.get('abbreviation') not in ('NIV', 'NIV11')
            or bible.get('language', {}).get('id') != 'eng'):
        raise ValueError('The endpoint did not confirm English NIV 2011.')
    main = get(path + '/search', {'query': passage, 'fuzziness': '0'})
    if not main['data'].get('passages'):
        raise ValueError('Main reference did not return a passage.')
    for entry in main['data']['passages']:
        validate_entry(entry, bible_id)
    result = {'status': 'research_candidates_not_approved', 'passage': passage,
              'requested_per_testament_per_word': count, 'bible': metadata,
              'main_passage': main, 'words': [], 'issues': [],
              'selection_method': 'Exact word occurrence, then overlap with other study words, then API relevance order. Not theological approval.'}
    context = set().union(*(tokens(word) for word in words))
    for word in words:
        item = {'word': word}
        for testament, books in [('old_testament', OT), ('new_testament', NT)]:
            pool, pages = {}, []
            offset = 0
            for _ in range(config['word_study']['max_pages_per_testament']):
                response = get(path + '/search', {'query': word, 'range': config['word_study']['ranges'][testament],
                               'limit': page_size, 'offset': offset, 'sort': 'relevance', 'fuzziness': '0'})
                pages.append(response)
                data = response['data']
                verses = data.get('verses', [])
                for verse in verses:
                    validate_entry(verse, bible_id, books)
                    if tokens(word) <= tokens(verse.get('text', '')):
                        pool.setdefault(verse['id'], verse)
                if len(pool) >= count or not verses:
                    break
                offset += len(verses)
                if offset >= data.get('total', offset):
                    break
            other = context - tokens(word)
            ranked = sorted(pool.values(), key=lambda v: -len(tokens(v['text']) & other))
            selected = []
            for verse in ranked[:count]:
                full = get(path + '/verses/' + quote(verse['id'], safe='.'),
                           {'content-type': 'text', 'include-notes': 'false',
                            'include-titles': 'false', 'include-chapter-numbers': 'false',
                            'include-verse-numbers': 'false'})
                data = full['data']
                validate_entry(data, bible_id, books)
                if data.get('id') != verse['id'] or data.get('reference') != verse['reference'] or not data.get('content', '').strip():
                    raise ValueError('Full verse retrieval did not match the selected reference.')
                selected.append({'id': data['id'], 'reference': data['reference'],
                                 'text': data['content'].strip(), 'source': full})
            item[testament] = {'candidates_checked': len(pool), 'search_pages': pages, 'verses': selected}
            print(f'{word}: {testament} {len(selected)}/{count}', flush=True)
            if len(selected) != count:
                result['issues'].append(f'{word}: only {len(selected)} distinct {testament} verses found; requested {count}.')
        result['words'].append(item)
    result['complete'] = not result['issues']
    return result


def markdown(result):
    lines = [f"# {result['passage']} — NIV word-study research", '',
             f"Requested: {result['requested_per_testament_per_word']} Old Testament and the same number of New Testament verses per word.",
             '', 'These are research candidates, not an approved one-page handout.', '', result['selection_method'], '']
    for item in result['words']:
        lines += ['## ' + item['word'], '']
        for key, label in [('old_testament', 'Old Testament'), ('new_testament', 'New Testament')]:
            lines += ['### ' + label, '']
            for number, verse in enumerate(item[key]['verses'], 1):
                lines += [f"{number}. **{verse['reference']}** — {verse['text']}", '']
    lines += ['## Source and status', '', result['bible']['data'].get('copyright', ''), '']
    lines += result['issues'] or ['All requested counts met. Editorial review still required.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'application.json')
    parser.add_argument('--passage', required=True)
    parser.add_argument('--words', nargs='+', required=True)
    parser.add_argument('--count', type=int, help='Verses per Testament per word; default from application.json')
    parser.add_argument('--limit', type=int, help='Search page size; default from application.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        if config['llm']['provider'] != 'none':
            raise ValueError('Remote LLM execution is not implemented. Set llm.provider to none for Python research.')
        count = args.count if args.count is not None else config['word_study']['verses_per_testament_per_word']
        limit = args.limit if args.limit is not None else config['word_study']['page_size']
        if not 1 <= count <= 50 or not 1 <= limit <= 50 or not 1 <= config['word_study']['max_pages_per_testament'] <= 20:
            raise ValueError('Count and page size must be 1–50; maximum pages must be 1–20.')
        dest = args.output.resolve()
        if (ROOT / 'work').resolve() not in dest.parents or dest.suffix != '.json':
            raise ValueError('Output must be a JSON file under work/.')
        if dest.exists() or dest.with_suffix('.md').exists():
            raise ValueError('Output already exists. Choose a new filename to preserve prior research.')
        result = collect(Client(config).get, config, args.passage, args.words, count, limit)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        with dest.with_suffix('.md').open('x', encoding='utf-8') as stream:
            stream.write(markdown(result))
        print(f'Research saved: {dest} and {dest.with_suffix(".md")}')
        return 0 if result['complete'] else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'ATTENTION: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

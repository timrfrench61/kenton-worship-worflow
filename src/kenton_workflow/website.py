"""Prepare and publish only the existing website's four public service panels."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import re
from pathlib import Path
import tempfile


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def destination(root):
    config = read(root / 'website.json')
    project = Path(config['project']).resolve()
    target = (project / config['data_file']).resolve()
    if project not in target.parents or target.suffix != '.json':
        raise ValueError('Website data_file must be a JSON file inside the configured website project.')
    if not target.is_file():
        raise ValueError(f'Website panel data is unavailable: {target}')
    return target


def card_date(value):
    for pattern in ('%Y-%m-%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f'Invalid website service date: {value}')


def apply_appearance(root, cards):
    config = read(root / 'website.json')
    settings = config.get('cards', {})
    slots = {c['slot'] for c in cards}
    if set(settings) - slots:
        raise ValueError('Unknown website appearance card slot.')
    colors = {'backgroundColor', 'overlayColor', 'textColor', 'headingColor', 'accentColor', 'borderColor', 'linkColor'}
    for card in cards:
        selected = settings.get(card['slot'], {})
        if set(selected) - {'backgroundImage', 'appearance'}:
            raise ValueError('Card settings support only backgroundImage and appearance.')
        if 'backgroundImage' in selected:
            name = selected['backgroundImage']
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:jpg|jpeg|png|webp)', name):
                raise ValueError('Card backgroundImage must be a local image filename.')
            image = Path(config['project']) / 'wwwroot/images/card-background' / name
            if not image.is_file():
                raise ValueError(f'Card background image is missing: {image}')
            card['backgroundImage'] = name
        appearance = selected.get('appearance', {})
        if set(appearance) - colors - {'imageOpacity'}:
            raise ValueError('Unknown card appearance setting.')
        for key, value in appearance.items():
            if key in colors and (not isinstance(value, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?', value)):
                raise ValueError(f'{key} must be #RRGGBB or #RRGGBBAA.')
            if key == 'imageOpacity' and (not isinstance(value, str) or not re.fullmatch(r'(?:0(?:\.\d+)?|1(?:\.0+)?)', value)):
                raise ValueError('imageOpacity must be a string between 0 and 1.')
        if appearance:
            card['appearance'] = deepcopy(appearance)


def prepare(root, day, plan):
    root = Path(root)
    selected = date.fromisoformat(day)
    if selected.weekday() != 6 or plan['date'] != day:
        raise ValueError('Website plan must match the selected Sunday.')
    target = destination(root)
    original_hash = digest(target)
    source = read(target)
    cards = source['cards']
    slots = {c['slot']: c for c in cards}
    expected = {f'{period}-sunday-{service}' for period in ('last', 'next') for service in ('morning', 'evening')}
    if len(cards) != 4 or set(slots) != expected:
        raise ValueError('Website source must have exactly the four recognized service slots.')
    result = []
    for name, time in (('morning', '11am'), ('evening', '6pm')):
        previous = [c for c in cards if c['slot'].endswith('-' + name)
                    and card_date(c['serviceDate']) == selected - timedelta(days=7)]
        if len(previous) != 1:
            raise ValueError(f'Website needs a verified {name} card for {selected - timedelta(days=7)}. No stale card was relabeled.')
        card = deepcopy(previous[0])
        card.update(slot=f'last-sunday-{name}', timeframe=f'Last Sunday {time}')
        result.append(card)
    for name, time in (('morning', '11am'), ('evening', '6pm')):
        service = plan[name]
        for field in ('sermon', 'topic', 'call_to_worship'):
            if not isinstance(service.get(field), str) or not service[field].strip():
                raise ValueError(f'Website {name} needs planner {field}.')
        movie = service['kind'] == 'discussion'
        card = deepcopy(slots[f'next-sunday-{name}'])
        card.update(serviceDate=day, timeframe=f'This Sunday {time}',
                    heading=('Morning Worship, Praise, Fellowship and Teaching' if name == 'morning'
                             else 'Evening Worship and Movie' if movie else 'Evening Worship, Praise and Teaching'),
                    summary=service['topic'].strip(),
                    sermonTitle=None if movie else service['sermon'].strip(),
                    scriptureReference=service['call_to_worship'].strip(),
                    speaker=None, linkUrl=None, linkLabel=None,
                    songs=service.get('praise_songs', []) + service.get('hymns', []))
        result.append(card)
    apply_appearance(root, result)
    source.update(lastUpdated=datetime.now().astimezone().isoformat(), cards=result)
    draft = root / 'work/desktop/worship-highlights.json'
    state = root / 'work/website-build.json'
    write(state, {'date': day, 'complete': False})
    write(draft, source)
    if digest(target) != original_hash:
        raise ValueError('Website changed during preparation. Rerun update.')
    write(state, {'date': day, 'complete': True, 'destination': str(target),
                  'source_sha256': original_hash, 'draft_sha256': digest(draft),
                  'config_sha256': digest(root / 'website.json')})
    return draft


def publish(root, day, reviewed):
    root = Path(root)
    if not reviewed:
        raise ValueError('Review the website draft first; publishing requires --reviewed.')
    state = read(root / 'work/website-build.json')
    draft = root / 'work/desktop/worship-highlights.json'
    target = destination(root)
    if state.get('config_sha256') and state['config_sha256'] != digest(root / 'website.json'):
        raise ValueError('Website settings changed after preparation. Rerun update --website-only and review.')
    if not state.get('complete') or state['date'] != day or state['destination'] != str(target) or digest(draft) != state['draft_sha256']:
        raise ValueError('Website draft/configuration changed or is incomplete. Rerun update --website-only and review.')
    if digest(target) == state['draft_sha256']:
        return target
    if digest(target) != state['source_sha256']:
        raise ValueError('Website was edited after preparation. Rerun update --website-only; existing edits were preserved.')
    archive = root / 'work/_archive/website'
    archive.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=day+'-', suffix='.json', dir=archive, delete=False) as backup:
        backup.write(target.read_bytes())
    staged = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.worship-', suffix='.json', dir=target.parent, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(draft.read_bytes())
        if digest(target) != state['source_sha256']:
            raise ValueError('Website changed during publication. Retry after preparing again.')
        staged.replace(target)
        if digest(target) != state['draft_sha256']:
            raise ValueError('Website copy verification failed.')
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
    return target

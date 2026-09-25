"""Prepare one Sunday's inputs. Drive is read-only; no src package is used."""
import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'G:\My Drive\kenton\_worship')
SKIP = {'.gdoc', '.gsheet', '.gslides', '.gdraw', '.glink', '.gform', '.gsite'}


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def log(message, clear=False):
    folder = ROOT / 'work/desktop'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'automation.log').open('w' if clear else 'a', encoding='utf-8') as stream:
        stream.write(f'{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n')
    print(message, flush=True)


def workbook(source, name):
    key = lambda value: re.sub('[^a-z0-9]', '', value.casefold())
    matches = [p for p in source.iterdir() if p.is_file() and p.suffix.lower() == '.xlsx'
               and not p.name.startswith('~$') and key(p.stem) == key(name)]
    if len(matches) != 1:
        available = ', '.join(p.name for p in source.glob('*.xlsx')) or '(none)'
        raise ValueError(f'Expected one {name} workbook in "{source}"; found {len(matches)}. Excel files there: {available}')
    return matches[0]


def list_files(folder):
    def fail(error):
        raise error
    for parent, directories, names in os.walk(folder, followlinks=False, onerror=fail):
        for name in directories:
            if (Path(parent) / name).is_symlink():
                raise ValueError(f'Linked source folder needs an explicit real path: {Path(parent) / name}')
        for name in sorted(names):
            path = Path(parent) / name
            if name.lower() in ('desktop.ini', 'thumbs.db') or name.startswith('~$'):
                continue
            if path.suffix.lower() in SKIP:
                continue
            if path.is_symlink():
                raise ValueError(f'Linked source file needs an explicit real path: {path}')
            yield path


def select_previous(weeks, sunday):
    previous = sunday - timedelta(days=7)
    candidates = [weeks / previous.strftime('%Y%m%d'), weeks / previous.isoformat(),
                  weeks / str(previous.year) / previous.strftime('%Y%m%d'),
                  weeks / str(previous.year) / previous.isoformat()]
    matches = [p for p in candidates if p.is_dir()]
    if len(matches) != 1:
        available = ', '.join(sorted(p.name for p in weeks.iterdir() if p.is_dir())[-15:])
        raise ValueError(f'Expected one week-set for {previous} in "{weeks}"; found {len(matches)}. '
                         f'Folders there: {available or "(none)"}. Use --previous-week with the correct Drive folder.')
    return matches[0]


def copy_verified(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = file_hash(source)
    if destination.exists():
        if destination.is_file() and file_hash(destination) == expected:
            return
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)  # Contents only; Drive timestamps can be invalid on Windows.
        if file_hash(temporary) != expected or file_hash(source) != expected:
            raise ValueError(f'Source changed while copying: "{source}". Save it and rerun input.')
        os.replace(temporary, destination)  # Refresh the working copy on every rerun.
    finally:
        temporary.unlink(missing_ok=True)


def prepare(sunday, source, weeks=None, previous=None):
    import openpyxl
    desktop, output = ROOT / 'work/desktop', ROOT / 'work/output'
    planning = ROOT / 'work/planning'
    previous_copy = desktop / 'previous'
    weeks = weeks or source / 'week-sets'
    log(f'INPUT - {sunday}', clear=True)
    log(f'Python: "{sys.executable}" ({sys.version.split()[0]})')
    state = ROOT / 'work/input-state.json'
    state.write_text(json.dumps({'date': str(sunday), 'complete': False}, indent=2), encoding='utf-8')
    log(f'Planning source: "{source}" (read-only)')
    log(f'Week-set source: "{weeks}" (read-only)')
    if not source.is_dir():
        raise ValueError(f'Cannot read "{source}". Connect Google Drive and rerun input.')
    if not weeks.is_dir():
        raise ValueError(f'Cannot read week-set folder "{weeks}". Use --week-sets with its Drive location.')
    books = [workbook(source, 'recent logs'), workbook(source, 'song lists')]
    previous = previous or select_previous(weeks, sunday)
    if not previous.is_dir():
        raise ValueError(f'Cannot read last week: "{previous}"')
    for original in (source, weeks, previous):
        for working in (desktop, output, planning):
            a, b = original.resolve(), working.resolve()
            if a == b or a in b.parents or b in a.parents:
                raise ValueError('Source folders and working folders must not overlap.')
    # Check both workbooks and the complete copy list before writing any content.
    for path in books:
        book = openpyxl.load_workbook(path, read_only=True, data_only=False)
        try:
            log(f'Workbook: "{path}"; sheets: {", ".join(book.sheetnames)}')
        finally:
            book.close()
    planned = [(p, planning / p.name) for p in books]
    planned += [(p, previous_copy / p.relative_to(previous)) for p in list_files(previous)]
    if len(planned) == len(books):
        raise ValueError(f'Last week has no copyable files: "{previous}"')
    expected_previous = {p for _, p in planned if previous_copy in p.parents}
    if previous_copy.exists():
        extras = [p for p in list_files(previous_copy) if p not in expected_previous]
        if extras:
            log(f'ATTENTION: {len(extras)} other files in DESKTOP/previous were retained; continuing refresh.')
    inventory = [f'Week-set source: {weeks}', f'Last week selected: {previous}', '']
    inventory += [str(p.relative_to(weeks)) for p in list_files(weeks)]
    for original, target in planned:
        copy_verified(original, target)
        log(f'Copied "{original}" -> "{target}"')
    (desktop / 'week-sets.txt').write_text('\n'.join(inventory) + '\n', encoding='utf-8')
    state.write_text(json.dumps({'date': str(sunday), 'complete': True,
        'planning_sources': [str(p.resolve()) for p in books],
        'week_sets_source': str(weeks.resolve()), 'previous_week': str(previous.resolve()),
        'desktop': str(desktop), 'planning': str(planning), 'output': str(output),
        'previous_copy': str(previous_copy),
        'copies': [{'source': str(a), 'copy': str(b), 'sha256': file_hash(b)} for a,b in planned]}, indent=2) + '\n', encoding='utf-8')
    log(f'INPUT complete. Planning copies: "{planning}". Last week\'s files: "{previous_copy}".')


def main():
    parser = argparse.ArgumentParser(description='Read Drive planning workbooks and copy last week into work/desktop/previous. One Sunday at a time.')
    parser.add_argument('--date', required=True, help='Sunday as YYYY-MM-DD')
    parser.add_argument('--source', type=Path, default=SOURCE, help='Drive worship folder containing the two Excel workbooks')
    parser.add_argument('--week-sets', type=Path, help='Drive week-set folder; defaults to SOURCE/week-sets')
    parser.add_argument('--previous-week', type=Path, help='Exact previous week folder if its name differs')
    args = parser.parse_args()
    try:
        sunday = date.fromisoformat(args.date)
        if sunday.weekday() != 6:
            raise ValueError('Select a Sunday in YYYY-MM-DD format.')
        from _python_environment import ensure_environment
        ensure_environment('input')
        prepare(sunday, args.source, args.week_sets, args.previous_week)
        return 0
    except (OSError, ValueError, ImportError) as error:
        log(f'INPUT stopped: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Conservative, one-way import of worship files. Never overwrites or deletes."""

import hashlib
import os
from pathlib import Path
import stat
import tempfile
from contextlib import contextmanager


# Google-native documents need an export, not a filesystem content copy.
GOOGLE_NATIVE_EXTENSIONS = {'.gslides', '.gdoc', '.gsheet', '.gdraw', '.gform',
                            '.gsite', '.gmap', '.gscript', '.gtable', '.glink'}


@contextmanager
def operation(label, path):
    """Keep the failing operation and filename in errors from virtual drives."""
    try:
        yield
    except OSError as error:
        raise OSError(f'{label}: {path}: {error}') from error


def checked_path(path: Path) -> Path:
    """Reject links/junctions rather than following them outside chosen roots."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            with operation('Inspect path', part):
                info = part.lstat()
        except OSError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Link or reparse point requires manual review: {part}')
    return path


def digest(path: Path) -> str:
    with operation('Read file for comparison', path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()


def sync(source: Path, destination: Path, apply: bool = False) -> dict:
    """Preview by default; copy missing files only, report differing files."""
    source, destination = checked_path(source), checked_path(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must not overlap.')
    if not source.is_dir():
        raise ValueError(f'Source folder is unavailable: {source}')
    if destination.exists() and not destination.is_dir():
        raise ValueError('Destination must be a folder.')

    # Finish enumeration and comparison before any writes.
    planned = []
    unchanged = 0
    conflicts = []
    skipped = []
    def fail(error):
        raise error
    for folder, directories, files in os.walk(source, onerror=fail, followlinks=False):
        for name in sorted(directories):
            checked_path(Path(folder) / name)
        for name in sorted(files):
            original = Path(folder) / name
            if original.suffix.lower() in GOOGLE_NATIVE_EXTENSIONS:
                skipped.append({'path': str(original.relative_to(source)),
                                'reason': 'Google-native entry; export separately to a local format if needed'})
                continue
            checked_path(original)
            if not stat.S_ISREG(original.stat().st_mode):
                raise ValueError(f'Not a regular file: {original}')
            relative = original.relative_to(source)
            target = checked_path(destination / relative)
            for parent in target.parents:
                if parent == destination.parent:
                    break
                if parent.exists() and not parent.is_dir():
                    raise ValueError(f'Destination parent is not a folder: {parent}')
            if target.exists():
                if target.is_file() and original.stat().st_size == target.stat().st_size and digest(original) == digest(target):
                    unchanged += 1
                else:
                    conflicts.append(str(relative))
            else:
                planned.append((original, target))

    copied = []
    warnings = []
    if apply:
        for original, target in planned:
            checked_path(original)
            checked_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            before = original.stat()
            temporary = None
            stage = 'Create temporary destination file'
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.sync-', delete=False) as output:
                    temporary = Path(output.name)
                    stage = 'Read source and write temporary destination'
                    with original.open('rb') as input_file:
                        while chunk := input_file.read(1024 * 1024):
                            output.write(chunk)
                stage = 'Verify copied contents'
                after = original.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or digest(original) != digest(temporary):
                    raise ValueError(f'Source changed while copying; retry later: {original}')
                # Virtual drives can report dates Windows cannot apply locally.
                # Timestamp preservation must not prevent a verified content copy.
                try:
                    os.utime(temporary, ns=(before.st_atime_ns, before.st_mtime_ns))
                except (OSError, OverflowError, ValueError) as error:
                    warnings.append(f'{original.relative_to(source)}: could not preserve timestamps ({error}); contents verified')
                stage = 'Publish verified destination file'
                checked_path(target)
                # Atomic publication on NTFS; fails if target appeared meanwhile.
                os.link(temporary, target)
                copied.append(str(target.relative_to(destination)))
            except OSError as error:
                raise OSError(f'{stage}: {original} -> {target}: {error}') from error
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    return {'mode': 'copy' if apply else 'preview', 'source': str(source),
            'destination': str(destination), 'missing': [str(t.relative_to(destination)) for _, t in planned],
            'copied': copied, 'unchanged': unchanged, 'conflicts': conflicts,
            'warnings': warnings, 'skipped': skipped}

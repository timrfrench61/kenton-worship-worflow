"""Preserve previous research when explicitly regenerating it."""
import json
import os
from pathlib import Path
import shutil
import tempfile


def write_research(root, destination, result, markdown, force=False):
    destination = Path(destination)
    targets = (destination, destination.with_suffix('.md'))
    if any(p.exists() for p in targets) and not force:
        raise ValueError('Output already exists. Add --force on the same command line to regenerate it.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Assemble both outputs before touching existing research.
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.research-') as folder:
        staged = [Path(folder) / p.name for p in targets]
        staged[0].write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        staged[1].write_text(markdown, encoding='utf-8')
        if any(p.exists() for p in targets):
            archive = Path(root) / 'work/_archive/research'
            archive.mkdir(parents=True, exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix=destination.stem + '-', dir=archive))
            for target in targets:
                if target.exists():
                    shutil.copy2(target, backup / target.name)
        for source, target in zip(staged, targets):
            os.replace(source, target)

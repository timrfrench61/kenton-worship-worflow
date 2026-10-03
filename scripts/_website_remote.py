"""Uploaded with a release; execute only on the configured Linux host."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen
from urllib.parse import urljoin


def activate(folder):
    folder = Path(folder).resolve()
    spec = json.loads((folder / 'release.json').read_text())
    live = Path(spec['remote_directory'])
    if not live.is_absolute() or len(live.parts) < 4 or live.is_symlink() or live.resolve() != live:
        raise ValueError('Invalid or linked live directory.')
    if not live.is_dir() or live in folder.parents or folder in live.parents:
        raise ValueError('Release storage and live directory must be separate.')
    service = spec['service_name']
    if not all(c.isalnum() or c in '-_.' for c in service) or service.startswith('-'):
        raise ValueError('Invalid service.')
    def control(action):
        subprocess.run(['sudo', '-n', '/usr/bin/systemctl', action, service], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for action in ('stop', 'start'):
        subprocess.run(['sudo', '-n', '-l', '/usr/bin/systemctl', action, service], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    receipt = folder / 'remote-receipt.json'
    if receipt.exists() or (folder / 'previous').exists():
        raise ValueError('Release already attempted; inspect its receipt before another deployment.')
    stage = folder / 'staged'
    stage.mkdir(exist_ok=False)
    with tarfile.open(folder / 'payload.tar.gz') as archive:
        for member in archive.getmembers():
            target = (stage / member.name).resolve()
            if not member.isfile() or stage not in target.parents or member.name not in spec['files']:
                raise ValueError('Unexpected archive member.')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
    for name, expected in spec['files'].items():
        if hashlib.sha256((stage / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Release hash mismatch: ' + name)
    # Preserve server configuration; no credentials are returned to the client.
    for name in spec['preserve_files']:
        source = live / name
        if source.is_symlink():
            raise ValueError('Linked persistent file requires explicit deployment design.')
        if source.is_file():
            shutil.copy2(source, stage / name)
    previous = folder / 'previous'
    previous.mkdir()
    status = {'release_id': spec['release_id'], 'status': 'activating', 'previous': str(previous)}
    receipt.write_text(json.dumps(status))
    moved_old, moved_new = [], []
    stopped = False
    try:
        control('stop')
        stopped = True
        for path in list(live.iterdir()):
            path.rename(previous / path.name)
            moved_old.append(path.name)
        for path in list(stage.iterdir()):
            path.rename(live / path.name)
            moved_new.append(path.name)
        control('start')
        healthy = False
        for _ in range(15):
            running = subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', service]).returncode == 0
            try:
                with urlopen(spec['health_url'], timeout=5) as response:
                    healthy = running and response.status == 200
                panel_file = 'wwwroot/data/worship-highlights.json'
                if healthy and panel_file in spec['files']:
                    with urlopen(urljoin(spec['health_url'], '/data/worship-highlights.json'), timeout=5) as response:
                        healthy = hashlib.sha256(response.read()).hexdigest() == spec['files'][panel_file]
            except Exception:
                healthy = False
            if healthy:
                break
            time.sleep(2)
        if not healthy:
            raise RuntimeError('Service/HTTP health check failed.')
        status['status'] = 'deployed'
    except Exception as error:
        status['error'] = str(error)
        if stopped:
            try:
                control('stop')
                failed = folder / 'failed'
                failed.mkdir(exist_ok=True)
                for name in moved_new:
                    (live / name).rename(failed / name)
                for name in moved_old:
                    (previous / name).rename(live / name)
                control('start')
                subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', service], check=True)
                with urlopen(spec['health_url'], timeout=15) as response:
                    if response.status != 200:
                        raise RuntimeError('Rollback HTTP check failed.')
                status['status'] = 'rolled_back'
            except Exception as rollback:
                status.update(status='rollback_failed', rollback_error=str(rollback))
        else:
            status['status'] = 'failed_before_switch'
        receipt.write_text(json.dumps(status, indent=2))
        raise
    receipt.write_text(json.dumps(status, indent=2))
    print(json.dumps(status))


if __name__ == '__main__':
    activate(sys.argv[1])

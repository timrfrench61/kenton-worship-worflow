"""Inspect deployment settings, prepare releases, and deploy reviewed website builds."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from _website_release import prepare, deploy, log_workbook

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--inspect', action='store_true', help='Read server identity, runtime, and service paths over SSH.')
    modes.add_argument('--prepare', action='store_true', help='Build a full local release with hashes; no upload.')
    modes.add_argument('--deploy', type=Path, metavar='RELEASE', help='Deploy an explicitly reviewed prepared release.')
    modes.add_argument('--log-only', type=Path, metavar='RELEASE', help='Retry maintenance logging without redeploying.')
    parser.add_argument('--reviewed', action='store_true')
    parser.add_argument('--note', default='', help='Description recorded with the release.')
    parser.add_argument('--ssh-user', help='Override the configured login for inspection.')
    args = parser.parse_args()
    try:
        config = json.loads((ROOT / 'website.json').read_text(encoding='utf-8-sig'))
        settings = config['deployment']
        project = Path(config['project']) / settings['project_file']
        if not project.is_file():
            raise ValueError(f'Website project not found: {project}')
        dotnet = shutil.which('dotnet') or 'C:/Program Files/dotnet/dotnet.exe'
        if args.prepare:
            if not args.note.strip():
                raise ValueError('--prepare requires --note describing this release.')
            prepare(ROOT, config, args.note.strip())
            return 0
        if args.deploy:
            deploy(ROOT, config, args.deploy, args.reviewed)
            return 0
        if args.log_only:
            folder = args.log_only.resolve()
            if (ROOT / settings['history_directory']).resolve() not in folder.parents:
                raise ValueError('Receipt must be inside deployment history.')
            receipt = json.loads((folder / 'receipt.json').read_text())
            if receipt['status'] != 'deployed':
                raise ValueError('Only verified successful deployments are logged to the workbook.')
            receipt['workbook_log'] = log_workbook(ROOT, settings, folder, receipt)
            (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2))
            print('Workbook log:', receipt['workbook_log'])
            return 0
        if args.check:
            result = subprocess.run([dotnet, '--list-sdks'], capture_output=True, text=True, check=True)
            print('Website project:', project)
            print('Installed .NET SDKs:\n' + result.stdout.strip())
            print('SSH available:', bool(shutil.which('ssh')))
            missing = [key for key in ('ssh_user', 'remote_directory', 'public_url', 'health_url', 'runtime_identifier') if not settings.get(key)]
            if missing:
                print('Deployment configuration still needed: ' + ', '.join(missing))
            else:
                print('Deployment configuration: complete')
            print('Live deployment enabled:', settings.get('enabled', False))
            if not settings.get('enabled', False):
                print('Next: complete the server permission setup, then set deployment.enabled to true in website.json.')
            return 2 if missing else 0
        user = args.ssh_user or settings.get('ssh_user')
        if not user or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', user):
            raise ValueError('Set deployment.ssh_user or supply --ssh-user with the confirmed login.')
        host, service = settings['host'], settings['service_name']
        if not re.fullmatch(r'[A-Za-z0-9.-]+', host) or host.startswith('-'):
            raise ValueError('Invalid deployment host.')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', service) or service.startswith('-'):
            raise ValueError('Invalid service name.')
        command = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                   '-p', str(int(settings.get('ssh_port', 22)))]
        if settings.get('identity_file'):
            command += ['-i', str(Path(settings['identity_file']).expanduser())]
        remote = ('hostname; uname -m; cat /etc/os-release; dotnet --list-runtimes; '
                  'systemctl show ' + shlex.quote(service) +
                  ' --property=LoadState,ActiveState,User,Group,WorkingDirectory,ExecStart,FragmentPath; '
                  'systemctl is-active caddy; caddy version')
        result = subprocess.run(command + [f'{user}@{host}', remote], capture_output=True, text=True, timeout=45)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        folder = (ROOT / settings['history_directory']).resolve()
        if (ROOT / 'work').resolve() not in folder.parents:
            raise ValueError('History must be stored under work/.')
        folder.mkdir(parents=True, exist_ok=True)
        report = folder / f'inspect-{stamp}.txt'
        report.write_text(f'Inspection only: {user}@{host}\nExit code: {result.returncode}\n'
                          + result.stdout + '\n' + result.stderr, encoding='utf-8')
        print(f'Inspection saved: {report}')
        print('Review each command result; SSH success alone does not verify deployment readiness.')
        return 0 if result.returncode == 0 else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'ATTENTION: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

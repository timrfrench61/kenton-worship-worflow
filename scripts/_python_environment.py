"""Install missing dependencies locally and rerun the same command.

This module uses only the standard library so it works before openpyxl exists.
It never installs packages into the Python that launched the user's command.
"""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys


def dependency_names(stage):
    names = ['openpyxl']
    if stage == 'update':
        names += ['lxml.etree', 'lxml.html', 'docx', 'pypdf']
    return names


def missing_dependencies(stage):
    missing = []
    for name in dependency_names(stage):
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    return missing


def ensure_environment(stage):
    if sys.version_info < (3, 11):
        print('This project needs Python 3.11 or newer. Current Python: ' + sys.executable)
        raise SystemExit(1)
    missing = missing_dependencies(stage)
    if not missing:
        return
    root = Path(__file__).resolve().parents[1]
    environment = root / '.automation-venv'
    executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    # The child must not repeatedly install when a package remains unavailable.
    if os.environ.get('KENTON_DEPENDENCIES_RETRIED') == str(environment):
        print('Project dependency setup did not provide: ' + ', '.join(missing))
        print('Python: ' + sys.executable)
        raise SystemExit(1)
    print('Preparing project Python automatically (your starting Python lacks: ' + ', '.join(missing) + ').', flush=True)
    print('Starting Python: ' + sys.executable, flush=True)
    print('Setting up project Python in ' + str(environment), flush=True)
    print('Packages will be installed here only; your global Python is unchanged.', flush=True)
    try:
        if environment.is_symlink() or (environment.exists() and getattr(environment.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('The project Python folder must not be a link or junction.')
        if not executable.exists():
            subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True, timeout=180)
        # Explicitly require a virtual environment, even if the folder was preexisting.
        subprocess.run([str(executable), '-c',
                        'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)'], check=True, timeout=30)
        probe = subprocess.run([str(executable), '-c',
                                'import importlib,sys; [importlib.import_module(n) for n in sys.argv[1:]]',
                                *dependency_names(stage)], capture_output=True, timeout=30)
        if probe.returncode:
            install_env = dict(os.environ, PIP_REQUIRE_VIRTUALENV='true')
            packages = ['openpyxl>=3.1,<4'] if stage == 'input' else ['openpyxl>=3.1,<4', 'lxml>=5,<7', 'python-docx>=1.1,<2', 'pypdf>=5,<7']
            subprocess.run([str(executable), '-m', 'pip', 'install', '--disable-pip-version-check', *packages],
                           check=True, env=install_env, timeout=300)
        record = root / 'work/python-environment.json'
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({'starting_python': sys.executable,
                                      'starting_version': sys.version,
                                      'project_python': str(executable)}, indent=2) + '\n', encoding='utf-8')
        print('Project Python is ready. Continuing your original command.', flush=True)
        child_env = dict(os.environ, KENTON_DEPENDENCIES_RETRIED=str(environment))
        result = subprocess.run([str(executable), str(Path(sys.argv[0]).resolve()), *sys.argv[1:]], env=child_env)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Project Python setup stopped: {error}')
        print('Check the installation message above and your internet connection, then rerun the same command.')
        raise SystemExit(1) from None
    raise SystemExit(result.returncode)

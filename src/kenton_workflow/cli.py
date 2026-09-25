"""Command-line entry point for the worship workflow."""

import argparse
import json
from pathlib import Path

from kenton_workflow import __version__


def main() -> int:
    """Display help/version or run an explicit one-way import."""
    parser = argparse.ArgumentParser(
        prog="kenton-workflow",
        description="Kenton worship workflow: conservative file copying and project tools.",
        epilog="Document generation, publishing, and archiving are not implemented yet.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest='command')
    copy_parser = commands.add_parser('sync', help='Preview or copy missing files from Drive into this project')
    copy_parser.add_argument('--source', type=Path, required=True)
    copy_parser.add_argument('--destination', type=Path, required=True)
    copy_parser.add_argument('--apply', action='store_true', help='Copy missing files; never overwrite or delete')
    plan_parser = commands.add_parser('plan', help='Preview a Sunday from the planner; optionally save a draft snapshot')
    plan_parser.add_argument('--date', required=True)
    plan_parser.add_argument('--planner', type=Path, default=Path('work/planning/recent logs.xlsx'))
    plan_parser.add_argument('--catalog', type=Path, default=Path('work/planning/Song Lists.xlsx'))
    plan_parser.add_argument('--output', type=Path, help='Write a new JSON snapshot under work/; never overwrite')
    args = parser.parse_args()
    if args.command == 'plan':
        try:
            from kenton_workflow.planner import extract_week, write_snapshot
            from kenton_workflow.sync import checked_path
            result = extract_week(args.planner, args.catalog, args.date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.output:
                root = Path.cwd()
                if not (root / 'pyproject.toml').is_file() or not (root / 'src/kenton_workflow').is_dir():
                    raise ValueError('Run from the repository root to save a snapshot.')
                output = checked_path(args.output)
                if checked_path(root / 'work') not in output.parents or output.suffix.lower() != '.json':
                    raise ValueError('Output must be a JSON file inside this repository\'s work/ folder.')
                write_snapshot(result, output)
                print(f'Saved draft snapshot: {output}')
            return 2 if result['issues'] else 0
        except (OSError, ValueError, ImportError) as error:
            parser.exit(1, f'Planner import stopped: {error}\n')
    if args.command == 'sync':
        from kenton_workflow.sync import checked_path, sync
        try:
            # Run from the repository root. Keep all imported content in ignored work/.
            root = Path.cwd()
            if not (root / 'pyproject.toml').is_file() or not (root / 'src/kenton_workflow').is_dir():
                raise ValueError('Run this command from the kenton-worship-workflow repository root.')
            destination = checked_path(args.destination)
            work = checked_path(root / 'work')
            if work not in destination.parents:
                raise ValueError('Destination must be a subfolder of this repository\'s work/ folder.')
            print(f'Source (read-only): {args.source}', flush=True)
            print(f'Destination: {destination}', flush=True)
            print('Copying missing files' if args.apply else 'Preview only; no files will be written', flush=True)
            result = sync(args.source, destination, args.apply)
        except (OSError, ValueError) as error:
            parser.exit(1, f'Sync stopped: {error}\nEarlier successful copies, if any, remain. Retry safely after resolving the error.\n')
        print(json.dumps(result, indent=2))
        return 2 if result['conflicts'] else 0
    parser.print_help()
    return 0

# Kenton Worship Workflow — start here

Run all commands from **`C:\repos\kenton-worship-workflow`** (the project root). Do not change your terminal into `data` or `work`.

## Current task: September 27 morning and evening audio

1. Set up read access and inventory the videos: [inventory instructions](data/README.md).
2. Identify the services in [the catalog](data/youtube-videos.json); save morning/evening labels and proposed `(AUDIO FIXED)` titles.
3. Repair the local recordings, listen, and upload privately: [audio workflow](docs/01-kenton-audio-repair-001.md).

The catalog remains empty until the first authorized fetch. Picture editing is optional for this task.

## Folder map

| Location | Purpose | GitHub? |
| --- | --- | --- |
| `data/youtube-videos.json` | Maintained inventory, service labels, proposed titles, repair status | Yes |
| `data/README.md` | Inventory command reference | Yes |
| `docs/` | Workflow specifications | Yes |
| `src/`, `scripts/`, `tests/` | Implementation, commands, tests | Yes |
| `work/audio-repair/` | Local audio jobs, reports, and credentials subfolder | No |
| `work/video-repair/` | Picture-edit plans and rendered videos, when needed | No |
| `work/youtube-venv/` | Intended YouTube Python environment, created during setup | No |
| `work/youtube-inventory/backups/` | Recovery copies from real catalog changes | No |
| `work/desktop`, `work/output`, `work/planning` | Weekly worship-document working files | No |
| `work/_archive/` | Previous results and retained development diagnostics | No |

`data` is the durable catalog we maintain together. `work` holds local processing files and secrets. Some folders appear only after their command runs. Neither is a separate project or a command starting directory.

## Which document applies?

| Document | Purpose |
| --- | --- |
| [01-kenton-workflow-001.md](docs/01-kenton-workflow-001.md) | Weekly bulletins, handouts, chords, Drive publication, local website panels |
| [01-kenton-audio-repair-001.md](docs/01-kenton-audio-repair-001.md) | Recording loudness repair and reviewed YouTube upload |
| [01-kenton-video-repair-001.md](docs/01-kenton-video-repair-001.md) | HSWTL picture replacement and Praise Band/Piano slides, keeping service audio |

This root README is the navigation page. The other documents contain details for their specific task. `tests/README.md` is for development verification. Documents in `docs/_archive` are retired.

Weekly document review files go directly in `work/output`, without date subfolders. Reviewed publication goes to `G:\My Drive\kenton\_worship\week-sets\YYYYMMDD`. Local website publication and live deployment are separate. Follow the weekly specification for those operations.

## Existing work folders

`connection-check`, `inspection`, `layout-verification`, `reference-review`, and `verification-missing-openpyxl` are earlier diagnostic/review areas, not audio-repair steps. They remain in place because some contain church document review material. Root-level build/input/website JSON files are workflow state; leave them for their scripts.

Media test environments, synthetic video runs, the one-off audio verification script, and fixture-only catalog backups from this task are now in `work/_archive/media-development-20260929`. They are development evidence, not your recordings or active setup. Archived virtual environments should be recreated for future testing, not run from their moved locations. Historical verification paths in the detailed documents refer to their locations when those tests ran.

Future developer-only artifacts belong in temporary test folders or under `work/_archive`, not beside active jobs. Preserve active document folders and reviewed outputs when organizing.

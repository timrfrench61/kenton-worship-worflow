# Kenton Worship Workflow

A small Python project for planning, producing, publishing, and archiving Kenton's weekly worship materials.

**GitHub holds the workflow system. Google Drive holds the working church materials.** Python handles repeatable file and state operations. AI/Codex helps draft, reason, and review; people make the final content and publishing decisions.

## Current status

This is the documentation and project foundation. The Python entry point provides help and version information only. Spreadsheet import, document generation, publishing, and archiving are planned, not implemented.

## Weekly outputs

| Area | Outputs |
| --- | --- |
| Morning worship | Bulletin, praise chord packet, word study handout, sermon outline |
| Evening worship | Bulletin, praise chord packet, word study handout, sermon outline |
| Prayer and congregational care | Private prayer bulletin and retained prayer reports |
| Website | Coming this Sunday, Where we've been, approved handouts |
| Social and broadcast | Public Facebook drafts, private Facebook prayer reports, Facebook Live and YouTube descriptions/links |

## Getting started

Use Python 3.11 or newer. From this folder in a PowerShell terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m kenton_workflow --help
.\.venv\Scripts\python.exe -m kenton_workflow --version
Copy-Item config\settings.example.toml config\settings.local.toml
```

Edit the local settings copy to point at the actual Google Drive folders. It is ignored by Git. The starter command does not read these settings or access Drive yet. No Google credentials or cloud connection are needed for the skeleton.

If Windows cannot find `python`, install/configure Python or select an existing Python interpreter in VS Code first.

## Project layout

```text
config/                 Safe example settings; ignored local settings
docs/                   Architecture, weekly workflow, sources, development plan
src/kenton_workflow/     Small Python package and command entry point
templates/              Sanitized reusable layouts only
tests/                  Future behavior tests and synthetic fixtures
scripts/                Optional developer utilities
pyproject.toml          Package and command configuration
```

Actual logs, songbooks, chord files, weekly plans, generated documents, prayer information, and archives live outside this repository in Google Drive. The folder names in the documentation are proposals; existing Drive content need not be moved.

## Read next

1. [Architecture](docs/architecture.md)
2. [Weekly workflow](docs/workflow.md)
3. [Data sources](docs/data-sources.md)
4. [Development plan](docs/development-plan.md)

## Git setup

Git is initialized in this folder. Review the files before the first commit and connect your GitHub repository if a remote is not already configured. Never commit local settings, credentials, or church working materials. No remote URL is assumed by this project.

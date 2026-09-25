# Kenton Worship Workflow

Follow [Kenton workflow 001](docs/01-kenton-workflow-001.md). Earlier documentation is in `docs/_archive`.

Use Python 3.11 or newer. Missing dependencies are installed automatically in the repository's `.automation-venv`, then the original command continues. First-time setup requires internet access; your global Python is unchanged.

Run the three stages:

```powershell
python scripts/input-automation.py --date 2026-09-27
python scripts/update-automation.py
# Review the generated Word documents and PDFs before the next command.
python scripts/publish-automation.py --reviewed
```

The date carries forward from input. Add `--check` to update to list missing inputs without building documents. Run `--help` on any script for its options.

Working files and the plain-text log are in `work/desktop`. Review copies are in `work/output/<date>/documents`. Published weeks are in `work/week-sets`. Google Drive is read-only. These scripts do not publish to a website or push to GitHub.

The user or agent supplies handout target words, meanings, and discussion questions in the editable content file described in the workflow. Microsoft Word must be installed and able to start in the terminal's Windows session to produce PDFs.

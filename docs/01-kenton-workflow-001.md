# Kenton workflow 001

1. Prepare the inputs
2. update the worship documents
3. review them
4. publish a new week-set  **NOTE: These are three separate Python commands.

## Who controls the workflow

This document records the user's workflow. AI can help analyze it, explain problems, draft content, and suggest improvements. Suggestions are not an approved replacement for the workflow.

| Responsibility | Authority or tool |
| --- | --- |
| Define the stages, inputs, outputs, and acceptance criteria | The user |
| Analyze issues and propose changes; draft teaching material | AI, subject to review |
| Execute repeatable file operations and validation | Python scripts |
| Control document appearance | The retained, approved templates |
| Confirm content and visual quality before publication | Human review of the actual output |

Fix local defects without redesigning the workflow. Any proposed change to its stages or outputs must be presented as a proposal. A generated file, successful test, or confident AI assessment does not by itself establish that the result is usable.

## How script changes are verified

Verify the command in the Python environment used by the user's VS Code terminal. Record the interpreter path and version; do not assume Codex's bundled environment is equivalent. Dependency changes also require a clean installation check and tests for unavailable optional libraries.

Report separately what passed in automated tests, what ran against real files, and what was rendered and visually reviewed. If the user's environment or Word session cannot be accessed, state that limitation explicitly. The practical procedure is in [tests/README.md](../tests/README.md).

## Folder names

| Workflow name | Folder | Purpose |
| --- | --- | --- |
| PLANNING | `G:\My Drive\kenton\_worship` | Current planning workbooks directly from Drive; read-only inputs, preserving their actual filenames |
| DESKTOP | `work/desktop` | Log, readable planning exports, temporary JSON, editable content, working builds |
| OUTPUT | `work/output` | Generated documents for review; no date subfolder |
| WEEK-SETS | `work/week-sets` | Local completed weekly sets and the previously copied archive |
| PRAISE CHORDS | Your praise-chords folder under `G:\My Drive\kenton\_worship` | Read-only music sources |

DESKTOP means the repository folder, not the Windows Desktop. Church content stays under Git-ignored `work/`. The scripts never change Google Drive files or the planning workbooks.

## Commands

Use Python 3.11 or newer. If a required package is missing, the scripts announce the setup, create a repository-local `.automation-venv`, install this project's declared dependencies there, and continue the original command. First-time setup needs internet access. Later runs reuse that environment. Global Python is not modified. The starting and project interpreter paths are recorded in `work/desktop/python-environment.json` when setup is needed.

Run the three stages:

```powershell
python scripts/input-automation.py --date 2026-09-27
python scripts/update-automation.py
# Review the output before publishing.
python scripts/publish-automation.py --reviewed
```

Input remembers the Sunday for subsequent commands. Use `--date YYYY-MM-DD` to select another Sunday. Input defaults to the next Sunday if its date is omitted.

## 1. Input automation

1. Clear `DESKTOP/automation.log` and start the new log.
2. Read the current planning workbooks directly from `G:\My Drive\kenton\_worship`. Do not use `work/planning` or fall back to it when Drive is unavailable. Match the recent-logs and song-lists workbook names while tolerating spaces, hyphens, and capitalization; preserve their actual filenames when copying.
3. Save readable Markdown exports for agent reading, including sheet names and cell addresses. Save workbook copies for local processing/reference.
4. Refresh the readable WEEK-SETS inventory for agent reading. WEEK-SETS is already local; this refreshes the inventory rather than repeating the Drive migration.
5. Copy last week's complete week-set to `DESKTOP/previous` for processing. Record the copy in the log.

The script accepts spaces or hyphens in workbook filenames. It selects the week exactly seven days earlier and recognizes `YYYYMMDD`, `YYYY-MM-DD`, and `YYYY/YYYY-MM-DD` folders. If more than one matches, specify the source:

```powershell
python scripts/input-automation.py --date 2026-09-27 --previous-week work/week-sets/20260920
```

Identical template copies are reused. A differing existing template copy is preserved and reported rather than overwritten. Superseded planning copies are preserved under `work/_archive/planning-copies`, then refreshed from Drive using the original filenames. Update reads the same Drive sources recorded by input. Old input records based on the rejected local files require rerunning input first.

## 2. Update automation

1. Read the selected date column from the **current** recent logs planner tab.
2. Write its record directly to `DESKTOP/temporary.json`. Read the current copied workbooks in `work/planning` and the previous templates in `work/desktop/previous`, using the completed `work/input-state.json` to select the Sunday.
3. Validate planning fields, prayers, templates, handout content, and chord files. List missing inputs in `DESKTOP/needs-attention.txt` and the log.
4. Generate morning and evening **bulletins**, using the copied Word templates and current JSON.
   - Call to worship: NIV from Bible Gateway, alternating Leader and People lines in the retained responsive table.
   - Prayer of confession: full text from Song Lists, PrayerOfConfession sheet, column D, matched by Scripture reference; marked **UNISON**.
   - Preserve template fonts, spacing, margins, deliberate page breaks, and standing text. Do not redistribute page space.
   - Replace the date, songs, hymns, sermon/program information, prayer, and reading. Preserve a preacher line following the title's line break.
   - Report the affected bulletin if template song/hymn slots differ from the plan; continue other outputs. Do not drop selections or guess positions.
5. Generate morning and evening **handouts**.
   - Normal sermon: one-page Word study, NIV passage, supplied target words, meanings, and questions.
   - `MOV`: discussion sheet using supplied discussion questions.
   - Export through Word. A Word study exceeding one page is retained as a draft with an ATTENTION message; do not reduce fonts automatically.
6. Generate morning and evening **praise chord sets**.
   - Header page: date, service, songs in planner order.
   - Read selected PDF/DOCX chord files from the praise-chords source.
   - Export copied DOCX chords through Word and combine PDFs in that order.
7. Refresh successfully generated files in DESKTOP and OUTPUT for review, even when other outputs need attention. Log each result.

Microsoft Word exports PDFs from the generated DOCX files. Bulletin PDFs are not separately designed. This requires Word in a usable Windows session; run from your normal VS Code terminal if Word cannot start inside an agent session.

### Handouts and chord sources

The planner's `Study-words` row supplies the morning target words (and a row in the evening section supplies evening words). Word-study worksheets include the NIV passage, the selected words, space for their meaning in context, and a study question. Missing prewritten definitions do not block worksheet generation.

For MOV, generate a discussion worksheet with standard viewing questions about the main idea, examples, Scripture, and application. These prompts do not claim knowledge of the video's specific content. Neither worksheet requires the user to fill out `content.json`.

An existing same-date `work/desktop/content.json` can optionally override wording or chord choices. Empty fields are ignored. Scripture may be supplied there or retrieved from Bible Gateway.

Praise-chord folders are discovered by their actual names under the Drive worship source, including nested folders such as `Praise/Chords`. If necessary, select an explicit folder with `--chords "FULL PATH"`. An unavailable source is reported once, not once for every song. Page-number suffixes are ignored when comparing song titles and filenames.

## Reruns and attention

Rerun input to overwrite the working Excel and previous-week copies with the latest source contents. Rerun update to overwrite generated files. ATTENTION messages do not stop the update run: each service and document is attempted independently. A document missing essential content is reported as not generated; other documents continue. A successfully generated DOCX is retained even if PDF export fails. Older PDFs are removed from active output when they no longer correspond to the new DOCX. See `needs-attention.txt` for what remains.

## Review

Open both services in `OUTPUT`. Check content and every rendered page: responsive lines, unison prayer, song order, spacing, page breaks, and the one-page Word study.

Correct planning facts in the workbook and authored material in `content.json`, then rerun update. Earlier successful output is retained outside DESKTOP and OUTPUT under `work/_archive`. A failed build remains on DESKTOP for inspection and cannot be published. Automated completion means files were produced, not that their appearance has been approved.

## 3. Publish automation

1. Require a completed update and `--reviewed` to confirm review.
2. Check that review files still match the generated set, keeping Word and PDF together.
3. Create a new local week-set using the existing `YYYYMMDD` convention.
4. Copy `OUTPUT` into it and verify the copies.

Exclude templates, earlier review runs, logs, and temporary files. Never overwrite an existing week-set. `work/week-sets/20260927` already exists, so publishing that date will stop instead of replacing it. Publication means a local file copy, not a website, Facebook, YouTube, Drive, or GitHub update.

## Reading a failure

Start with `work/desktop/automation.log`. Missing-input details are in `work/desktop/needs-attention.txt`. `temporary.json` shows what the workbook supplied. Exit code 0 means the requested stage succeeded, 2 means update found missing inputs, and 1 means another failure prevented completion.

Input is standalone. Update currently uses document functions in `src/kenton_workflow/automation.py`, so keep `src` while using update. The archived layout profiles and spacing engine are not used. There is no GUI, scheduler, or new framework.

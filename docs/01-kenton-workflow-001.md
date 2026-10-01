# Kenton worship workflow 001

Run these commands in the VS Code terminal from `C:\repos\kenton-worship-workflow`.

This workflow has three separate Python commands:

1. Prepare the inputs.
2. Build the worship documents.
3. Review and publish them.

## 1. Prepare the inputs

Use Python 3.11 or newer. Run:

```powershell
python scripts/input-automation.py --date 2026-10-04
```

Wait for **Complete**. The script reads the current planning workbooks from:

```text
G:\My Drive\kenton\_worship
```

It copies the workbooks, refreshes the week-set inventory, and copies last week's complete week-set into `work/desktop/previous`.

Each input run refreshes both planning workbook copies from Drive and replaces `work/desktop/previous` with only the selected week's reference files after verifying the incoming copies. The old working set is preserved under `work/_archive/input-refresh`. Review generated documents in `work/output`; reusable templates live in `work/templates`.

Use another Sunday with `--date YYYY-MM-DD`. If the previous week is ambiguous, select it explicitly:

```powershell
python scripts/input-automation.py --date 2026-10-04 --previous-week "G:\My Drive\kenton\_worship\week-sets\20260927"
```

Normally omit `--previous-week`: input selects the preceding Sunday's folder from Drive automatically. If specifying it, use the full Drive path; relative paths are resolved from your terminal's current folder, not from the Drive week-set folder.

The input command must use the current Drive workbooks. Do not use `work/planning` as a fallback when Drive is unavailable.

In `recent-logs.xlsx`, the planner's morning and evening `PofC-text` rows supply the complete confession prayers; `PofC` supplies their Scripture references. Update reads fields by label, including inserted rows. Older planners without `PofC-text` use the song catalog's prayer lookup.

## 2. Build the worship documents

For October 4, use the communion templates for both services:

```powershell
python scripts/update-automation.py --date 2026-10-04 --communion
```

`--communion` selects `morning-bulletin.docx` and `evening-bulletin.docx` in `work/templates/communion` for both services. Without the flag, update uses the pair in `work/templates/standard`. Include the flag on each communion run; the selection is not remembered.

| Document | Template used |
| --- | --- |
| Standard morning/evening bulletin | `work/templates/standard/morning-bulletin.docx` and `evening-bulletin.docx` |
| Communion morning/evening bulletin | `work/templates/communion/morning-bulletin.docx` and `evening-bulletin.docx` |
| Sermon word study | `work/templates/word_study_template.docx` |
| Movie discussion notes (`MOV` in the planner) | `work/templates/discussion_template.docx` |

Update fills these templates without modifying them. Last week's documents in `previous` are reference copies, not the templates used for generation.

For a standard service, run:

```powershell
python scripts/update-automation.py
```

Wait for **Complete**. The script reads the selected Sunday from `work/input-state.json` and creates the morning and evening files in:

```text
work/output
```

It generates:

- bulletins from the named standard or communion Word templates;
- sermon Word studies using `work/templates/word_study_template.docx`;
- movie (`MOV`) discussion notes using `work/templates/discussion_template.docx`;
- praise chord sets in planner song order;
- the website draft at `work/desktop/worship-highlights.json`.

Missing inputs are listed in `work/desktop/needs-attention.txt`. Exit code 2 means that some outputs need attention; successfully generated independent outputs are still retained. Exit code 1 means the update failed.

Update archives older dated generated documents from DESKTOP and OUTPUT under `work/_archive/previous-generated`. An open file may need to be closed before it can be archived. A supplied Scripture reading must have a mapped place in the bulletin; the script must not silently omit it. A blank reading preserves its template mapping for later weeks.

For an offline rerun, use the verified local Scripture cache:

```powershell
python scripts/update-automation.py --offline
```

For a communion rerun, keep the flag: `python scripts/update-automation.py --communion --offline`.

If the chord folder is not found automatically, provide it:

```powershell
python scripts/update-automation.py --chords "G:\My Drive\kenton\_worship\Praise\Chords"
```

To update only the website draft:

```powershell
python scripts/update-automation.py --website-only
```

## 3. Review the output

Open both services in `work/output`. Check every rendered page before publishing:

1. Date, service, sermon, speaker, songs, and hymns.
2. Responsive call to worship and the full unison confession prayer.
3. Song order and chord-set headers.
4. Page breaks, spacing, fonts, and readable Scripture.
5. Handout content and layout against the retained reference pattern.
6. Website details in `work/desktop/worship-highlights.json`, when applicable.
7. Communion wording and placement in both bulletins when `--communion` was selected.

Word studies must contain the complete NIV main passage and exact NIV cross-references. Use 14-point Scripture/body text and 16-point main/word headings; 13-point body text is allowed only when required to fit. A Word study exporting to more than one page is not ready to publish. MOV handouts keep their separate two-page format.

Correct planning facts in the workbook or authored material, then rerun steps 1 and 2. Do not publish an output that has not been visually reviewed.

## 4. Publish the reviewed week-set

After review, run:

```powershell
python scripts/publish-automation.py --reviewed
```

Success creates a new folder under:

```text
G:\My Drive\kenton\_worship\week-sets\YYYYMMDD
```

The command checks that the reviewed files still match the generated output and copies the Word and PDF files together. It does not publish to the live website, commit Git changes, or use a local week-set fallback.

To publish a selected date, the date must match the completed update:

```powershell
python scripts/publish-automation.py --date 2026-10-04 --reviewed
```

To replace an existing Drive week-set after reviewing the replacement:

```powershell
python scripts/publish-automation.py --reviewed --force
```

`--force` archives the existing Drive week-set before replacing it. It does not bypass review, completed-update checks, or file-hash checks.

## Website panels only

Prepare and review the website draft:

```powershell
python scripts/update-automation.py --website-only
```

Then apply it to the configured local website project:

```powershell
python scripts/publish-automation.py --website-only --reviewed
```

This updates the local website data file configured by `website.json`. Live deployment is separate. If website publication fails after a Drive publication, correct the issue and retry the website-only command.

## Important locations

- Planning workbooks: `G:\My Drive\kenton\_worship` (read-only source)
- Working files: `work/desktop`
- Review files: `work/output`
- Editable templates: `work/templates`
- Previous week reference copies: `work/desktop/previous` (not the generation templates)
- Drive week-sets: `G:\My Drive\kenton\_worship\week-sets`
- Update log: `work/desktop/automation.log`
- Missing-input report: `work/desktop/needs-attention.txt`

Church content stays under the ignored `work/` directory. The scripts treat Drive source documents and your named templates as read-only. To change a layout, edit the appropriate DOCX in `work/templates`, save and close it, then rerun update.

You do not need to interpret or edit the JSON files in DESKTOP. They are working data for the scripts and AI-authored material. For document review, open `work/output`; for a problem, read `work/desktop/needs-attention.txt`. DESKTOP's Word/PDF files are working copies, not a second review set.

Handout templates supply layout. Current teaching content must come from AI/user-authored material or a matching authored study; old example text is never substituted for this week's passage or movie. The word-study PDF is a visual reference; generation uses the DOCX.

## If a command stops

- Start with `work/desktop/automation.log` and `work/desktop/needs-attention.txt`.
- If the planning workbooks or previous week-set are wrong, rerun step 1.
- If generated content is wrong, correct the source and rerun step 2.
- If Word cannot export PDFs, run the command from the normal VS Code terminal with Microsoft Word available.
- If the Drive week-set already exists, review the replacement and use `--force` only when replacement is intended.
- If Drive is unavailable, stop; do not publish to a local substitute.

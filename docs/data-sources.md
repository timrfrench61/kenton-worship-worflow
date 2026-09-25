# Data sources

## Known sources and pending details

The source categories below come from the workflow proposal. Exact filenames, folder paths, workbook tabs, column names and access rules have not been verified.

| Source | Intended use | Details to confirm |
| --- | --- | --- |
| Recent service logs (Excel) | Historical record, continuity, repetition checks | Workbook, tabs, date/service fields |
| Praise song list (Excel) | Select and identify songs | Stable identifiers, titles, arrangements, keys |
| Hymn list (Excel) | Select and identify hymns | Hymnal/edition, hymn numbers, tune references |
| Call-to-worship list (Excel) | Select approved readings | Reference/text fields and source |
| Prayer-of-confession list (Excel) | Select approved readings | Reference/text fields and source |
| Google Drive chord library | Assemble praise chord packets | Folder, file types, arrangement naming, permissions |
| Planning workbook | Shared facts for the coming Sunday | Whether one already exists and who edits it |
| Sermon and handout documents | Word studies and sermon outlines | Locations, formats, approved versions |
| Prayer reports/private Facebook | Restricted care history and prayer bulletin | Authorized capture method, audience and retention |
| Existing bulletins and layouts | Reference for reusable templates | Representative AM/PM documents and print requirements |
| Website/Facebook/YouTube | Approved content destinations and links | Existing publishing process and responsible person |

## Configuration

Copy `config/settings.example.toml` to `config/settings.local.toml`. Store machine-specific absolute paths only in that ignored local file. The example defines folder roles, not real locations. Paths with Windows backslashes can use TOML single-quoted strings.

The current scaffold does not load this file. A later command will accept an explicit settings path and validate it before touching content. Configure existing Drive folders; do not reorganize the church library just to match example names.

Prefer relative source references within an explicitly configured library. If source folders are shared differently, configure distinct roots. Never place prayer data within a public output root.

## Source ownership

Keep a single editor-authority for each kind of information:

- Planning spreadsheet: upcoming shared service facts.
- Reference workbooks and chord library: song and reading identities and source files.
- Handout documents: reviewed long-form content.
- Restricted prayer record: private prayer details and history.
- Final manifest and historical log: what was actually delivered.

The generated weekly JSON snapshot is derived from these designated sources. Do not repair a generated bulletin as the only place a shared fact is corrected.

## Repository hygiene

Commit only invented sample data and sanitized reusable templates. Keep actual spreadsheets, chord/song content, documents, prayer requests, personal contact details, credentials and generated artifacts in Drive.

The root ignore file covers local settings, secret files, environment folders and conventional output folders. Ignore rules do not prevent every accidental disclosure and do not untrack previously committed files. Review staged changes before committing. Do not copy working church material into an arbitrary repository folder.

A template belongs here only after removing personal information and content that should remain in Drive. A content-bearing or licensed template may instead remain in Drive and be referenced by configuration.

## First source review

Inspect one representative week, its AM/PM bulletins, and the relevant workbook headers. Document the actual mapping, date conventions, duplicates, missing identifiers and file types. Use synthetic fixtures for tests. Confirm whether “Google cloud” means Google Drive desktop files for all material; other storage would need a separate access decision.

Do not automate Facebook capture, Drive permissions or publishing until the access method and intended audience have been established.

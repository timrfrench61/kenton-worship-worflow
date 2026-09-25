# Architecture

## Boundaries

Keep one small Python package, a command-line entry point, and ordinary files. No GUI, database, background service, workflow engine, or plugin framework is needed for the first version.

| Location or participant | Responsibility |
| --- | --- |
| GitHub repository | Python code, safe configuration examples, documentation, sanitized templates, tests with invented data |
| Google Drive | Working spreadsheets, chord/song libraries, weekly content, generated documents, prayer records, archives |
| Python | Validate inputs, normalize spreadsheet data, resolve file references, generate repeatable outputs, record state |
| AI/Codex | Suggest wording, reason about selections, draft sermon-related material from supplied sources, flag inconsistencies |
| People | Verify meaning, theology, factual accuracy, song arrangements, private information, final approval and publishing |

Start with Google Drive's locally available files. Confirm files can actually be read; a cloud placeholder is not a usable input. Add Drive APIs only if a concrete requirement makes them necessary.

## One weekly plan

Use an ISO Sunday date, such as `YYYY-MM-DD`, to identify a week, with distinct `morning` and `evening` service sections. Both services use a consistent field vocabulary. A service can explicitly be marked as not scheduled.

Initially, the designated planning spreadsheet remains the editable authority for shared service facts. Python will derive a `week.json` snapshot in that week's Drive folder. That snapshot is the common input for a generation run, not a second place to edit the same facts. Correct the source and regenerate. If planning eventually moves to JSON, make that an explicit migration.

Proposed contents:

- Date, theme, liturgical color, source references and schema version.
- Each service: scheduled flag, sermon title/text/topic, call to worship, prayer of confession, ordered praise songs and hymns, special music, announcements.
- References to handouts and approved public publishing text.
- Build metadata identifying the inputs used.

Finalize field names and required fields only after inspecting real spreadsheet headers and a representative Sunday. Use stable song references plus arrangement/key where available; matching title alone is insufficient.

Prayer details belong in a separate restricted record and private generation path. Keep them out of the general weekly snapshot and public publishing inputs.

## Files and state

A proposed Drive layout, adaptable to existing folders:

```text
Kenton/
  Reference/                 Existing logs, song libraries and source materials
  Weeks/YYYY-MM-DD/
    week.json                Derived shared plan
    drafts/                  Review copies
    approved/                Approved final outputs
    manifest.json            Source/build references and artifact status
  Archive/YYYY-MM-DD/        Record of what actually happened
  Private/                   Restricted prayer plans, outputs and history
```

Folder names do not enforce privacy. Google Drive sharing must separately restrict private folders. Keep the private location outside any broadly shared publishing folder.

Start with a small manifest when generation is implemented. Record source file references/fingerprints, generation time, output paths, and per-artifact review status. Weekly status can be planned, drafted, approved, published, or archived; publication details belong to individual outputs because destinations may be completed at different times.

A changed source or regenerated artifact invalidates that artifact's prior approval. Archive the final delivered version with actual service changes and publication links. Preserve past weeks rather than regenerating over them.

## Operational rules for future commands

- Resolve paths from local configuration; never embed one person's Drive path in code.
- Read source libraries without modifying them. Missing/ambiguous references stop affected output generation with a useful message.
- Validate a complete input set before writing. Use temporary files and replace only successful outputs; keep prior approved versions.
- Keep generated paths inside the configured destination and reject source/destination overlap.
- Make retries predictable: do not duplicate archives, publication records, or outputs.
- Keep private content and credentials out of console output, logs, fixtures, and Git.
- Local file replacement does not make an entire Drive sync transaction atomic. Keep one editor per week and confirm sync before treating another device's copy as current.

## AI boundary

AI drafting is separate from deterministic production. A draft must not silently replace an approved sermon title, Scripture reference, song, or prayer item. Use only the material needed for the task and only authorized private information. Generation should consume reviewed content without requiring a live AI call.

Publishing starts as a manual step using reviewed files and copy-ready text. Automated publishing is a separate future feature, with explicit destination and approval tracking.

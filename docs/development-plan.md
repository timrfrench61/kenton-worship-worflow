# Development plan

Implement one usable step at a time. Add libraries only for a demonstrated need; avoid a GUI, database, scheduler, generic workflow engine or elaborate class hierarchy.

## Phase 0: foundation (included)

- Documentation for boundaries, sources, weekly operations and implementation order.
- Installable Python package with help/version command.
- Safe configuration example and repository ignore rules.
- Placeholders explaining the purpose of templates, tests and scripts.

No church-content processing or network integration is included.

## Phase 1: inspect sources and agree on one week

Review a representative planning/log workbook, song lists, AM/PM bulletins and chord filenames. Confirm the real Drive folder locations and private sharing boundary. Decide which workbook is the editable weekly authority.

Deliver a documented column mapping and a small synthetic example weekly record. Agree on required fields, canceled-service behavior and song identifiers before coding the importer.

Done when one real week's inputs can be traced to every requested output without guessing.

## Phase 2: configuration, validation and import

Add a small configuration loader using the standard library. Then add the spreadsheet reader required by the actual file format. Introduce a read-only validation command and a separate explicit snapshot-generation command.

Validate dates, required fields, missing/ambiguous files, destination boundaries and source overlap. Keep private prayer inputs separate. Test with synthetic workbooks and temporary directories.

Done when an invalid input produces actionable errors without partial output, and the same source consistently produces the same normalized service data.

## Phase 3: first bulletin

Generate a morning bulletin using a reviewed layout and the shared snapshot. Compare its rendered pages with the approved reference. Add evening support using the same approach, with explicit support for no evening service.

Done when shared facts are correct, print layout is approved, failures preserve the previous output, and changed inputs invalidate approval.

## Phase 4: supporting materials

Resolve and assemble existing chord arrangements; add handout references and production where useful. Implement the private prayer bulletin as a separate path with restricted destinations.

Done when song/key/order checks pass and public outputs cannot ingest prayer records. Test behavior and file boundaries, not merely function names.

## Phase 5: publishing preparation and archive

Produce copy-ready public website/social/broadcast drafts. Track reviewed outputs, manual publishing results and recording URLs. Save actual service changes and update the historical log without duplicates.

Done when a completed week can be traced from source snapshot to approved/delivered files and actual history; retrying does not duplicate records.

## Later, only as needed

Consider direct Drive access, website integration or channel-specific publishing after the manual workflow works reliably. Scheduling and automatic AI calls are not prerequisites.

## Development checks

During this foundation phase, install the package and check both the module and installed command with `--help` and `--version`. Future behavior tests can start with Python's built-in `unittest`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

There are no behavior tests yet because no content-processing behavior exists. Before a feature is declared complete, add the meaningful checks listed for its phase, including document rendering when layout matters.

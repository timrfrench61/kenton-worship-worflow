# Kenton workflow

- Read `docs/01-kenton-workflow-001.md` first. It is the current specification.
- Documents in `docs/_archive` describe retired work. Do not reintroduce those workflows.
- Use `scripts/input-automation.py`, `scripts/update-automation.py`, and `scripts/publish-automation.py`.
- DESKTOP is `work/desktop`. OUTPUT is `work/output`. Keep church content under Git-ignored `work/`.
- One day at a time: never add date subfolders to DESKTOP or OUTPUT. Input copies the two Drive workbooks into `work/planning`, not DESKTOP. Last week's files come from the Drive `week-sets` folder and go into `work/desktop/previous`; OUTPUT is reserved for generated documents. Input is standalone and must not import `src`.
- Google Drive and planning workbooks are read-only inputs. Publish only to local `work/week-sets`.
- Planning workbooks come directly from `G:\My Drive\kenton\_worship`. The user has rejected the files in `work/planning`; never use those as a fallback. Preserve actual source filenames and log complete paths.
- Use last week's retained Word templates. Change mapped content while preserving layout and standing text. Do not use the retired spacing engine or separately compose bulletin PDFs.
- Word exports the PDF from the generated DOCX. Never claim an unrendered output has passed visual review.
- AI/Codex or the user supplies target words, interpretations, and discussion questions. Python must not invent these or silently substitute missing text.
- Use plain-text logs and actionable missing-input messages. Keep the three-stage workflow readable.
- Praise-song validation ignores trailing parenthesized page references on both names being compared (including `(II4)`). Preserve the complete original titles for printed output and keep meaningful arrangement subtitles.
- Preserve previous week-sets and reviewed output. Publication requires the user's review indication.

## Authority and division of work

- The user's workflow is authoritative. AI suggestions about stages, inputs, outputs, naming, or layout are proposals, not specifications. Do not silently implement a different workflow.
- Use AI for analysis, explanation, drafting, and identifying ambiguities. Implement repeatable operations in ordinary Python with explicit inputs, outputs, and failure behavior.
- Use approved templates for visual design. AI judgment and successful text extraction are not evidence of a satisfactory layout.
- Make the smallest change needed for the requested outcome. Do not add a framework, extra stages, or a redesign to fix a local defect.
- Investigate routine implementation details independently. Ask only when an unresolved decision changes the user's intended workflow or content.

## Required verification before reporting a script fixed

1. Establish the interpreter used by the user's VS Code terminal: executable path, Python version, and installed dependencies. Codex's bundled Python is a different environment unless demonstrated otherwise.
2. Reproduce the reported command and failure before changing code when possible. If reproduction is unavailable, identify the evidence supporting the diagnosis.
3. Test the command-line entry point, not only imported functions. Use the user's interpreter when accessible. Keep real publication out of tests; exercise it with temporary fixtures.
4. For dependency or installation changes, test installation from declared dependencies in a clean environment. Test that input preparation works without document/PDF dependencies, and exercise the relevant failure path.
5. Test the corrected behavior and relevant regressions. Distinguish simulated Word export from a real Word export, and structural checks from visual review.
6. Report the interpreter/environment tested, command or behavior verified, and any remaining gap. If the user's interpreter is inaccessible, explicitly say that their environment remains unverified. Do not present a test count as proof of end-to-end readiness.

These are required working practices, not a claim that every check is already automated. See `tests/README.md` for the verification procedure. Do not silently install into or change the user's global Python environment to make a test pass.

- Update reads the completed `work/input-state.json`, the input-created workbook copies in `work/planning`, and templates in `work/desktop/previous`. Write temporary.json and content.json directly under DESKTOP; generated files go directly under DESKTOP and OUTPUT. Do not resurrect dated folders or current-week.json.

- Reruns replace existing working copies and generated files. ATTENTION is advisory: never block all of update on an input completion flag or on another document's missing data. Attempt each service/output independently; report outputs that could not be produced without fabricating missing content.

- Map Study-words from the planner. Generate word-study worksheets and standard MOV discussion prompts without demanding target_words or discussion_questions in content.json. That file is optional. Discover actual praise/chord folders under the worship source; do not assume a folder named praise-chords. Report shared source failures once.

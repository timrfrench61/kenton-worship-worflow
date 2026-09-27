# Verification

Use the Python executable recorded in `work/python-environment.json` to reproduce the user's command. Record its version and available dependencies; the automatic project environment is a separate interpreter. Do not install into the global interpreter.

Run the focused regression suite with the project interpreter:

```powershell
.automation-venv/Scripts/python.exe -m unittest discover -s tests -v
```

The handout tests use synthetic documents. They check subject matching, unchanged MOV copies, template mapping, untouched package parts, removal of Greek, verified quotation replacement, missing authored fields, ambiguous sources, and the real update script entry point against isolated fixtures. The fixture entry-point test substitutes workbook gathering and Word export; its PDFs are blank two-page test files, not a visual review. It also checks that one failed document does not block the other service and that stale handouts are archived.

The publish tests invoke the real command-line script with temporary project and destination folders. They verify new publication, refusal to overwrite without `--force`, full-folder replacement with an archived previous set, recovery after a simulated final-move failure, and enforcement of review, completed-update, and hash checks even with `--force`. No real Drive publication occurs during these tests.

For real verification, run `scripts/update-automation.py --check --offline`, then `scripts/update-automation.py --offline` with the user's interpreter and current input state. Existing Scripture caches are required for offline bulletin generation. Preserve earlier reviewed output, inspect `work/build.json` and `work/desktop/needs-attention.txt`, and distinguish unrelated output failures from handout results.

Real Microsoft Word must export the generated DOCX files. Render those PDFs to images and inspect every page before claiming visual review. Source/DOCX byte equality establishes template fidelity but is not visual verification. Do not run real publication as a test; publication requires the user's review indication.

If dependencies change, also test installation from declared dependencies in a clean virtual environment and verify that input preparation does not need document/PDF libraries. No dependency changes are needed by the handout generator update.

The NIV reader tests use synthetic source HTML to verify exact text extraction, footnote removal, small-capital rendering, nonconsecutive verse selections, wrong-translation/reference/verse rejection, cache integrity, and offline missing-source behavior. Real word-study validation must separately retrieve NIV source pages. Cleanup tests verify that successful CLI runs remove staging, failed runs archive diagnostics, altered output prevents cleanup, and cleanup refuses paths outside immediate `.update-*` children of `work`.

Word-study excerpt tests reject changed wording, capitalization, partial words, and internal omissions. The CLI fixture simulates a two-page Word study to confirm that the one-page requirement prevents a completed build without blocking the evening handout. Real one-page verification still requires Word export and visual inspection.

Single-verse tests verify that old excerpt fields are ignored in favor of the full source verse. Generated Word studies must contain no commentary, Greek, or synthesis and must remain usable as retained templates on a later run.

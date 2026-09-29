# Verification

YouTube inventory: `python -m unittest discover -s tests -p test_youtube_inventory.py -v` covers pagination, public-only storage, preserved editorial labels, missing videos, channel mismatch, failed reads, and real CLI sync/list/label with a fake API. Live access requires the read grant. On 2026-09-29 the declared YouTube dependencies installed in a clean `work/youtube-inventory-test-venv`; `pip check`, Los Angeles date conversion, and the real CLI missing-authorization path passed. The actual catalog remains empty until authorization and a successful channel fetch.

Video repair: `python -m unittest discover -s tests -p test_video_repair.py -v` uses standard-library Python plus real FFmpeg/ffprobe. It checks both CLI entry points with synthetic color/tone movies and slides, including original-audio retention, picture placement, alternate file-audio/duration mapping, invalid plans, and source/output protection. Set `KENTON_VIDEO_TEST_ARTIFACTS` to a new local folder to retain synthetic artifacts for separate visual inspection. No real service or account publication is used.

Audio repair has a separate focused suite: `python -m unittest discover -s tests -p test_audio_repair.py -v`. It runs with standard-library Python and real FFmpeg/ffprobe; no document libraries are needed. It exercises the local repair CLI on generated video/audio, rejects silence and changed files, preserves sources/results, and tests YouTube receipts and request bodies with mock services, including an actual script entry point in a subprocess. No YouTube account action is performed. Optional dependencies are declared separately in `requirements-youtube.txt`; install them only into a local environment. Live OAuth/upload and listening review are separate checks described in the audio workflow document.

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

Word-study mapping checks 14-point body runs and 16-point main headings. Real layout validation still requires a one-page Word export and visual inspection; reduce authored reference counts instead of shrinking below 13 points.

Website tests exercise the publish CLI against a temporary website: exact previous-week rollover, stale-link/speaker removal for upcoming services, preserved photos, mandatory review, concurrent-edit protection, backup, idempotent publication, and skipped-week rejection. Real `update-automation.py --website-only` reads planning copies without Word export. Verify the actual local homepage after authorized website publication; neither this command nor the tests deploy to the live server.

# Kenton Worship Workflow

Prepare weekly worship documents, repair recording audio, and replace selected video pictures or add slides. Start with the task below; the folder map follows the instructions.

Run commands in the VS Code PowerShell terminal from the project root:

```powershell
cd C:\repos\kenton-worship-workflow
```

Use Python 3.11 or newer. Worship-document PDF export requires Microsoft Word. Audio and video repair require FFmpeg and ffprobe on PATH. Keep Google Drive connected when reading planning files or publishing a week-set.

## Weekly worship documents

1. **Load the current planning workbooks.** Change the date to the Sunday you are preparing.

   ```powershell
   python scripts/input-automation.py --date 2026-10-04
   ```

   Success: **INPUT complete**. Each run refreshes both workbook copies from `G:\My Drive\kenton\_worship` and replaces the previous week's local reference copies. Drive sources are read-only.

2. **Build the documents.** For standard services:

   ```powershell
   python scripts/update-automation.py
   ```

   For communion in both services, use this command instead:

   ```powershell
   python scripts/update-automation.py --communion
   ```

   Update uses the Sunday selected by input. Include `--communion` on every communion run; it is not remembered. The terminal reports generated files and any **ATTENTION** items. An incomplete output does not prevent independent outputs from being attempted.

3. **Review the Word and PDF files in [work/output](work/output/).** Check every page: date, service, Scripture, confession prayer, songs, sermon/movie, handout content, and communion where selected. Word studies must fit on one readable page; movie discussion notes use their two-page format. Resolve missing outputs before publication.

4. **Publish after review.**

   ```powershell
   python scripts/publish-automation.py --reviewed
   ```

   Success: **PUBLISH complete**, with the destination under `G:\My Drive\kenton\_worship\week-sets\YYYYMMDD`. To intentionally replace an already published set after reviewing the new files, add `--force`; the replaced set is archived on Drive.

### Templates and teaching material

| Document | Template |
| --- | --- |
| Standard bulletins | `work/templates/standard/morning-bulletin.docx` and `evening-bulletin.docx` |
| Communion bulletins | `work/templates/communion/morning-bulletin.docx` and `evening-bulletin.docx` |
| Sermon word study | `work/templates/word_study_template.docx` |
| Movie discussion notes (`MOV` in the planner) | `work/templates/discussion_template.docx` |

To change a layout, edit the appropriate template, save and close it, then rerun update. Generation does not modify your templates. `work/desktop/previous` holds reference copies, not generation layouts.

Templates supply layout. AI/user-authored material or a matching authored study supplies the current teaching content. A missing study needs that content prepared; the script does not substitute last week's teaching or invent a worksheet. The word-study PDF is a visual reference; generation uses the DOCX.

**Review only `work/output`.** DESKTOP contains working copies, logs, caches, and internal JSON. You do not need to interpret or edit those JSON files. Read `work/desktop/needs-attention.txt` for unresolved items. Update archives older dated generated documents; close any older Word files that prevent archiving.

### NIV word-study research

Collect six Old Testament and six New Testament verses for each study word:

```powershell
python scripts/research-word-study.py --passage "Matthew 5:8" --words Pure heart see God --output work/research/2026-10-04-word-study-six-per-testament.json
```

Success prints **Research saved** and creates readable Markdown alongside the JSON. Use a fresh output filename for each run. Settings are centralized in `application.json`; the API key is in ignored `work/credentials/application.json` or `API_BIBLE_KEY`. This uses standard Python and makes no LLM calls. The results supply research for AI/user selection, not a completed handout. See [endpoint development](docs/10-bible-endpoints.md) for configuration and optional model choices.

### Website panels only

1. Prepare the website draft:

   ```powershell
   python scripts/update-automation.py --website-only
   ```

2. Review the proposed service details, then apply them to the local website project:

   ```powershell
   python scripts/publish-automation.py --website-only --reviewed
   ```

Success updates the local project configured in `website.json`. Live deployment is separate.

Full reference: [weekly worship workflow](docs/01-kenton-workflow-001.md).

## Audio repair

Use this when a recording needs loudness correction. If it also needs picture replacement, complete the video steps below first, then repair the final recording's audio.

1. **Choose a source recording.** Use a local MP4/MKV, or download from the existing YouTube inventory. With the YouTube environment already configured:

   ```powershell
   .\work\youtube-venv\Scripts\python.exe -m pip install -U -r requirements-download.txt
   .\work\youtube-venv\Scripts\python.exe scripts/download-youtube.py --date 2026-09-20 --service evening
   ```

   Success: **Downloaded**. This example saves `work/audio-repair/source/20260920-evening.mp4`. Change the date and service together. If the environment or YouTube access is not set up, use the complete [YouTube setup instructions](data/README.md) first. Downloading requires a matching inventory entry.

2. **Repair the audio into a new job folder.** For the downloaded example:

   ```powershell
   python scripts/repair-audio.py work/audio-repair/source/20260920-evening.mp4 --output-dir work/audio-repair/20260920-evening
   ```

   For a local recording, substitute its full path. Success: **Complete**, with `repaired.mp4` and `repair.json` in the job folder. Use a new folder for another attempt; preserve reviewed results.

3. **Listen to `repaired.mp4`.** Check speech, music, quiet passages, and transitions. Loudness checks do not establish listening approval or correct a poor recording mix.

4. **Record acceptance after listening.**

   ```powershell
   python scripts/audio-repair-accept.py work/audio-repair/20260920-evening/repair.json
   ```

   Success: **Accepted** or **Already accepted**. If only the peak check failed, follow the [audio workflow](docs/01-kenton-audio-repair-001.md) to review the partial result before accepting it.

5. **Upload after review and upload authorization are in place.** Replace `VIDEO_ID` with the original service's ID from the lookup and use the matching title:

   ```powershell
   .\work\youtube-venv\Scripts\python.exe scripts/find-youtube-video.py --date 2026-09-20 --service evening
   .\work\youtube-venv\Scripts\python.exe scripts/youtube-audio.py upload work/audio-repair/20260920-evening/accepted.json --original-id VIDEO_ID --title "Kenton Sunday Service - September 20, 2026 - Evening (AUDIO FIXED)" --reviewed
   ```

   Success: **Private upload** and a new URL. Check processing and playback in YouTube Studio before changing visibility or adding it to a playlist. The original video remains unchanged.

All YouTube operations target **Kenton Church EPC** (`@kentonchurchepc8338`), channel `UCQv5lUpAVNhfV7RS1Hzbf-Q`, as configured in `youtube.json`. The signed-in account does not select a different target; personal and Kenton Session channels are excluded. Inventory labels change the local catalog only.

Full reference: [audio repair workflow](docs/01-kenton-audio-repair-001.md).

## Video repair

Use this to replace filmed movie playback with the matching movie picture, or to show Praise Band/Piano slides during missed camera coverage. The Kenton choice is to **keep the service audio** throughout these picture changes.

1. **Prepare an edit plan.** Substitute your actual recording path:

   ```powershell
   python scripts/plan-video-repair.py "D:\Recordings\Sunday Service.mkv" --output work/video-repair/plan.json
   ```

   Success creates `plan.json` and the source-stream inventory. Supply the replacement episode file, slide images, and exact service/source timestamps. Ask Codex to fill the plan from those inputs; you do not need to author JSON unaided. Complete the starter's unset times and paths before rendering.

2. **Validate the completed plan.**

   ```powershell
   python scripts/repair-video.py work/video-repair/plan.json --check
   ```

   Success prints the validated timeline without rendering. Check that the intervals and selected audio track are the ones you intend.

3. **Render into a new job folder.**

   ```powershell
   python scripts/repair-video.py work/video-repair/plan.json --output-dir work/video-repair/service-repair
   ```

   Success produces `work/video-repair/service-repair/repaired.mp4` and `video-repair.json` after automated checks.

4. **Watch and listen.** Review every replacement, both sides of each edit, slide readability, picture/sound synchronization, and the full service duration. A valid timeline does not prove synchronization.

5. **Repair the final audio if needed.**

   ```powershell
   python scripts/repair-audio.py work/video-repair/service-repair/repaired.mp4 --output-dir work/audio-repair/service-video-final
   ```

   Continue with listening, acceptance, and reviewed upload in the audio steps above, using this job's paths. The current upload workflow requires an audio repair/acceptance report; `video-repair.json` is not that report. Local picture rendering does not upload or change YouTube videos.

Full reference and edit-plan format: [video repair workflow](docs/01-kenton-video-repair-001.md).

## Folder map

| Location | What belongs here |
| --- | --- |
| `work/output/` | Current worship documents for visual review |
| `work/templates/` | Your editable bulletin, word-study, and discussion templates |
| `work/planning/` | Refreshed copies of the two Drive planning workbooks |
| `work/desktop/previous/` | Selected previous week's reference files |
| `work/desktop/` | Internal working copies, authored content, logs, Scripture cache, website draft |
| `work/audio-repair/` | Recordings, audio jobs, acceptance reports, and credentials |
| `work/video-repair/` | Picture-edit plans, assets, rendered videos, and reports |
| `work/youtube-venv/` | Local Python environment for YouTube tools |
| `work/youtube-inventory/backups/` | Recovery copies from catalog changes |
| `work/_archive/` | Preserved older output, failed-run diagnostics, and development artifacts |
| `data/youtube-videos.json` | Git-tracked public inventory and editorial labels |
| `youtube.json`, `website.json` | YouTube target and local website configuration |
| `docs/` | Current workflow references; `docs/_archive/` contains retired workflows |
| `scripts/`, `src/`, `tests/` | Commands, implementation, and tests |

Church content, credentials, recordings, and local backups stay under Git-ignored `work/`. Published worship week-sets go only to `G:\My Drive\kenton\_worship\week-sets\YYYYMMDD`. Media jobs do not belong in the worship-document output folder or Drive week-sets.

## When something needs attention

| Problem | Next step |
| --- | --- |
| Planning changes are missing | Save the Drive workbook, then rerun input and update for the selected Sunday. |
| Worship document was skipped | Read `work/desktop/needs-attention.txt`; the detailed log is `work/desktop/automation.log`. |
| Word file cannot be replaced or archived | Close the file in Word and rerun the command. |
| Study or discussion content is missing | Have AI/user-authored material prepared for the planner's passage or movie. |
| Recording download needs sign-in | Use the audio workflow's browser-cookie option. |
| Media output folder already exists | Choose a new job folder to preserve the earlier result. |
| Upload stopped or its outcome is unclear | Check the saved receipt and YouTube Studio before retrying. |

Developer verification procedures are in [tests/README.md](tests/README.md). Keep test fixtures and environments in temporary folders or `work/_archive`, away from active review files.

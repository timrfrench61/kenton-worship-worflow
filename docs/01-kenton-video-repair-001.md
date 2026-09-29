# Kenton video repair 001

Scope: picture replacement and slides. For audio-only repair, use [the audio workflow](01-kenton-audio-repair-001.md). Start at the [project README](../README.md) for the folder map and current task.

## Requested repairs

1. Snip out HSWTL video and insert picture from a file.
2. Add Praise Band slides when the camera is not on the Praise Band.
3. Add Piano slides when the camera is not on the Piano.

**Confirmed September 28, 2026: use the HSWTL file's picture and keep the service audio.** Praise Band and Piano slides also keep service audio. With these choices the renderer uses the original soundtrack continuously, without cutting it at picture-edit boundaries. Output audio is encoded as AAC, so this preserves the performance and timing, not the compressed source bytes.

## Plan and responsibilities

Use a local original recording, the matching HSWTL source file, and supplied slide images. AI or the user identifies the exact intervals where the camera picture needs replacing. Python validates and renders those explicit decisions. It does not guess when a musician is off camera, choose an episode, generate slide content, or infer synchronization from similar-looking frames.

The implementation consists of:

| Command | Purpose |
| --- | --- |
| `scripts/plan-video-repair.py` | Inspect the recording and create an editable plan with unset edit times |
| `scripts/repair-video.py PLAN --check` | Validate sources, audio choices, and intervals; print the resulting timeline |
| `scripts/repair-video.py PLAN` | Render and verify a new MP4 for viewing/listening review |

Both commands use `src/kenton_workflow/video_repair.py`. They require Python 3.11 or newer and FFmpeg/ffprobe, with no added Python packages. They reuse the audio workflow's file hashing, media probing, and report-writing helpers. There are no Google calls or credential requirements for local video editing.

Church recordings, slides, edit plans, and rendered output belong under Git-ignored `work/video-repair/` or an explicit local source path. Do not use the document workflow's DESKTOP, OUTPUT, or Drive week-sets for video jobs. Sources are read-only. A new render uses a new job directory and refuses an existing destination, preserving reviewed results and failed diagnostics.

## 1. Prepare the edit plan

From the repository root:

```powershell
python scripts/plan-video-repair.py "D:\Recordings\Sunday Service.mkv" --output work/video-repair/plan.json
```

The recording path is an example. The command writes `plan.json` and `plan.source.json` (FFprobe stream inventory). It does not overwrite either file. The starter contains three edit entries corresponding to the requested repairs, but timestamps and asset paths remain unset. Complete the needed entries, duplicate slide entries for additional slides/intervals, and remove unused entries. An incomplete starter cannot render.

AI can prepare this plan from supplied timestamps and files; the user need not write JSON unaided. A real plan still needs:

- The service recording path and selected audio track, especially for multitrack OBS recordings.
- HSWTL interval in the service recording, the correct episode file, and the matching picture interval within that file.
- Praise Band and Piano intervals where the camera is elsewhere, plus the slide image for each interval.

Export existing slides as individual PNG or JPEG images. PowerPoint/PDF conversion and creation of new artwork are outside this renderer. Slides replace the entire picture during their interval; they are not a small overlay. Different aspect ratios are fitted with black bars without cropping. Confirm that source slides have an opaque background and readable text.

The following is a **format example**, not an edit plan for a real service. All asset paths are relative to the plan file unless absolute:

```json
{
  "schema": 1,
  "source": "D:/Recordings/Sunday Service.mkv",
  "source_audio_track": 0,
  "output": {"width": 1920, "height": 1080, "fps": "30"},
  "edits": [
    {
      "type": "replace",
      "label": "HSWTL picture replacement",
      "start": "00:20:00",
      "end": "00:40:00",
      "file": "assets/hswtl-episode.mp4",
      "in": "00:00:10",
      "out": "00:20:10",
      "audio": "original"
    },
    {
      "type": "slide",
      "kind": "praise-band",
      "label": "Praise Band slide",
      "start": "00:05:00",
      "end": "00:06:15",
      "file": "assets/praise-band.png"
    },
    {
      "type": "slide",
      "kind": "piano",
      "label": "Piano slide",
      "start": "00:45:00",
      "end": "00:46:00",
      "file": "assets/piano.png"
    }
  ]
}
```

Rules:

- `start` and `end` always refer to elapsed time in the **original service recording**, not to wall-clock time or the repaired video's timeline. The start is included and the end excluded. Accept seconds or `HH:MM:SS.sss`.
- `in` and `out` select picture from the replacement file. With `audio: "original"`, this interval must exactly equal `end - start`. Align the replacement picture with the recorded soundtrack, including any introductory offset; matching durations alone does not establish lip synchronization.
- No automatic speeding up, slowing down, pausing, looping of replacement movies, or sound replacement is inferred. If the recorded playback drifted, supply separately aligned sections or prepare a deliberately synchronized replacement first.
- `source_audio_track` is the zero-based audio-track number. The starter selects 0 only if the source has exactly one audio track. Inspect the inventory when several exist. A source with no usable audio is rejected.
- Slide intervals may abut but cannot overlap another slide or an HSWTL replacement. Split intervals to make the intent explicit. Sorting entries by start time is automatic; overlapping entries are rejected.
- The output dimensions must be even integers; frame rate accepts a number or a rational such as `30000/1001`. The starter uses 1920×1080 at 30 fps; choose the intended output format after inspecting the source. Boundaries are rounded on the cumulative output-frame grid, avoiding accumulated rounding drift. A sub-frame interval is rejected if it would produce no frame.
- Only one picture stream is supported in each movie input. Extra audio, subtitles, data, and chapters are not carried into the result. HDR input is rejected pending an explicit SDR conversion.

An alternate `audio: "file"` option exists only for an explicit future decision to use replacement sound. It requires usable audio in that file (and `audio_track` if ambiguous). That mode allows a different inserted duration and records the changed output positions for later edits; later `start`/`end` values still use the original recording. It is not the selected Kenton default.

## 2. Validate and render

```powershell
python scripts/repair-video.py work/video-repair/plan.json --check
python scripts/repair-video.py work/video-repair/plan.json --output-dir work/video-repair/service-repair
```

`--check` reads/probes files and prints original-to-output time mapping without rendering or creating a job. It catches missing assets, unset times, invalid tracks, overlapping/out-of-range edits, unsupported fields, and mismatched picture durations when retaining service audio. It does not confirm that an episode, slide, or camera interval is the right one.

Omit `--output-dir` for a uniquely named job. Supply full executable paths with `--ffmpeg` and `--ffprobe` if they are not on PATH. Rendering reencodes picture as H.264 and audio as 48 kHz stereo AAC. It uses hard cuts, with no transitions or loudness adjustment. Review joins for visual continuity. The renderer may repeat the last picture frame for at most one output frame to meet frame-grid rounding; it does not extend a substantially short movie to fit.

The job produces:

| File | Purpose |
| --- | --- |
| `repaired.mp4` | Completed result for review |
| `video-repair.json` | Source hashes, exact input paths, original/output mapping, chosen audio mode, expected/actual duration, checks, output hash |
| `plan.json` | Snapshot of the supplied plan; relative paths retain their original-plan meaning |
| `repair.log` | Readable progress and failures |
| `segments.txt` | Record of rendered segment order |

The report has resolved paths for every segment and the original plan path; use the original plan location when rerunning a relative-path plan. Successful runs remove only their own intermediate segment movies. Failed runs retain partial media and an incomplete report for diagnosis. Reserve space for the source-sized H.264 intermediates plus the final MP4; an explicit replacement-sound job also has PCM audio intermediates. There is no automatic retry or overwrite. An interrupted process may leave an incomplete report without a final error message; use a new destination for the next attempt.

Verification checks container, picture, and audio durations, output dimensions, stereo/48 kHz audio, unchanged source hashes, and a complete decode of the resulting MP4. The final filename and complete state are assigned only after checks pass. Exit 0 means validation/render completed; 1 means a file/media/plan error; 2 means invalid command arguments. Automated completion is not viewing/listening approval.

## 3. Review, audio repair, and upload

Watch every replacement and both sides of every boundary. Confirm the episode, slide content, camera coverage, readability, and especially synchronization between inserted HSWTL picture and original service sound. Listen through transitions. Verify the whole service duration and that all sections remain present.

If audio normalization is needed, run it **after** picture repair so its report measures the final recording:

```powershell
python scripts/repair-audio.py work/video-repair/service-repair/repaired.mp4 --output-dir work/audio-repair/service-video-final
```

Then review that final file and follow `docs/01-kenton-audio-repair-001.md` for private YouTube upload and the separately authorized old-video action. The existing upload command takes the completed **audio repair report**; `video-repair.json` is not an upload authorization. This implementation does not bypass that measured-audio requirement or create a new publication path. No existing YouTube video, playlist, website, or Drive publication is changed by planning or rendering.

## Implementation and verification record

Implementation order: explicit plan/inventory, input and timeline validation, picture/slide assembly with continuous service audio, final media verification, and existing audio/YouTube handoff. Real service edits await the actual source files and selected intervals; no content or timestamps have been guessed.

The regression suite is `python -m unittest discover -s tests -p test_video_repair.py -v`. It generates synthetic service/replacement movies with distinguishable pictures and tones plus two slide images, then invokes both real CLI scripts. It checks the rendered pictures at selected times, retained service sound versus file sound, shifted output mapping in the alternate mode, source preservation, refusal to overwrite, and actionable invalid-plan failures. These checks do not replace reviewing a real church service.

The recorded VS Code interpreter was verified as `C:\Users\timrfrench61\AppData\Local\Programs\Python\Python313\python.exe`, Python 3.13.14, with only pip 26.1.2 installed. No dependencies were installed or changed for this video workflow.

On September 28, 2026, all five video tests and all ten existing audio tests passed with that interpreter and real FFmpeg. The six-second synthetic service retained its 440 Hz soundtrack through the blue replacement picture and green/yellow slides. The explicit file-audio alternative used the replacement's 880 Hz tone and correctly mapped later slides into a five-second output. A frame strip from the chosen original-audio mode was visually inspected and showed the expected service/replacement/slides/service sequence. Artifacts are retained in `work/video-verification-002`; they are synthetic colors and tones, not a real service, readable church-slide test, or human listening approval. Real HSWTL synchronization and church-slide readability remain to be reviewed with actual media.

Technical reference: [FFmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html) for picture/audio trimming, frame-rate conversion, scaling, padding, and timestamp reset. The Python edit plan supplies the editorial decisions; FFmpeg executes them.

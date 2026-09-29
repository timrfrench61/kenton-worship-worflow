# Kenton audio repair 001

Repair a completed service recording locally, listen to it, upload the corrected MP4 privately, then explicitly decide what happens to the previous YouTube video. This is separate from the weekly document input/update/publish commands. No video is deleted, automatically made public, or silently hidden.

## Files and provenance

The September 28, 2026 conversation, **YouTube Audio Editing Limits**, described a downloadable script package, but its attachment bytes were not available through the conversation reference. These are rebuilt implementations in this repository, not a recovered copy of that package.

| Purpose | Implementation | Command |
| --- | --- | --- |
| Measure, repair, verify a local recording | `src/kenton_workflow/audio_repair.py` | `scripts/repair-audio.py` |
| Authorize, read metadata, upload, mark original | `src/kenton_workflow/youtube_audio.py` | `scripts/youtube-audio.py` |

Church media, reports, credentials, and receipts go under Git-ignored `work/audio-repair/`. Each repair uses a new job folder there. DESKTOP, OUTPUT, Drive week-sets, and their review process remain the document workflow's responsibility. Source recordings are read-only. Failed jobs retain diagnostics. Existing job folders and action receipts are not overwritten.

## Requirements

Python 3.11 or newer and FFmpeg/ffprobe are sufficient for local repair; no Python packages are required. Both executables must be on PATH, or supplied with `--ffmpeg` and `--ffprobe`. The current machine has them at `C:\ProgramData\chocolatey\bin`.

YouTube commands additionally need the packages declared in `requirements-youtube.txt`. Install them into a dedicated environment, not global Python:

```powershell
python -m venv work/audio-repair-venv
.\work\audio-repair-venv\Scripts\python.exe -m pip install -r requirements-youtube.txt
```

Use that environment's Python for the YouTube examples below in place of `python`. Scripts do not install packages or open a consent browser except when explicitly running `auth`.

## Separate access for reading, uploading, and managing

Google uses browser-based OAuth consent, not a different Google password for each operation. Do not put account passwords in scripts or JSON. The roles have separate client files and token files:

| Role | Scope suffixes under `https://www.googleapis.com/auth/` | Files in `work/audio-repair/credentials` |
| --- | --- | --- |
| read | `youtube.readonly` | `credentials-read.json`, `token-read.json` |
| upload | `youtube.upload`, `youtube.readonly` | `credentials-upload.json`, `token-upload.json` |
| manage | `youtube.force-ssl` | `credentials-manage.json`, `token-manage.json` |

Upload also needs read access to verify channel identity, the original recording, and the new video's private status. The manage scope is broader than privacy changes: Google does not provide an archive-only scope. The script restricts what it does, but its token is not an archive-only security boundary. For grant isolation use three separate Google Cloud projects with separate Desktop OAuth clients; separate token filenames alone do not establish independent Google permissions. Tokens are local plaintext credentials protected by the Windows account's folder permissions; Git-ignore is not encryption. Do not share the credentials folder.

For each role, enable **YouTube Data API v3** in its Google Cloud project, configure the consent screen and test user if applicable, create a **Desktop app** OAuth client, and save its downloaded JSON using the filename above. Select the correct Kenton channel in each consent flow. Testing-mode consent may require reauthorization; public-app verification and API upload restrictions are controlled by Google.

```powershell
python scripts/youtube-audio.py auth read
python scripts/youtube-audio.py auth upload
# Only needed when choosing a remote change to the previous video:
python scripts/youtube-audio.py auth manage
```

All operational commands require the expected `--channel-id` (the YouTube channel ID, not its handle). They check the signed-in channel and the video owner. No authorization has been performed as part of implementing these scripts.

## 1. Inspect and repair the recording

Use the original OBS recording where available. The YouTube read API retrieves metadata, not the uploaded media file. If the recording exists only on YouTube, obtain your own recording through YouTube Studio or Google Takeout first; this workflow does not implement a video downloader.

Optional metadata snapshot, using actual IDs:

```powershell
python scripts/youtube-audio.py read ORIGINAL_VIDEO_ID --channel-id KENTON_CHANNEL_ID --output work/audio-repair/original.json
```

Repair a local recording:

```powershell
python scripts/repair-audio.py "D:\Recordings\Sunday Service.mkv" --output-dir work/audio-repair/service-repair
```

The example recording path and IDs are placeholders. Omit `--output-dir` to create a uniquely named job folder. If the recording has multiple audio tracks, inspect them with `ffprobe` and explicitly select the program/board mix with `--audio-track 0` (zero based). Only the first actual video stream and selected audio stream are included; alternate audio, subtitles, and data streams are not copied. If video cannot be remuxed into MP4, rerun into a new job folder with `--transcode-video` to encode H.264.

The default is **-18 LUFS integrated loudness, -2 dBTP true-peak target, LRA 11**. These are explicit workflow defaults, not an asserted YouTube requirement. Override with `--lufs`, `--true-peak`, and `--lra`. FFmpeg measures the source, uses its measured values in a second loudnorm pass, encodes AAC at 48 kHz, and measures the actual encoded result. FFmpeg may use dynamic normalization when linear normalization cannot meet the requested constraints. This is whole-recording loudness repair, not a substitute for a live automatic gain controller or individual segment mixing.

The job contains:

- `repaired.mp4`: completed result, only created after checks pass.
- `repair.json`: source/output paths and SHA-256 hashes, settings, before/after measurements, duration, and completion state.
- `repair.log`: readable progress and failure messages.
- `repaired.partial.mp4`: retained only when a render/check fails before finalization.

Checks require loudness within 1 LU of target, encoded true peak within 0.3 dB of the requested ceiling, duration within 1 second, and unchanged source hash. Silence, missing streams, invalid targets, failed FFmpeg, and failed checks produce an incomplete report and exit code 1 (argument errors use 2). Rerunning into an existing job folder is refused; choose a new folder to preserve reviewed results.

Listen to quiet speech, loud singing, transitions, and the start/end; check audio/video synchronization. Normalization may expose room noise and cannot recover missing microphone audio or undo clipping. Automated checks do not establish listening quality. A failed loudness check requires inspection and a deliberate new target or separate audio edit; do not modify the report to force upload.

## 2. Upload privately after listening

Save explicit upload metadata as `work/audio-repair/upload-metadata.json`, for example:

```json
{
  "title": "Sunday service — audio corrected",
  "description": "Service recording with corrected audio levels.",
  "categoryId": "22",
  "madeForKids": false
}
```

Choose the actual service title, description, category, and audience designation; the example's audience/category are not an automatic classification of Kenton content. Nothing is copied blindly from another service.

```powershell
python scripts/youtube-audio.py upload work/audio-repair/service-repair/repair.json --metadata work/audio-repair/upload-metadata.json --original-id ORIGINAL_VIDEO_ID --channel-id KENTON_CHANNEL_ID --reviewed
```

The command requires a complete measured repair, unchanged MP4 hash, and explicit listening review. It uploads privately with subscriber notification disabled and saves `upload.json` alongside the report. The original is unchanged. The new upload gets a new video ID/URL; thumbnails, captions, chapters, playlists, comments, views, and website embeds are not migrated by this command.

The receipt is written before uploading begins and updated with the returned ID before verification. If upload is interrupted, the receipt intentionally blocks blind retries: inspect YouTube Studio and the receipt first. No cross-process resumable-upload recovery is implemented. If Studio confirms no upload exists, preserve/rename the failed receipt before retrying. If an upload does exist, recover its identity through deliberate operator reconciliation; do not create another copy merely because verification failed.

Wait for YouTube processing, listen to the uploaded version, check its picture and metadata, then make it public manually in Studio when approved. Unverified API projects may have uploads restricted to private visibility; resolve Google's project requirements rather than bypassing them.

## 3. Choose how to mark the original

No policy is assumed. Choose one explicit action per command after reviewing the replacement:

```powershell
# Local record only; leaves YouTube unchanged and uses the read grant:
python scripts/youtube-audio.py mark-original work/audio-repair/service-repair/upload.json --channel-id KENTON_CHANNEL_ID --action document --reviewed

# Alternatively choose ONE remote action using the manage grant:
python scripts/youtube-audio.py mark-original work/audio-repair/service-repair/upload.json --channel-id KENTON_CHANNEL_ID --action notice --reviewed
python scripts/youtube-audio.py mark-original work/audio-repair/service-repair/upload.json --channel-id KENTON_CHANNEL_ID --action unlisted --reviewed
python scripts/youtube-audio.py mark-original work/audio-repair/service-repair/upload.json --channel-id KENTON_CHANNEL_ID --action private --reviewed
```

`notice` prepends the replacement URL to the original description while preserving its title, tags, category, language, and existing description. `unlisted` or `private` changes privacy while preserving other writable status fields. Remote actions require the replacement to be processed successfully and public, so the original cannot be hidden while its replacement is still private. A live/upcoming original or scheduled publication requires manual handling.

The command saves the original metadata and intended request to `original-ACTION.json` before a remote change, then rereads the result. Failed or uncertain attempts retain the snapshot and block automatic repeats. The snapshot supports manual recovery in Studio; no delete or automatic rollback is implemented. Review any later changes before restoring earlier metadata.

## Website follow-through

After the replacement is public, check actual website and playlist links to the original ID and decide which to replace. Website service-panel configuration remains `website.json`; follow `docs/01-kenton-workflow-001.md` and its existing update/review/publish commands. Local website publication and live deployment are separate. These media scripts do not change the website, invent service dates, or claim to diagnose recording loudness from a webpage. A site-wide audit needs the actual intended URLs and is not performed by these commands.

## Verification and limits

Run `python -m unittest discover -s tests -p test_audio_repair.py -v`. Tests use temporary files and fake YouTube API responses; no real uploads or changes to an account occur. The FFmpeg test generates a quiet six-second recording and verifies real CLI repair, silence rejection, source preservation, and refusal to overwrite an existing job. Mock API tests cover private upload, altered media, channel mismatch, duplicate attempts, preservation of old metadata, and refusal to hide the original while its replacement is private.

Implementation verification on September 28, 2026 used the recorded VS Code interpreter `C:\Users\timrfrench61\AppData\Local\Programs\Python\Python313\python.exe`, Python 3.13.14, initially containing only pip 26.1.2. Real FFmpeg corrected the synthetic recording from -41.81 to -17.98 LUFS. This is a generated-tone test, not listening review of a Kenton recording. Google consent, account permissions, actual upload, and remote mutation remain unverified until credentials and a reviewed recording are supplied.

All ten focused tests passed. A clean environment at `work/audio-repair-test-venv` installed `requirements-youtube.txt` successfully (`google-api-python-client` 2.200.0, `google-auth-oauthlib` 1.4.1); `pip check` passed and offline YouTube request construction succeeded. The missing-library and missing-client-file CLI errors were verified without opening consent. After adding only the declared openpyxl dependency, the existing input CLI prepared real fixture workbooks in a temporary copied project with no document/PDF libraries installed. The user's global packages were unchanged. Test environments and the one-off verification harness remain under Git-ignored `work/`.

## Primary references

- [FFmpeg loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm): measured normalization and filter parameters.
- [Google desktop OAuth](https://developers.google.com/youtube/v3/guides/auth/installed-apps): browser consent and scopes.
- [YouTube video upload](https://developers.google.com/youtube/v3/docs/videos/insert): upload authorization, privacy, and project restrictions.
- [YouTube metadata update](https://developers.google.com/youtube/v3/docs/videos/update): writable fields and omitted-field replacement semantics.

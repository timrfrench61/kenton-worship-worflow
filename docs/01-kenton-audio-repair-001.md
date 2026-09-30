# Audio repair

Run these commands in the VS Code terminal from `C:\repos\kenton-worship-workflow`.

## 1. Install the downloader — once

```powershell
.\work\youtube-venv\Scripts\python.exe -m pip install -U -r requirements-download.txt
```

## 2. Download September 20 evening

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/download-youtube.py --date 2026-09-20 --service evening
```

Wait for **Downloaded**. The script looks up the video ID automatically from the inventory.

Morning means before noon; evening means noon onward, using `event_local_time` and `event_local_date` for original livestreams. Missing or duplicate matches print **ATTENTION** and stop before downloading. Lookup results and warnings are logged to `work/audio-repair/youtube-lookup.log`.

## 3. Repair the audio

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/repair-audio.py work/audio-repair/source/20260920-evening.mp4 --output-dir work/audio-repair/20260920-evening
```

Wait for **Complete**. The script adjusts audio levels and checks the result automatically.

## 4. Listen

Open:

```text
C:\repos\kenton-worship-workflow\work\audio-repair\20260920-evening\repaired.mp4
```

Check speech and music. September 27 is still being checked separately.

## 5. Accept after listening

If only the peak check failed, listen to `repaired.partial.mp4`. To accept the result:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/audio-repair-accept.py work/audio-repair/20260920-evening/repair.json
```

Success: **Accepted**. **Already accepted** also means this step is done. Continue to step 6; do not repeat acceptance.

## 6. Upload after approval — Python

With approval saved and upload OAuth already set up, run:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/youtube-audio.py upload work/audio-repair/20260920-evening/accepted.json --original-id EfXqhmmZgzI --title "Kenton Sunday Service - September 20, 2026 - Evening (AUDIO FIXED)" --reviewed
```

Success: **Private upload** with the new URL. Description, category, and audience setting come from the original. The original remains unchanged.

Check playback in Studio and add the new video to **Sunday Worship Services**. Unlisted visibility allows playlist access without appearing in Videos. New unaudited API projects can be restricted to private uploads; use Studio upload if that restriction applies.

## Another service

Download September 20 evening:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/download-youtube.py --date 2026-09-20 --service evening
```

Change the date/service paths in the repair and acceptance commands to match. To look up the ID separately (for the upload command):

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/find-youtube-video.py --date 2026-09-20 --service evening
```

## If a command stops

- **Sign-in requested:** add `--cookies-from-browser edge` to the download command, using the browser where you are signed in (`edge`, `chrome`, or `firefox`).
- **Existing source:** if its download completed, skip step 2.
- **Existing repair folder:** use a new output folder, such as `work/audio-repair/20260920-evening-v2`.
- **Other error:** send the terminal error text.

# Audio repair

Run these commands in the VS Code terminal from `C:\repos\kenton-worship-workflow`.

## 1. Install the downloader — once

```powershell
.\work\youtube-venv\Scripts\python.exe -m pip install -U -r requirements-download.txt
```

## 2. Download September 20 morning

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/download-youtube.py V6DYhRG58Mw --date 2026-09-20 --service morning
```

Wait for **Downloaded**.

## 3. Repair the audio

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/repair-audio.py work/audio-repair/source/20260920-morning.mp4 --output-dir work/audio-repair/20260920-morning
```

Wait for **Complete**. The script adjusts audio levels and checks the result automatically.

## 4. Listen

Open:

```text
C:\repos\kenton-worship-workflow\work\audio-repair\20260920-morning\repaired.mp4
```

Check speech and music. September 27 is still being checked separately.

## 5. Accept after listening

If only the peak check failed, listen to `repaired.partial.mp4`. To accept the result:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/audio-repair-accept.py work/audio-repair/20260920-morning/repair.json
```

Success: **Accepted**. **Already accepted** also means this step is done. Continue to step 6; do not repeat acceptance.

## 6. Upload after approval — Python

With approval saved and upload OAuth already set up, run:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/youtube-audio.py upload work/audio-repair/20260920-morning/accepted.json --original-id V6DYhRG58Mw --title "Kenton Sunday Service - September 20, 2026 - Morning (AUDIO FIXED)" --reviewed
```

Success: **Private upload** with the new URL. Description, category, and audience setting come from the original. The original remains unchanged.

Check playback in Studio and add the new video to **Sunday Worship Services**. Unlisted visibility allows playlist access without appearing in Videos. New unaudited API projects can be restricted to private uploads; use Studio upload if that restriction applies.

## Another service

Find its video ID:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py list --date 2026-09-20
```

Use that ID, date, and `morning` or `evening` in step 2. Change the date/service filenames in steps 3 and 4 to match.

## If a command stops

- **Sign-in requested:** add `--cookies-from-browser edge` to the download command, using the browser where you are signed in (`edge`, `chrome`, or `firefox`).
- **Existing source:** if its download completed, skip step 2.
- **Existing repair folder:** use a new output folder, such as `work/audio-repair/20260920-morning-v2`.
- **Other error:** send the terminal error text.

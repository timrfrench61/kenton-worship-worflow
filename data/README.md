# YouTube video catalog

This is the inventory command reference. Start at the [project README](../README.md) for the overall workflow and folder map. Run commands from the project root; `data` stores the catalog, while `work` stores processing files and credentials.

`youtube-videos.json` is the Git-tracked inventory requested by the user. It starts empty until a successful read-authorized sync. It contains public video metadata and our editorial labels, not recordings, passwords, OAuth tokens, or private-video metadata.

Run commands from the repository root, using the local YouTube environment:

```powershell
# One-time setup, if this environment does not already exist:
python -m venv work/youtube-venv
.\work\youtube-venv\Scripts\python.exe -m pip install -r requirements-youtube.txt

# One-time Google read authorization (see setup below):
.\work\youtube-venv\Scripts\python.exe scripts/youtube-audio.py auth read

# Inventory and find the September 27 services:
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py sync
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py list --date 2026-09-27
```

Before authorization, enable YouTube Data API v3 in a Google Cloud project, configure its consent screen/test user as applicable, create a Desktop app OAuth client, and save the downloaded client JSON as `work/audio-repair/credentials/credentials-read.json`. Choose the Kenton account/channel in the browser. This uses Google's read-only grant; no upload/manage authorization is needed. Never put credentials in `data/`. Full setup is in [the audio workflow](../docs/01-kenton-audio-repair-001.md).

`sync` discovers the signed-in channel when there is exactly one, then pins future refreshes to its ID. If ambiguous, it lists choices; rerun with `sync --channel-id CHANNEL_ID`. It walks all pages of the uploads playlist and requests video metadata in batches. It inventories all public uploads, including repaired recordings that are no longer livestreams. `list --live-only` filters entries with live-streaming metadata; premieres can also have that metadata, so this is not a guaranteed livestream-only classification. Coverage is the videos returned through the uploads playlist, not every possible upcoming/live broadcast resource.

Local dates use `America/Los_Angeles`, including daylight saving time. The date basis is actual broadcast start, then scheduled start, then publication timestamp. The last fallback is not necessarily the service date. Morning/evening is deliberately not guessed from publication time. The `tzdata` dependency provides time zones on Windows.

After identifying each service, maintain labels and proposed titles locally:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py label VIDEO_ID --date 2026-09-27 --service morning --title "September 27, 2026 - Morning Worship (AUDIO FIXED)" --repair-status planned
```

Use `evening` and the evening ID for the other recording. These are proposed titles for the repaired uploads; labeling does not rename anything on YouTube. `--replacement-id` records the new video ID after an upload. Status choices are `unassessed`, `planned`, `rendered`, `reviewed`, and `uploaded`; these are operator-maintained labels, not substitutes for the audio workflow's measured report and review requirement. Direct edits to each entry's `local` object are also preserved during refresh.

Each entry is keyed by stable YouTube video ID, with separate `youtube` and `local` objects. API refresh replaces the former and preserves the latter. Missing/nonpublic entries previously inventoried are retained with `seen_in_public_inventory: false`, along with their earlier public metadata and labels; this does not assert deletion. Newly discovered private/unlisted metadata is not saved. Current titles, links, dates and proposed titles will be visible to anyone who can read the GitHub repository.

The catalog updates only after a complete successful fetch. Previous versions are backed up under ignored `work/youtube-inventory/backups`; writes use temporary-file replacement and detect concurrent edits. API failures leave the last catalog intact. Recordings and machine-specific source paths remain under `work/`, outside the catalog. Only this README and `youtube-videos.json` are allowed through the existing `data/` ignore rules.

Codex can refresh and maintain this catalog when working on your videos. No recurring schedule is installed. You decide when to commit and push; these commands never push or change YouTube. No live inventory has been claimed before authorization succeeds.

Implementation: `src/kenton_workflow/youtube_inventory.py`; entry point: `scripts/inventory-youtube.py`. Tests: `python -m unittest discover -s tests -p test_youtube_inventory.py -v`. Tests use fake API responses and real local CLI operations; live Google access is a separate verification.

API references: [channels.list](https://developers.google.com/youtube/v3/docs/channels/list), [playlistItems.list](https://developers.google.com/youtube/v3/docs/playlistItems/list), [videos.list](https://developers.google.com/youtube/v3/docs/videos/list).

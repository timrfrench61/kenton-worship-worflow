# YouTube inventory — setup and run

Run these commands in the VS Code PowerShell terminal. The catalog is saved in `data/youtube-videos.json`; credentials stay in ignored `work/`.

**Target:** Kenton Church EPC (`@kentonchurchepc8338`), channel `UCQv5lUpAVNhfV7RS1Hzbf-Q`. This is saved in root `youtube.json`, shared by inventory, authorization, upload, and old-video commands. Your personal channel (`UCf_VN9JkxVt21UJheXtRdzw`) and Kenton Session channel (`UCRgaPdRqB4C94lUiHwMSNvA`) are not targets. The Google sign-in account and Cloud project are separate from this channel selection.

## 1. Prepare Python — once

```powershell
cd C:\repos\kenton-worship-workflow
python -m venv work/youtube-venv
.\work\youtube-venv\Scripts\python.exe -m pip install -r requirements-youtube.txt
New-Item -ItemType Directory -Force work/audio-repair/credentials | Out-Null
```

## 2. Set up Google access — once

1. Open [Google Cloud Console](https://console.cloud.google.com/). Sign in with the Google account that manages Kenton's YouTube channel.
2. Open the project selector at the top → **New Project**. Name it **Kenton YouTube Read**, create it, and select it.
3. Open **APIs & Services → Library**. Search **YouTube Data API v3**, open it, and click **Enable**.
4. Open **Google Auth Platform → Branding → Get started**. Enter **Kenton YouTube Read** as the app name, your email for support/contact, and **External** as the audience. Complete the form.
5. Open **Audience**. Leave publishing status as **Testing**. Under **Test users → Add users**, add the Google email you will use to access the Kenton channel, then save.
6. Open **Data Access → Add or remove scopes**. Add `https://www.googleapis.com/auth/youtube.readonly`, then update/save.
7. Open **Clients → Create client**. Choose **Desktop app**, name it **Kenton Read Desktop**, and click **Create**. Download the client's JSON file.
8. Rename the downloaded file **credentials-read.json** and place it here:

   ```text
   C:\repos\kenton-worship-workflow\work\audio-repair\credentials\credentials-read.json
   ```

## 3. Sign in — first use

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/youtube-audio.py auth read
```

In the browser, sign in with the account that owns/manages Kenton, then select **Kenton Church EPC** as the channel and approve read access. Do not select **Kenton Session** or your personal channel. The script checks the channel before saving authorization. If Google shows an unverified-app warning for **your Kenton YouTube Read app**, use **Advanced → Go to Kenton YouTube Read**, then continue. If access is blocked, check that the signed-in email is listed under Test users.

Success: the terminal prints **Authorized read.** Testing-mode access can expire; rerun this command when reauthorization is requested.

## 4. Inventory the videos

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py sync
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py list --date 2026-09-27
```

Success: `data/youtube-videos.json` contains Kenton Church EPC's public videos, and the terminal lists September 27 candidates using Los Angeles dates. If authorization provides the wrong channel, repeat step 3 and select Kenton Church EPC. The script never substitutes another channel.

For later refreshes, repeat only step 4.

## Label a service

Replace `VIDEO_ID` with an ID from the list:

```powershell
.\work\youtube-venv\Scripts\python.exe scripts/inventory-youtube.py label VIDEO_ID --date 2026-09-27 --service morning --title "September 27, 2026 - Morning Worship (AUDIO FIXED)" --repair-status planned
```

Use `evening` and the evening video's ID for the other service. Labels and proposed titles survive refreshes. This edits the local catalog only; it does not rename or upload videos on YouTube.

The catalog can be committed to GitHub. Credentials, recordings, and catalog backups stay under ignored `work/`. The inventory includes public uploads; `list --live-only` narrows the list to videos with live-event metadata, which may also include premieres. Missing entries retain their last public details and local labels. Dates based on publication time may need a service-date correction.

Setup checked against Google's [YouTube Python guide](https://developers.google.com/youtube/v3/quickstart/python), [consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent), and [Desktop client instructions](https://developers.google.com/workspace/guides/create-credentials).

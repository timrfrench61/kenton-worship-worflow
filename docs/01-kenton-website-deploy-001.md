# Kenton website deployment

Run this workflow from `C:\repos\kenton-worship-workflow`. Settings are in `website.json`. Code and this procedure belong in Git; release packages, receipts, and backups stay under ignored `work/`.

## Weekly release

Use the activated `.automation-venv` terminal and the current week's completed Input. Set any desired card appearance in `website.json` before step 1 (settings are described below).

Run one numbered step at a time from `C:\repos\kenton-worship-workflow`. Wait for each command to finish successfully before continuing.

1. Prepare the website cards:

   ```powershell
   python scripts/update-automation.py --website-only
   ```

   Success: **Website panels ready for review**.

2. Open `work/desktop/worship-highlights.json`. Review the service dates, card text, Scripture references, links, and selected images. Continue when the content is correct.

3. Apply the reviewed cards to the local website:

   ```powershell
   python scripts/publish-automation.py --website-only --reviewed
   ```

   Success: the command completes without an ATTENTION error and updates the local website's `wwwroot/data/worship-highlights.json`.

4. Run the website in Visual Studio. Review dates, text, colors, images, links, and mobile layout. Review any other website changes that will be included in this release.

5. Check deployment configuration:

   ```powershell
   python scripts/deploy-website.py --check
   ```

   Success: **Deployment configuration: complete** and **Live deployment enabled: True**. This is a local configuration check; it does not test the server connection.

6. Build the release. Change the note to describe this week's changes:

   ```powershell
   python scripts/deploy-website.py --prepare --note "Weekly worship panels and card appearance"
   ```

   Success: **Prepared release**. The script manages the release ID. If you change the local website after this step, build again before deploying.

7. Deploy the latest prepared release:

   ```powershell
   python scripts/deploy-website.py --deploy --reviewed --release
   ```

   Success: **Deployment verified** and the receipt path. Expect a brief website interruption during the switch. No ID or folder needs to be entered.

8. Open `https://kentonchurch.org`. Confirm the live dates, text, images, colors, and links match your review.

9. Check `work/desktop/website-maintenance.log` and the **Website Maintenance** sheet in `G:\My Drive\kenton\_worship\recent-logs.xlsx` for the successful release. If workbook logging is pending, follow the logging recovery command below.

### Release records

Preparation builds the full application and records file hashes and the website Git revision. Deployment preserves server settings, verifies the uploaded package, restarts the website service, and checks service state, HTTPS, and the published panel-data hash. It leaves DNS and Caddy unchanged.

The selected release folder under `work/website-deploy` contains `receipt.json` and timestamped `deployment.log` entries. If the latest release was already attempted, prepare a new release; automatic selection never falls back to an older build.

## Failure and recovery

An unhealthy activated release triggers automatic restoration of the previous files, followed by service and HTTP checks. Read `receipt.json`: `rolled_back` means recovery checks passed; `rollback_failed` requires manual server investigation; `unknown_check_server` means the connection did not establish a final state. Do not redeploy blindly after an unknown result.

Server evidence stays under `/home/tim/kenton-deploy/RELEASE_ID`: `remote-receipt.json`, `previous/`, and, on failed activation, `failed/`. Successful releases retain their predecessor. Local evidence stays in the matching `work/website-deploy/RELEASE_ID`. No automatic archive deletion is implemented. Retrying an already attempted release is refused; prepare a new release after diagnosing the problem. This version implements automatic failure rollback, not a separate operator command to roll back a healthy release.

If only workbook logging fails, deployment remains recorded as successful with `workbook_log: pending`. Close Excel/resolve Drive access and retry logging only:

```powershell
python scripts/deploy-website.py --log-only (Read-Host "Paste the affected release folder path printed in the deployment receipt")
```

At the prompt, paste the affected release folder path without surrounding quotes. Unlike normal deployment, this recovery command requires the specific folder whose logging failed. Release IDs prevent duplicate maintenance rows. Logging backs up the workbook before editing and detects changes made while it saves. Planning sheets remain intact. Do not run deployment again merely to retry logging.

## Server configuration reference

Server versions below were observed on October 2, 2026. `website.json` is the deployment configuration; use `--inspect` to refresh server observations.

| Parameter | Value / behavior |
| --- | --- |
| DigitalOcean project / Droplet | kenton-church / kenton-web-01 |
| SSH host / user | 138.68.26.140 / tim, port 22 |
| Public URL | https://kentonchurch.org; Caddy also serves www.kentonchurch.org |
| OS / architecture | Ubuntu 24.04.4 / x86_64 |
| Installed runtime | ASP.NET Core and .NET 10.0.12 |
| Service | kenton-website, runs as tim |
| Service directory | /var/www/kenton |
| Executable | /usr/bin/dotnet /var/www/kenton/kenton_website.dll |
| Proxy | Caddy 2.6.2, proxies to 127.0.0.1:5000 |
| Local project | C:/repos/kenton_website/kenton_website.csproj |
| Build | Release, framework-dependent, no Windows apphost; full application, not just wwwroot |
| Server-only settings preserved | Existing appsettings.json, appsettings.Production.json, appsettings.Development.json |
| Local history | work/website-deploy plus work/desktop/website-maintenance.log |
| Workbook logging | deployment.maintenance_workbook settings; separate Website Maintenance sheet |

If you introduce uploads, databases, or other runtime-written files, add an explicit preservation design before deploying; this release procedure replaces website content and retains the old copy in the release archive. It does not migrate server settings. The `--inspect` command can refresh a read-only host report:

```powershell
python scripts/deploy-website.py --inspect
```

## Card appearance

1. Edit `website.json` in this project. Under `cards`, choose one of `last-sunday-morning`, `last-sunday-evening`, `next-sunday-morning`, or `next-sunday-evening`.
2. Set `backgroundImage` to an existing filename under `C:/repos/kenton_website/wwwroot/images/card-background`. Under `appearance`, set colors using `#RRGGBB` or `#RRGGBBAA` (the final pair controls opacity). `imageOpacity` is a quoted value from `"0"` to `"1"`.
3. Follow the weekly release steps above to prepare, review, apply, build, and deploy these settings. Changing `website.json` after card preparation requires repeating preparation before local publication.

Supported colors: `backgroundColor`, `overlayColor`, `textColor`, `headingColor`, `accentColor`, `borderColor`, `linkColor`. Text and card content continue to come from the worship planner. Settings are applied by card slot after date rollover, so a last-Sunday card receives that slot's appearance. Existing metadata and sermon-text colors retain the website's styling.

The website renderer validates values before using them as CSS variables. Existing website styling remains the fallback for cards without appearance settings.

## Rebuild server access (one-time setup)

Server permissions have been verified and deployment is enabled. This one-time setup is retained for rebuilding access; skip it for normal weekly releases.

1. Connect from PowerShell:

   ```powershell
   ssh tim@138.68.26.140
   ```

2. At the Droplet's `tim@kenton-web-01:~$` prompt, open the rule in the Nano editor:

   ```sh
   sudo EDITOR=nano visudo -f /etc/sudoers.d/kenton-website-deploy
   ```

   Enter your sudo password if prompted (no characters appear while typing). Continue only when the Nano editor opens.

3. Paste this single line **inside the editor, not at the shell prompt**. If the file already contains this rule, do not add a duplicate:

   ```text
   tim ALL=(root) NOPASSWD: /usr/bin/systemctl stop kenton-website, /usr/bin/systemctl start kenton-website
   ```

   Press **Ctrl+O**, then **Enter** to save; press **Ctrl+X** to exit. Success returns you to `tim@kenton-web-01:~$` without a syntax error. If visudo reports an error, choose `e` to reopen and correct the line.

   If you saw `-bash: syntax error near unexpected token '('`, the rule was pasted into Bash instead of the editor. It did not install the rule; repeat steps 2 and 3.

4. Validate the saved rule:

   ```sh
   sudo visudo -cf /etc/sudoers.d/kenton-website-deploy
   ```

   Success: **parsed OK**.

5. Check stop permission without stopping the website:

   ```sh
   sudo -n -l /usr/bin/systemctl stop kenton-website
   ```

   Success: the permitted command is printed without a password prompt.

6. Check start permission without starting or restarting the website:

   ```sh
   sudo -n -l /usr/bin/systemctl start kenton-website
   ```

   Success: the permitted command is printed without a password prompt.

7. Return to your local terminal:

   ```sh
   exit
   ```

8. Set `deployment.enabled` to `true` in `website.json` after both permission checks pass. Private keys and passwords do not belong in configuration.

## Implementation and verification

Entry point: `scripts/deploy-website.py`. Local release/history/logging: `scripts/_website_release.py`. Uploaded activation and automatic rollback: `scripts/_website_remote.py`. Regression tests: `tests/test_website_deploy.py`.

Verified: live SSH inspection, local .NET Release build, and isolated CLI tests of activation, hash rejection before stopping the service, failed-health rollback, and workbook-log idempotency. Service actions and HTTP responses in those tests are simulated. The user has since reported successful live deployment. The fixture tests do not establish a successful write to the real maintenance workbook; confirm that using the release receipt and Website Maintenance sheet.

References: [DigitalOcean OpenSSH](https://docs.digitalocean.com/products/droplets/how-to/connect-with-ssh/openssh/) and [Microsoft ASP.NET Core Linux hosting](https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/linux-nginx?view=aspnetcore-10.0). The latter documents application publishing/systemd; this server's Caddy configuration was independently inspected.
